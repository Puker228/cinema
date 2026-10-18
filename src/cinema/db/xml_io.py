"""Экспорт и импорт данных в XML.

Связи между сущностями в файле задаются естественными ключами (название жанра,
название+год фильма, имя зала, зал+время сеанса, телефон покупателя), поэтому файл
можно загрузить в любую базу, а не только в ту, из которой он выгружен.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from cinema.db.engine import engine, now_str
from cinema.db.errors import describe_error

ENTITIES = {
    "genres": "Жанры",
    "films": "Фильмы",
    "halls": "Залы",
    "customers": "Покупатели",
    "sessions": "Сеансы",
    "tickets": "Билеты",
}

_EXPORT_SQL = {
    "genres": "SELECT name FROM genres ORDER BY name",
    "films": """SELECT f.title, g.name AS genre, f.duration_min, f.age_rating, f.release_year, f.description
                FROM films f JOIN genres g ON g.id = f.genre_id ORDER BY f.title""",
    "halls": "SELECT name, rows_count, seats_per_row, hall_type FROM halls ORDER BY name",
    "customers": "SELECT full_name, phone, email FROM customers ORDER BY full_name",
    "sessions": """SELECT f.title AS film, f.release_year AS film_year, h.name AS hall, s.start_time, s.base_price
                   FROM sessions s JOIN films f ON f.id = s.film_id JOIN halls h ON h.id = s.hall_id
                   ORDER BY s.start_time""",
    "tickets": """SELECT h.name AS hall, s.start_time AS session_start, t.row_num, t.seat_num, t.price,
                         t.sold_at, t.status, c.phone AS customer_phone
                  FROM tickets t JOIN sessions s ON s.id = t.session_id JOIN halls h ON h.id = s.hall_id
                  LEFT JOIN customers c ON c.id = t.customer_id
                  ORDER BY s.start_time, t.row_num, t.seat_num""",
}

# Порядок важен: сначала справочники, потом зависящие от них сущности.
_ORDER = list(ENTITIES)


def export_xml(path: str | Path, entities: list[str] | None = None) -> dict[str, int]:
    """Выгружает выбранные сущности в XML-файл. Возвращает число выгруженных записей по каждой."""
    entities = [e for e in _ORDER if e in (entities or _ORDER)]
    root = ET.Element("cinema", exported_at=now_str())
    counts = {}
    with engine.connect() as conn:
        for entity in entities:
            container = ET.SubElement(root, entity)
            result = conn.execute(text(_EXPORT_SQL[entity]))
            columns = list(result.keys())
            item_tag = entity[:-1]
            n = 0
            for row in result:
                item = ET.SubElement(container, item_tag)
                for col, value in zip(columns, row, strict=True):
                    if value is not None:
                        ET.SubElement(item, col).text = str(value)
                n += 1
            counts[entity] = n
    tree = ET.ElementTree(root)
    ET.indent(tree)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return counts


@dataclass
class ImportReport:
    added: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)
    unchanged: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def count(self, kind: str, entity: str) -> None:
        bucket = getattr(self, kind)
        bucket[entity] = bucket.get(entity, 0) + 1

    def summary(self) -> str:
        lines = []
        for entity, title in ENTITIES.items():
            a, u, n, s = (
                getattr(self, k).get(entity, 0)
                for k in ("added", "updated", "unchanged", "skipped")
            )
            if a or u or n or s:
                lines.append(
                    f"{title}: добавлено {a}, обновлено {u}, без изменений {n}, с ошибками {s}"
                )
        if self.errors:
            lines.append(f"\nОшибки ({len(self.errors)}):")
            lines.extend(self.errors[:20])
            if len(self.errors) > 20:
                lines.append(f"… и ещё {len(self.errors) - 20}")
        return "\n".join(lines) or "Файл не содержит данных"


def _fields(item: ET.Element) -> dict[str, str | None]:
    return {child.tag: child.text for child in item}


def _scalar(conn: Connection, sql: str, **params):
    return conn.execute(text(sql), params).scalar()


def _upsert(
    conn: Connection,
    report: ImportReport,
    entity: str,
    existing_id,
    insert_sql,
    update,
    params,
):
    """update — {столбец: параметр}; строка обновляется, только если значения действительно отличаются."""
    if existing_id is None:
        conn.execute(text(insert_sql), params)
        report.count("added", entity)
        return
    if update:
        assignments = ", ".join(f"{col} = :{param}" for col, param in update.items())
        same = " AND ".join(f"{col} IS :{param}" for col, param in update.items())
        sql = f"UPDATE {entity} SET {assignments} WHERE id = :id AND NOT ({same})"
        if conn.execute(text(sql), {**params, "id": existing_id}).rowcount:
            report.count("updated", entity)
            return
    report.count("unchanged", entity)


def _import_item(conn: Connection, report: ImportReport, entity: str, f: dict) -> None:
    if entity == "genres":
        existing = _scalar(conn, "SELECT id FROM genres WHERE name = :n", n=f["name"])
        _upsert(
            conn,
            report,
            entity,
            existing,
            "INSERT INTO genres (name) VALUES (:name)",
            None,
            f,
        )

    elif entity == "films":
        genre_id = _scalar(conn, "SELECT id FROM genres WHERE name = :n", n=f["genre"])
        if genre_id is None:
            conn.execute(
                text("INSERT INTO genres (name) VALUES (:n)"), {"n": f["genre"]}
            )
            genre_id = _scalar(
                conn, "SELECT id FROM genres WHERE name = :n", n=f["genre"]
            )
        params = {**f, "genre_id": genre_id, "description": f.get("description") or ""}
        existing = _scalar(
            conn,
            "SELECT id FROM films WHERE title = :t AND release_year = :y",
            t=f["title"],
            y=f["release_year"],
        )
        _upsert(
            conn,
            report,
            entity,
            existing,
            "INSERT INTO films (title, genre_id, duration_min, age_rating, release_year, description) "
            "VALUES (:title, :genre_id, :duration_min, :age_rating, :release_year, :description)",
            {c: c for c in ("genre_id", "duration_min", "age_rating", "description")},
            params,
        )

    elif entity == "halls":
        existing = _scalar(conn, "SELECT id FROM halls WHERE name = :n", n=f["name"])
        _upsert(
            conn,
            report,
            entity,
            existing,
            "INSERT INTO halls (name, rows_count, seats_per_row, hall_type) "
            "VALUES (:name, :rows_count, :seats_per_row, :hall_type)",
            {c: c for c in ("rows_count", "seats_per_row", "hall_type")},
            f,
        )

    elif entity == "customers":
        params = {
            "full_name": f["full_name"],
            "phone": f.get("phone"),
            "email": f.get("email"),
        }
        existing = None
        if params["phone"]:
            existing = _scalar(
                conn, "SELECT id FROM customers WHERE phone = :p", p=params["phone"]
            )
        _upsert(
            conn,
            report,
            entity,
            existing,
            "INSERT INTO customers (full_name, phone, email) VALUES (:full_name, :phone, :email)",
            {"full_name": "full_name", "email": "email"},
            params,
        )

    elif entity == "sessions":
        film_id = _scalar(
            conn,
            "SELECT id FROM films WHERE title = :t AND release_year = :y",
            t=f["film"],
            y=f["film_year"],
        )
        hall_id = _scalar(conn, "SELECT id FROM halls WHERE name = :n", n=f["hall"])
        if film_id is None or hall_id is None:
            raise LookupError(f"не найден фильм «{f['film']}» или зал «{f['hall']}»")
        params = {
            "film_id": film_id,
            "hall_id": hall_id,
            "start": f["start_time"],
            "price": f["base_price"],
        }
        existing = _scalar(
            conn,
            "SELECT id FROM sessions WHERE hall_id = :h AND start_time = :s",
            h=hall_id,
            s=f["start_time"],
        )
        _upsert(
            conn,
            report,
            entity,
            existing,
            "INSERT INTO sessions (film_id, hall_id, start_time, base_price) VALUES (:film_id, :hall_id, :start, :price)",
            {"film_id": "film_id", "base_price": "price"},
            params,
        )

    elif entity == "tickets":
        session_id = _scalar(
            conn,
            "SELECT s.id FROM sessions s JOIN halls h ON h.id = s.hall_id WHERE h.name = :h AND s.start_time = :s",
            h=f["hall"],
            s=f["session_start"],
        )
        if session_id is None:
            raise LookupError(f"не найден сеанс {f['hall']} {f['session_start']}")
        customer_id = None
        if f.get("customer_phone"):
            customer_id = _scalar(
                conn, "SELECT id FROM customers WHERE phone = :p", p=f["customer_phone"]
            )
        params = {
            "session_id": session_id,
            "customer_id": customer_id,
            "row": f["row_num"],
            "seat": f["seat_num"],
            "price": f.get("price"),
            "sold_at": f.get("sold_at") or now_str(),
            "status": f.get("status") or "sold",
        }
        existing = _scalar(
            conn,
            "SELECT id FROM tickets WHERE session_id = :s AND row_num = :r AND seat_num = :n AND status = :st",
            s=session_id,
            r=f["row_num"],
            n=f["seat_num"],
            st=params["status"],
        )
        _upsert(
            conn,
            report,
            entity,
            existing,
            "INSERT INTO tickets (session_id, customer_id, row_num, seat_num, price, sold_at, status) "
            "VALUES (:session_id, :customer_id, :row, :seat, :price, :sold_at, :status)",
            None,
            params,
        )


def import_xml(path: str | Path) -> ImportReport:
    """Загружает XML-файл. Строки, нарушающие ограничения/триггеры, пропускаются и попадают в отчёт."""
    root = ET.parse(path).getroot()
    if root.tag != "cinema":
        raise ValueError(
            "Это не файл выгрузки кинотеатра (ожидается корневой элемент <cinema>)"
        )
    report = ImportReport()
    # Одна транзакция на весь файл. В SQLite ошибка ограничения или RAISE(ABORT) в триггере
    # откатывает только текущую инструкцию, поэтому ошибочную строку можно просто пропустить.
    with engine.begin() as conn:
        for entity in _ORDER:
            container = root.find(entity)
            if container is None:
                continue
            for i, item in enumerate(container, start=1):
                try:
                    _import_item(conn, report, entity, _fields(item))
                except (IntegrityError, LookupError, KeyError) as exc:
                    report.count("skipped", entity)
                    reason = (
                        f"нет поля {exc}"
                        if isinstance(exc, KeyError)
                        else describe_error(exc)
                    )
                    report.errors.append(f"{ENTITIES[entity]} #{i}: {reason}")
    return report
