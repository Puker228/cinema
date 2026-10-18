"""Каталог запросов, демонстрирующих операции реляционной алгебры."""

from __future__ import annotations

from dataclasses import dataclass

SELECTION = "Селекция σ"
PROJECTION = "Проекция π"
UNION = "Объединение ∪"
INTERSECTION = "Пересечение ∩"
DIFFERENCE = "Разность −"
PRODUCT = "Декартово произведение ×"
JOIN = "Соединение ⋈"
AGGREGATION = "Группировка γ"

OPERATIONS = [
    SELECTION,
    PROJECTION,
    UNION,
    INTERSECTION,
    DIFFERENCE,
    PRODUCT,
    JOIN,
    AGGREGATION,
]


@dataclass(frozen=True)
class Query:
    title: str
    operations: tuple[str, ...]
    algebra: str
    sql: str


QUERIES: list[Query] = [
    # ------------------------------------------------------------------ селекция
    Query(
        "Длинные фильмы для взрослых",
        (SELECTION,),
        "σ age_rating ∈ {16+, 18+} ∧ duration_min > 120 (films)",
        """SELECT *
FROM films
WHERE age_rating IN ('16+', '18+') AND duration_min > 120
ORDER BY duration_min DESC""",
    ),
    Query(
        "Сеансы на сегодня",
        (SELECTION,),
        "σ date(start_time) = today (sessions)",
        """SELECT *
FROM sessions
WHERE date(start_time) = date('now', 'localtime')
ORDER BY hall_id, start_time""",
    ),
    Query(
        "Возвращённые билеты дороже 400 ₽",
        (SELECTION,),
        "σ status = 'refunded' ∧ price > 400 (tickets)",
        """SELECT *
FROM tickets
WHERE status = 'refunded' AND price > 400
ORDER BY price DESC""",
    ),
    # ------------------------------------------------------------------ проекция
    Query(
        "Типы залов",
        (PROJECTION,),
        "π hall_type (halls)",
        """SELECT DISTINCT hall_type
FROM halls""",
    ),
    Query(
        "Годы выпуска фильмов",
        (PROJECTION,),
        "π release_year (films)",
        """SELECT DISTINCT release_year
FROM films
ORDER BY release_year""",
    ),
    Query(
        "Контакты покупателей с почтой на mail.ru",
        (PROJECTION, SELECTION),
        "π full_name, phone (σ email LIKE '%@mail.ru' (customers))",
        """SELECT full_name, phone
FROM customers
WHERE email LIKE '%@mail.ru'
ORDER BY full_name""",
    ),
    Query(
        "Название и длительность фильмов (в часах)",
        (PROJECTION,),
        "π title, duration_min/60 (films)",
        """SELECT title,
       duration_min,
       printf('%d ч %02d мин', duration_min / 60, duration_min % 60) AS duration
FROM films
ORDER BY title""",
    ),
    # ------------------------------------------------------------------ объединение
    Query(
        "Единый справочник: фильмы, залы, жанры",
        (UNION, PROJECTION),
        "π 'Фильм', title (films) ∪ π 'Зал', name (halls) ∪ π 'Жанр', name (genres)",
        """SELECT 'Фильм' AS kind, title AS name FROM films
UNION
SELECT 'Зал', name FROM halls
UNION
SELECT 'Жанр', name FROM genres
ORDER BY kind, name""",
    ),
    Query(
        "Фильмы, шедшие в IMAX, или с рейтингом 18+",
        (UNION, JOIN, SELECTION),
        "π title (films ⋈ sessions ⋈ σ hall_type='IMAX' (halls)) ∪ π title (σ age_rating='18+' (films))",
        """SELECT f.title
FROM films f
JOIN sessions s ON s.film_id = f.id
JOIN halls h ON h.id = s.hall_id
WHERE h.hall_type = 'IMAX'
UNION
SELECT title FROM films WHERE age_rating = '18+'
ORDER BY title""",
    ),
    Query(
        "Активные покупатели: бывали в VIP или купили больше 30 билетов",
        (UNION, JOIN, AGGREGATION),
        "π customer (… σ hall='VIP' …) ∪ π customer (σ cnt > 30 (γ customer; count (tickets)))",
        """SELECT c.full_name
FROM customers c
JOIN tickets t ON t.customer_id = c.id
JOIN sessions s ON s.id = t.session_id
JOIN halls h ON h.id = s.hall_id
WHERE h.name = 'VIP' AND t.status = 'sold'
UNION
SELECT c.full_name
FROM customers c
JOIN tickets t ON t.customer_id = c.id
GROUP BY c.id
HAVING COUNT(*) > 30
ORDER BY 1""",
    ),
    # ------------------------------------------------------------------ пересечение
    Query(
        "Фильмы, которые шли и в IMAX, и в 2D-залах",
        (INTERSECTION, JOIN, SELECTION),
        "π title (… σ hall_type='IMAX' …) ∩ π title (… σ hall_type='2D' …)",
        """SELECT f.title FROM films f
JOIN sessions s ON s.film_id = f.id JOIN halls h ON h.id = s.hall_id
WHERE h.hall_type = 'IMAX'
INTERSECT
SELECT f.title FROM films f
JOIN sessions s ON s.film_id = f.id JOIN halls h ON h.id = s.hall_id
WHERE h.hall_type = '2D'""",
    ),
    Query(
        "Покупатели, смотревшие и комедии, и фантастику",
        (INTERSECTION, JOIN),
        "π full_name (… σ genre='Комедия' …) ∩ π full_name (… σ genre='Фантастика' …)",
        """SELECT c.full_name FROM customers c
JOIN tickets t ON t.customer_id = c.id JOIN sessions s ON s.id = t.session_id
JOIN films f ON f.id = s.film_id JOIN genres g ON g.id = f.genre_id
WHERE g.name = 'Комедия'
INTERSECT
SELECT c.full_name FROM customers c
JOIN tickets t ON t.customer_id = c.id JOIN sessions s ON s.id = t.session_id
JOIN films f ON f.id = s.film_id JOIN genres g ON g.id = f.genre_id
WHERE g.name = 'Фантастика'""",
    ),
    Query(
        "Дни, когда работали и VIP-зал, и IMAX после 22:00",
        (INTERSECTION, SELECTION, JOIN),
        "π date (σ hall='VIP' (…)) ∩ π date (σ hall='IMAX' ∧ hour ≥ 22 (…))",
        """SELECT date(s.start_time) AS day FROM sessions s JOIN halls h ON h.id = s.hall_id
WHERE h.name = 'VIP'
INTERSECT
SELECT date(s.start_time) FROM sessions s JOIN halls h ON h.id = s.hall_id
WHERE h.name = 'IMAX' AND time(s.start_time) >= '22:00:00'
ORDER BY day""",
    ),
    # ------------------------------------------------------------------ разность
    Query(
        "Фильмы без будущих сеансов",
        (DIFFERENCE, JOIN, SELECTION),
        "π id, title (films) − π id, title (films ⋈ σ start_time > now (sessions))",
        """SELECT id, title FROM films
EXCEPT
SELECT f.id, f.title FROM films f
JOIN sessions s ON s.film_id = f.id
WHERE s.start_time > datetime('now', 'localtime')""",
    ),
    Query(
        "Покупатели без купленных билетов",
        (DIFFERENCE, PROJECTION),
        "π id, full_name (customers) − π id, full_name (customers ⋈ tickets)",
        """SELECT id, full_name FROM customers
EXCEPT
SELECT c.id, c.full_name FROM customers c JOIN tickets t ON t.customer_id = c.id""",
    ),
    Query(
        "Свободные места на ближайший сеанс",
        (DIFFERENCE, PRODUCT),
        "(rows × seats) − π row_num, seat_num (σ session = ближайший ∧ status='sold' (tickets))",
        """WITH RECURSIVE
  target AS (
    SELECT s.id, h.rows_count, h.seats_per_row
    FROM sessions s JOIN halls h ON h.id = s.hall_id
    WHERE s.start_time > datetime('now', 'localtime')
    ORDER BY s.start_time LIMIT 1
  ),
  r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < (SELECT rows_count FROM target)),
  c(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM c WHERE n < (SELECT seats_per_row FROM target))
SELECT r.n AS row_num, c.n AS seat_num FROM r CROSS JOIN c
EXCEPT
SELECT row_num, seat_num FROM tickets
WHERE status = 'sold' AND session_id = (SELECT id FROM target)
ORDER BY 1, 2""",
    ),
    Query(
        "Залы, где не показывали детские фильмы (0+, 6+)",
        (DIFFERENCE, JOIN),
        "π name (halls) − π name (halls ⋈ sessions ⋈ σ age_rating ∈ {0+, 6+} (films))",
        """SELECT name FROM halls
EXCEPT
SELECT h.name FROM halls h
JOIN sessions s ON s.hall_id = h.id
JOIN films f ON f.id = s.film_id
WHERE f.age_rating IN ('0+', '6+')""",
    ),
    # ------------------------------------------------------------------ декартово произведение
    Query(
        "Матрица планирования: зал × жанр",
        (PRODUCT, PROJECTION),
        "π hall, genre (halls × genres)",
        """SELECT h.name AS hall, g.name AS genre
FROM halls h CROSS JOIN genres g
ORDER BY h.name, g.name""",
    ),
    Query(
        "Сетка мест VIP-зала",
        (PRODUCT,),
        "rows × seats",
        """WITH RECURSIVE
  hall AS (SELECT rows_count, seats_per_row FROM halls WHERE name = 'VIP'),
  r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < (SELECT rows_count FROM hall)),
  c(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM c WHERE n < (SELECT seats_per_row FROM hall))
SELECT r.n AS row_num, c.n AS seat_num
FROM r CROSS JOIN c""",
    ),
    Query(
        "Какие длинные фильмы можно поставить в IMAX (× + σ)",
        (PRODUCT, SELECTION),
        "σ hall_type='IMAX' ∧ duration_min > 150 (films × halls)",
        """SELECT f.title, f.duration_min, h.name AS hall
FROM films f, halls h
WHERE h.hall_type = 'IMAX' AND f.duration_min > 150""",
    ),
    # ------------------------------------------------------------------ соединение
    Query(
        "Расписание на ближайшую неделю (внутреннее соединение)",
        (JOIN, SELECTION, PROJECTION),
        "π start_time, title, hall (σ … (sessions ⋈ films ⋈ halls))",
        """SELECT s.start_time, f.title, f.age_rating, h.name AS hall, s.base_price
FROM sessions s
JOIN films f ON f.id = s.film_id
JOIN halls h ON h.id = s.hall_id
WHERE s.start_time BETWEEN datetime('now', 'localtime') AND datetime('now', 'localtime', '+7 days')
ORDER BY s.start_time""",
    ),
    Query(
        "Естественное соединение фильмов и их сеансов",
        (JOIN, PROJECTION),
        "π film_id, title (films) ⋈ π film_id, start_time (sessions)",
        """SELECT *
FROM (SELECT id AS film_id, title FROM films)
NATURAL JOIN (SELECT film_id, start_time FROM sessions)
ORDER BY start_time DESC
LIMIT 100""",
    ),
    Query(
        "Все фильмы и число их сеансов (левое внешнее соединение)",
        (JOIN, AGGREGATION),
        "films ⟕ sessions",
        """SELECT f.title, COUNT(s.id) AS sessions_count
FROM films f
LEFT JOIN sessions s ON s.film_id = f.id
GROUP BY f.id
ORDER BY sessions_count DESC""",
    ),
    Query(
        "Билеты дороже средней цены своего сеанса (θ-соединение)",
        (JOIN, AGGREGATION),
        "tickets ⋈ t.price > a.avg_price (γ session_id; avg(price) (tickets))",
        """SELECT t.id, t.session_id, t.row_num, t.seat_num, t.price, ROUND(a.avg_price, 2) AS avg_price
FROM tickets t
JOIN (SELECT session_id, AVG(price) AS avg_price FROM tickets GROUP BY session_id) a
  ON a.session_id = t.session_id AND t.price > a.avg_price
LIMIT 200""",
    ),
    # ------------------------------------------------------------------ группировка
    Query(
        "Выручка по фильмам",
        (AGGREGATION, JOIN),
        "γ title; count, sum(price) (films ⋈ sessions ⋈ σ status='sold' (tickets))",
        """SELECT f.title, COUNT(t.id) AS tickets, ROUND(SUM(t.price), 2) AS revenue
FROM films f
JOIN sessions s ON s.film_id = f.id
JOIN tickets t ON t.session_id = s.id AND t.status = 'sold'
GROUP BY f.id
ORDER BY revenue DESC""",
    ),
    Query(
        "Заполняемость залов (функция occupancy)",
        (AGGREGATION, JOIN),
        "γ hall; occupancy(sum(sold), sum(capacity)) (v_session_info)",
        """SELECT hall, hall_type, COUNT(*) AS sessions_count,
       SUM(sold) AS sold, occupancy(SUM(sold), SUM(capacity)) AS occupancy_pct
FROM v_session_info
WHERE start_time < datetime('now', 'localtime')
GROUP BY hall_id
ORDER BY occupancy_pct DESC""",
    ),
    Query(
        "Топ-10 покупателей",
        (AGGREGATION, JOIN),
        "γ customer; count, sum(price) (customers ⋈ σ status='sold' (tickets))",
        """SELECT c.full_name, c.phone, COUNT(*) AS tickets, ROUND(SUM(t.price), 2) AS spent
FROM customers c
JOIN tickets t ON t.customer_id = c.id AND t.status = 'sold'
GROUP BY c.id
ORDER BY spent DESC
LIMIT 10""",
    ),
]
