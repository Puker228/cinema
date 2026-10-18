"""«Хранимые процедуры».

В SQLite нет CREATE PROCEDURE, поэтому серверная логика, которую в серверных СУБД
оформляют процедурами, реализована здесь: каждая функция выполняется в одной
транзакции, а проверки целостности дополнительно обеспечиваются триггерами (ddl.py).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from cinema.db.engine import DT_FORMAT, engine, now_str
from cinema.db.errors import ProcedureError, describe_error


def sell_tickets(
    session_id: int,
    seats: Iterable[tuple[int, int]],
    customer_id: int | None = None,
    price: float | None = None,
) -> list[int]:
    """Продаёт несколько мест на сеанс (всё или ничего). Цена None — рассчитает триггер."""
    seats = list(seats)
    if not seats:
        raise ProcedureError("Не выбрано ни одного места")
    with engine.begin() as conn:
        start = conn.execute(
            text("SELECT start_time FROM sessions WHERE id = :id"), {"id": session_id}
        ).scalar()
        if start is None:
            raise ProcedureError(f"Сеанс №{session_id} не найден")
        if start <= now_str():
            raise ProcedureError("Нельзя продать билет на уже начавшийся сеанс")
        ids = []
        for row_num, seat_num in seats:
            try:
                result = conn.execute(
                    text(
                        "INSERT INTO tickets (session_id, customer_id, row_num, seat_num, price, sold_at, status) "
                        "VALUES (:session_id, :customer_id, :row, :seat, :price, :sold_at, 'sold')"
                    ),
                    {
                        "session_id": session_id,
                        "customer_id": customer_id,
                        "row": row_num,
                        "seat": seat_num,
                        "price": price,
                        "sold_at": now_str(),
                    },
                )
            except IntegrityError as exc:
                raise ProcedureError(
                    f"Ряд {row_num}, место {seat_num}: {describe_error(exc)}"
                ) from exc
            ids.append(result.lastrowid)
        return ids


def sell_ticket(
    session_id: int, row_num: int, seat_num: int, customer_id: int | None = None
) -> int:
    return sell_tickets(session_id, [(row_num, seat_num)], customer_id)[0]


def cancel_ticket(ticket_id: int) -> None:
    """Оформляет возврат билета до начала сеанса."""
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT t.status, s.start_time FROM tickets t JOIN sessions s ON s.id = t.session_id "
                "WHERE t.id = :id"
            ),
            {"id": ticket_id},
        ).one_or_none()
        if row is None:
            raise ProcedureError(f"Билет №{ticket_id} не найден")
        if row.status == "refunded":
            raise ProcedureError("Билет уже возвращён")
        if row.start_time <= now_str():
            raise ProcedureError("Сеанс уже начался — возврат невозможен")
        conn.execute(
            text("UPDATE tickets SET status = 'refunded' WHERE id = :id"),
            {"id": ticket_id},
        )


def clone_session(session_id: int, new_start: datetime) -> int:
    """Копирует сеанс (фильм, зал, цена) на другое время."""
    with engine.begin() as conn:
        try:
            result = conn.execute(
                text(
                    "INSERT INTO sessions (film_id, hall_id, start_time, base_price) "
                    "SELECT film_id, hall_id, :start, base_price FROM sessions WHERE id = :id"
                ),
                {"id": session_id, "start": new_start.strftime(DT_FORMAT)},
            )
        except IntegrityError as exc:
            raise ProcedureError(describe_error(exc)) from exc
        if result.rowcount == 0:
            raise ProcedureError(f"Сеанс №{session_id} не найден")
        return result.lastrowid


def hall_report(hall_id: int, date_from: date, date_to: date) -> dict:
    """Сводка по залу за период: сеансы, билеты, выручка, заполняемость, топ фильмов."""
    params = {
        "hall_id": hall_id,
        "from": date_from.isoformat(),
        "to": date_to.isoformat(),
    }
    with engine.connect() as conn:
        summary = conn.execute(
            text(
                """
                SELECT COUNT(*) AS sessions_count,
                       COALESCE(SUM(sold), 0) AS tickets_sold,
                       COALESCE(SUM(revenue), 0) AS revenue,
                       occupancy(SUM(sold), SUM(capacity)) AS occupancy
                FROM v_session_info
                WHERE hall_id = :hall_id AND date(start_time) BETWEEN :from AND :to
                """
            ),
            params,
        ).one()
        top_films = conn.execute(
            text(
                """
                SELECT title, COUNT(*) AS sessions_count, SUM(sold) AS tickets_sold,
                       ROUND(SUM(revenue), 2) AS revenue, occupancy(SUM(sold), SUM(capacity)) AS occupancy
                FROM v_session_info
                WHERE hall_id = :hall_id AND date(start_time) BETWEEN :from AND :to
                GROUP BY film_id
                ORDER BY revenue DESC
                """
            ),
            params,
        ).all()
    return {**summary._asdict(), "films": [tuple(r) for r in top_films]}


def film_revenue(date_from: date, date_to: date) -> list[tuple]:
    """Выручка и посещаемость по фильмам за период."""
    with engine.connect() as conn:
        return [
            tuple(r)
            for r in conn.execute(
                text(
                    """
                    SELECT title, COUNT(*) AS sessions_count, SUM(sold) AS tickets_sold,
                           ROUND(SUM(revenue), 2) AS revenue
                    FROM v_session_info
                    WHERE date(start_time) BETWEEN :from AND :to
                    GROUP BY film_id
                    ORDER BY revenue DESC
                    """
                ),
                {"from": date_from.isoformat(), "to": date_to.isoformat()},
            )
        ]
