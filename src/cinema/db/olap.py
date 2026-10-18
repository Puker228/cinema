"""Хранилище данных: ETL в схему «звезда» и OLAP-куб продаж.

Измерения: дата (год → квартал → месяц → день), время суток, фильм (жанр → фильм),
зал (тип → зал). Меры: выручка, билеты, сеансы, средняя цена, заполняемость.
Срезы (slice/dice) — фильтры по значениям измерений, свёртка/детализация
(roll-up/drill-down) — смена уровня иерархии измерения.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text

from cinema.db.engine import engine

MONTHS = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]  # fmt: skip
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

# Название измерения -> SQL-выражение над fact_sales f / dim_date d / dim_film fl / dim_hall h.
DIMENSIONS: dict[str, str] = {
    "Год": "CAST(d.year AS TEXT)",
    "Квартал": "d.year || ' Q' || d.quarter",
    "Месяц": "d.year || '-' || printf('%02d', d.month) || ' ' || d.month_name",
    "Дата": "d.full_date",
    "День недели": "d.weekday || ' ' || d.weekday_name",
    "Время суток": (
        "CASE WHEN f.start_hour < 12 THEN '1 Утро (до 12)' "
        "WHEN f.start_hour < 17 THEN '2 День (12–17)' ELSE '3 Вечер (после 17)' END"
    ),
    "Жанр": "fl.genre",
    "Фильм": "fl.title",
    "Возрастной рейтинг": "fl.age_rating",
    "Тип зала": "h.hall_type",
    "Зал": "h.name",
}

MEASURES: dict[str, str] = {
    "Выручка, ₽": "ROUND(SUM(f.revenue), 2)",
    "Билеты, шт": "SUM(f.tickets_count)",
    "Сеансы, шт": "COUNT(*)",
    "Средняя цена, ₽": "ROUND(SUM(f.revenue) / NULLIF(SUM(f.tickets_count), 0), 2)",
    "Заполняемость, %": "ROUND(100.0 * SUM(f.tickets_count) / NULLIF(SUM(f.capacity), 0), 1)",
}

# Срезы: название -> SQL-выражение, по которому фильтруем.
FILTERS: dict[str, str] = {"Год": "d.year", "Жанр": "fl.genre", "Зал": "h.name"}

_STAR_JOIN = """
FROM fact_sales f
JOIN dim_date d ON d.date_key = f.date_key
JOIN dim_film fl ON fl.film_key = f.film_key
JOIN dim_hall h ON h.hall_key = f.hall_key
"""


def refresh_warehouse() -> int:
    """ETL: полностью перезагружает измерения и факты из операционных таблиц. Возвращает число фактов."""
    with engine.begin() as conn:
        for table in ("fact_sales", "dim_date", "dim_film", "dim_hall"):
            conn.execute(text(f"DELETE FROM {table}"))

        conn.execute(
            text(
                """
                INSERT INTO dim_film (film_key, title, genre, age_rating, release_year)
                SELECT f.id, f.title, g.name, f.age_rating, f.release_year
                FROM films f JOIN genres g ON g.id = f.genre_id
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO dim_hall (hall_key, name, hall_type, capacity)
                SELECT id, name, hall_type, rows_count * seats_per_row FROM halls
                """
            )
        )
        days = [
            r[0]
            for r in conn.execute(
                text("SELECT DISTINCT date(start_time) FROM sessions")
            )
        ]
        rows = []
        for day in days:
            year, month, dd = map(int, day.split("-"))
            weekday = date(year, month, dd).isoweekday()
            rows.append(
                {
                    "key": year * 10000 + month * 100 + dd,
                    "date": day,
                    "day": dd,
                    "month": month,
                    "month_name": MONTHS[month - 1],
                    "quarter": (month - 1) // 3 + 1,
                    "year": year,
                    "weekday": weekday,
                    "weekday_name": WEEKDAYS[weekday - 1],
                }
            )
        if rows:
            conn.execute(
                text(
                    "INSERT INTO dim_date (date_key, full_date, day, month, month_name, quarter, year, "
                    "weekday, weekday_name) VALUES (:key, :date, :day, :month, :month_name, :quarter, "
                    ":year, :weekday, :weekday_name)"
                ),
                rows,
            )
        conn.execute(
            text(
                """
                INSERT INTO fact_sales (session_id, date_key, film_key, hall_key, start_hour,
                                        tickets_count, revenue, capacity)
                SELECT v.session_id,
                       CAST(strftime('%Y%m%d', v.start_time) AS INTEGER),
                       v.film_id, v.hall_id,
                       CAST(strftime('%H', v.start_time) AS INTEGER),
                       v.sold, v.revenue, v.capacity
                FROM v_session_info v
                """
            )
        )
        return conn.execute(text("SELECT COUNT(*) FROM fact_sales")).scalar()


def warehouse_info() -> tuple[int, str | None, str | None]:
    with engine.connect() as conn:
        return tuple(
            conn.execute(
                text(
                    f"SELECT COUNT(*), MIN(d.full_date), MAX(d.full_date) {_STAR_JOIN}"
                )
            ).one()
        )


def filter_values(name: str) -> list[str]:
    with engine.connect() as conn:
        expr = FILTERS[name]
        return [
            str(r[0])
            for r in conn.execute(
                text(f"SELECT DISTINCT {expr} {_STAR_JOIN} ORDER BY 1")
            )
        ]


@dataclass
class Pivot:
    row_keys: list[str]
    col_keys: list[str]  # пусто, если измерение столбцов не выбрано
    cells: dict[tuple[str, str], float]
    row_totals: dict[str, float]
    col_totals: dict[str, float]
    grand_total: float | None


def build_pivot(
    row_dim: str,
    col_dim: str | None,
    measure: str,
    filters: dict[str, str] | None = None,
) -> Pivot:
    """Строит сводную таблицу куба. Итоги считаются отдельными агрегатами — корректно и для неаддитивных мер."""
    measure_sql = MEASURES[measure]
    where, params = [], {}
    for i, (name, value) in enumerate((filters or {}).items()):
        where.append(f"CAST({FILTERS[name]} AS TEXT) = :f{i}")
        params[f"f{i}"] = value
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    def query(*dims: str) -> list[tuple]:
        select = ", ".join([*(DIMENSIONS[d] for d in dims), measure_sql])
        group = (
            ("GROUP BY " + ", ".join(str(i + 1) for i in range(len(dims))))
            if dims
            else ""
        )
        sql = f"SELECT {select} {_STAR_JOIN} {where_sql} {group}"
        with engine.connect() as conn:
            return [tuple(r) for r in conn.execute(text(sql), params)]

    row_totals = {str(k): v for k, v in query(row_dim)}
    cells, col_totals = {}, {}
    if col_dim:
        cells = {(str(r), str(c)): v for r, c, v in query(row_dim, col_dim)}
        col_totals = {str(k): v for k, v in query(col_dim)}
    grand = query()[0][0]
    return Pivot(
        row_keys=sorted(row_totals),
        col_keys=sorted(col_totals),
        cells=cells,
        row_totals=row_totals,
        col_totals=col_totals,
        grand_total=grand,
    )
