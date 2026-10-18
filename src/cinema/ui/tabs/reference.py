"""Справочники: жанры, фильмы, залы, покупатели."""

from __future__ import annotations

from cinema.db.models import AGE_RATINGS, HALL_TYPES, Customer, Film, Genre, Hall
from cinema.ui.crud import CrudTab, Field, ref_choices


def genres_tab() -> CrudTab:
    return CrudTab(
        Genre,
        "Жанр",
        [Field("name", "Название")],
        """SELECT g.id, g.name, COUNT(f.id)
           FROM genres g LEFT JOIN films f ON f.genre_id = g.id
           GROUP BY g.id ORDER BY g.name""",
        ["№", "Жанр", "Фильмов"],
    )


def films_tab() -> CrudTab:
    return CrudTab(
        Film,
        "Фильм",
        [
            Field("title", "Название"),
            Field(
                "genre_id",
                "Жанр",
                "ref",
                ref_choices("SELECT name, id FROM genres ORDER BY name"),
            ),
            Field(
                "duration_min",
                "Длительность, мин",
                "int",
                minimum=1,
                maximum=600,
                default=120,
            ),
            Field("age_rating", "Возраст", "choice", AGE_RATINGS, default="12+"),
            Field(
                "release_year",
                "Год выпуска",
                "int",
                minimum=1895,
                maximum=2100,
                default=2025,
            ),
            Field("description", "Описание", "multiline", required=False),
        ],
        """SELECT f.id, f.title, g.name, f.duration_min, f.age_rating, f.release_year,
                  (SELECT COUNT(*) FROM sessions s WHERE s.film_id = f.id), f.description
           FROM films f JOIN genres g ON g.id = f.genre_id
           ORDER BY f.title""",
        ["№", "Название", "Жанр", "Мин", "Возраст", "Год", "Сеансов", "Описание"],
    )


def halls_tab() -> CrudTab:
    return CrudTab(
        Hall,
        "Зал",
        [
            Field("name", "Название"),
            Field("hall_type", "Тип", "choice", HALL_TYPES),
            Field("rows_count", "Рядов", "int", minimum=1, maximum=50, default=10),
            Field(
                "seats_per_row", "Мест в ряду", "int", minimum=1, maximum=60, default=12
            ),
        ],
        """SELECT hall_id, name, hall_type, capacity, sessions_count, tickets_sold, revenue, avg_occupancy
           FROM v_hall_stats ORDER BY name""",
        [
            "№",
            "Зал",
            "Тип",
            "Мест",
            "Сеансов",
            "Продано",
            "Выручка, ₽",
            "Ср. заполняемость, %",
        ],
    )


def customers_tab() -> CrudTab:
    return CrudTab(
        Customer,
        "Покупатель",
        [
            Field("full_name", "ФИО"),
            Field("phone", "Телефон", required=False),
            Field("email", "E-mail", required=False),
        ],
        """SELECT c.id, c.full_name, c.phone, c.email,
                  COUNT(t.id), COALESCE(ROUND(SUM(t.price), 2), 0)
           FROM customers c LEFT JOIN tickets t ON t.customer_id = c.id AND t.status = 'sold'
           GROUP BY c.id ORDER BY c.full_name""",
        ["№", "ФИО", "Телефон", "E-mail", "Билетов", "Потрачено, ₽"],
    )
