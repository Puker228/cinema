"""Заполнение базы демонстрационными данными."""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta

from sqlalchemy import text

from cinema.db.ddl import CLEANING_MIN
from cinema.db.engine import DT_FORMAT, engine

GENRES = [
    "Драма",
    "Комедия",
    "Фантастика",
    "Боевик",
    "Мультфильм",
    "Ужасы",
    "Триллер",
    "Мелодрама",
]

# (название, жанр, длительность, возраст, год, описание)
FILMS = [
    (
        "Интерстеллар",
        "Фантастика",
        169,
        "12+",
        2014,
        "Путешествие сквозь червоточину ради спасения человечества.",
    ),
    (
        "Дюна: Часть вторая",
        "Фантастика",
        166,
        "12+",
        2024,
        "Пол Атрейдес объединяется с фрименами.",
    ),
    ("Оппенгеймер", "Драма", 180, "18+", 2023, "История создателя атомной бомбы."),
    ("Головоломка 2", "Мультфильм", 96, "6+", 2024, "У Райли появляются новые эмоции."),
    (
        "Джон Уик 4",
        "Боевик",
        169,
        "18+",
        2023,
        "Джон Уик бросает вызов Правлению Кланов.",
    ),
    ("Барби", "Комедия", 114, "16+", 2023, "Барби отправляется в реальный мир."),
    ("Чебурашка", "Комедия", 113, "6+", 2023, "Необычный зверёк в приморском городке."),
    ("Холоп 2", "Комедия", 107, "12+", 2024, "Новое перевоспитание мажорки."),
    ("Мастер и Маргарита", "Драма", 157, "18+", 2024, "Экранизация романа Булгакова."),
    (
        "Субстанция",
        "Ужасы",
        141,
        "18+",
        2024,
        "Препарат, создающий лучшую версию тебя.",
    ),
    (
        "Дэдпул и Росомаха",
        "Боевик",
        128,
        "18+",
        2024,
        "Наёмник с длинным языком и Росомаха.",
    ),
    ("Гадкий я 4", "Мультфильм", 94, "0+", 2024, "Грю и миньоны снова в деле."),
    ("Чужой: Ромул", "Ужасы", 119, "18+", 2024, "Колонисты на заброшенной станции."),
    (
        "Ла-Ла Ленд",
        "Мелодрама",
        128,
        "16+",
        2016,
        "Джазовый пианист и начинающая актриса.",
    ),
    ("Паразиты", "Триллер", 132, "18+", 2019, "Бедная семья проникает в дом богачей."),
    ("Начало", "Фантастика", 148, "12+", 2010, "Кража идей из снов."),
]

# (название, рядов, мест в ряду, тип, надбавка к базовой цене)
HALLS = [
    ("Зал 1", 10, 14, "2D", 0),
    ("Зал 2 (3D)", 8, 12, "3D", 0),
    ("IMAX", 12, 20, "IMAX", 0),
    ("VIP", 5, 8, "2D", 300),
]

FIRST_NAMES = [
    "Алексей",
    "Мария",
    "Иван",
    "Екатерина",
    "Дмитрий",
    "Анна",
    "Сергей",
    "Ольга",
    "Никита",
    "Полина",
]
LAST_NAMES = [
    "Иванов",
    "Смирнов",
    "Кузнецов",
    "Попов",
    "Соколов",
    "Лебедев",
    "Козлов",
    "Новиков",
]

DAYS_BACK = 45
DAYS_FORWARD = 7


def _female(last_name: str, first_name: str) -> str:
    return last_name + "а" if first_name[-1] in "ая" else last_name


def seed(rng_seed: int = 42) -> None:
    rng = random.Random(rng_seed)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO genres (name) VALUES (:name)"),
            [{"name": g} for g in GENRES],
        )
        genre_ids = dict(conn.execute(text("SELECT name, id FROM genres")).all())

        conn.execute(
            text(
                "INSERT INTO films (title, genre_id, duration_min, age_rating, release_year, description) "
                "VALUES (:title, :genre_id, :duration, :age, :year, :descr)"
            ),
            [
                {
                    "title": t,
                    "genre_id": genre_ids[g],
                    "duration": d,
                    "age": a,
                    "year": y,
                    "descr": ds,
                }
                for t, g, d, a, y, ds in FILMS
            ],
        )
        films = conn.execute(
            text("SELECT id, duration_min, release_year, age_rating FROM films")
        ).all()

        conn.execute(
            text(
                "INSERT INTO halls (name, rows_count, seats_per_row, hall_type) VALUES (:name, :rows, :seats, :type)"
            ),
            [{"name": n, "rows": r, "seats": s, "type": t} for n, r, s, t, _ in HALLS],
        )
        halls = conn.execute(
            text("SELECT id, name, rows_count, seats_per_row FROM halls ORDER BY id")
        ).all()
        surcharge = {n: extra for n, *_, extra in HALLS}

        customers = []
        for i in range(40):
            first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
            customers.append(
                {
                    "name": f"{_female(last, first)} {first}",
                    "phone": f"+7 9{rng.randint(10, 99)} {rng.randint(100, 999)}-{i:02d}-{rng.randint(10, 99)}",
                    "email": f"user{i + 1}@{rng.choice(['mail.ru', 'yandex.ru', 'gmail.com'])}",
                }
            )
        conn.execute(
            text(
                "INSERT INTO customers (full_name, phone, email) VALUES (:name, :phone, :email)"
            ),
            customers,
        )
        # Несколько покупателей ещё ничего не купили.
        customer_ids = [
            row[0] for row in conn.execute(text("SELECT id FROM customers"))
        ][:-5]

        # Расписание: в каждом зале сеансы подряд с 10:00 до полуночи.
        today = date.today()
        sessions = []
        for offset in range(-DAYS_BACK, DAYS_FORWARD + 1):
            day = today + timedelta(days=offset)
            # Старые фильмы — ретроспектива, которая шла только в начале периода.
            day_films = [
                f for f in films if f.release_year >= 2020 or offset < -DAYS_BACK // 2
            ]
            for hall in halls:
                # Во VIP-зале не показывают детские фильмы.
                hall_films = [
                    f
                    for f in day_films
                    if hall.name != "VIP" or f.age_rating not in ("0+", "6+")
                ]
                start = datetime.combine(day, time(10, 0)) + timedelta(
                    minutes=rng.choice([0, 10, 20, 30])
                )
                day_end = datetime.combine(day + timedelta(days=1), time(0, 0))
                while True:
                    film_id, duration, *_ = rng.choice(hall_films)
                    if start + timedelta(minutes=duration) > day_end:
                        break
                    base = 300 if start.hour < 12 else 400 if start.hour < 17 else 500
                    sessions.append(
                        {
                            "film_id": film_id,
                            "hall_id": hall.id,
                            "start": start.strftime(DT_FORMAT),
                            "price": base + surcharge[hall.name],
                        }
                    )
                    gap = duration + CLEANING_MIN
                    start += timedelta(minutes=gap + (-gap) % 10)
        conn.execute(
            text(
                "INSERT INTO sessions (film_id, hall_id, start_time, base_price) "
                "VALUES (:film_id, :hall_id, :start, :price)"
            ),
            sessions,
        )

        # Билеты: прошедшие сеансы заполнены сильнее будущих, вечер и выходные — популярнее.
        hall_by_id = {h.id: h for h in halls}
        now = datetime.now()
        tickets = []
        for session_id, hall_id, start_s in conn.execute(
            text("SELECT id, hall_id, start_time FROM sessions")
        ):
            hall = hall_by_id[hall_id]
            start = datetime.strptime(start_s, DT_FORMAT)
            rate = rng.uniform(0.1, 0.7)
            if start.hour >= 17:
                rate += 0.15
            if start.weekday() >= 5:
                rate += 0.1
            if start > now:
                rate *= max(0.1, 1 - (start - now).days / DAYS_FORWARD) * 0.6
            seats = [
                (r, s)
                for r in range(1, hall.rows_count + 1)
                for s in range(1, hall.seats_per_row + 1)
            ]
            for row_num, seat_num in rng.sample(
                seats, round(len(seats) * min(rate, 1.0))
            ):
                sold_at = min(start - timedelta(hours=rng.uniform(0.2, 96)), now)
                tickets.append(
                    {
                        "session_id": session_id,
                        "customer_id": rng.choice(customer_ids)
                        if rng.random() < 0.4
                        else None,
                        "row": row_num,
                        "seat": seat_num,
                        "sold_at": sold_at.strftime(DT_FORMAT),
                        "status": "refunded" if rng.random() < 0.03 else "sold",
                    }
                )
        conn.execute(
            text(
                "INSERT INTO tickets (session_id, customer_id, row_num, seat_num, price, sold_at, status) "
                "VALUES (:session_id, :customer_id, :row, :seat, NULL, :sold_at, :status)"
            ),
            tickets,
        )
        # Часть билетов продана по льготному тарифу (−30%).
        conn.execute(
            text("UPDATE tickets SET price = ROUND(price * 0.7, 2) WHERE id % 7 = 0")
        )
        # Начальная загрузка — не пользовательские изменения, в журнале она не нужна.
        conn.execute(text("DELETE FROM audit_log"))

    from cinema.db.olap import refresh_warehouse

    refresh_warehouse()
