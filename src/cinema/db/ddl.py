"""Серверная логика в SQLite: триггеры и представления."""

from __future__ import annotations

# Перерыв на уборку зала между сеансами, минут.
CLEANING_MIN = 15

_OVERLAP_CHECK = f"""
    SELECT RAISE(ABORT, 'Сеанс пересекается с другим сеансом в этом зале (с учётом {CLEANING_MIN} мин уборки)')
    WHERE EXISTS (
        SELECT 1
        FROM sessions s
        JOIN films f ON f.id = s.film_id
        WHERE s.hall_id = NEW.hall_id
          AND s.id IS NOT NEW.id
          AND datetime(NEW.start_time) <
              datetime(s.start_time, '+' || (f.duration_min + {CLEANING_MIN}) || ' minutes')
          AND datetime(s.start_time) <
              datetime(NEW.start_time, '+' || ((SELECT duration_min FROM films WHERE id = NEW.film_id)
                                               + {CLEANING_MIN}) || ' minutes')
    );
"""

_SEAT_CHECK = """
    SELECT RAISE(ABORT, 'Место находится вне границ зала')
    WHERE NEW.row_num < 1 OR NEW.seat_num < 1 OR EXISTS (
        SELECT 1
        FROM sessions s
        JOIN halls h ON h.id = s.hall_id
        WHERE s.id = NEW.session_id
          AND (NEW.row_num > h.rows_count OR NEW.seat_num > h.seats_per_row)
    );
"""

TRIGGERS: list[str] = [
    # 1. Сеансы в одном зале не должны пересекаться по времени.
    f"""
    CREATE TRIGGER IF NOT EXISTS trg_session_no_overlap_ins
    BEFORE INSERT ON sessions
    BEGIN {_OVERLAP_CHECK} END;
    """,
    f"""
    CREATE TRIGGER IF NOT EXISTS trg_session_no_overlap_upd
    BEFORE UPDATE OF film_id, hall_id, start_time ON sessions
    BEGIN {_OVERLAP_CHECK} END;
    """,
    # 2. Ряд и место билета должны существовать в зале сеанса.
    f"""
    CREATE TRIGGER IF NOT EXISTS trg_ticket_seat_valid_ins
    BEFORE INSERT ON tickets
    BEGIN {_SEAT_CHECK} END;
    """,
    f"""
    CREATE TRIGGER IF NOT EXISTS trg_ticket_seat_valid_upd
    BEFORE UPDATE OF session_id, row_num, seat_num ON tickets
    BEGIN {_SEAT_CHECK} END;
    """,
    # 3. Цена билета по умолчанию = базовая цена сеанса с наценкой за формат зала.
    """
    CREATE TRIGGER IF NOT EXISTS trg_ticket_default_price
    AFTER INSERT ON tickets
    WHEN NEW.price IS NULL
    BEGIN
        UPDATE tickets
        SET price = (
            SELECT round(s.base_price * CASE h.hall_type WHEN 'IMAX' THEN 1.5
                                                         WHEN '3D' THEN 1.2
                                                         ELSE 1.0 END, 2)
            FROM sessions s JOIN halls h ON h.id = s.hall_id
            WHERE s.id = NEW.session_id
        )
        WHERE id = NEW.id;
    END;
    """,
    # 4. Нельзя удалить будущий сеанс, на который уже проданы билеты.
    """
    CREATE TRIGGER IF NOT EXISTS trg_session_delete_guard
    BEFORE DELETE ON sessions
    WHEN datetime(OLD.start_time) > datetime('now', 'localtime')
     AND EXISTS (SELECT 1 FROM tickets WHERE session_id = OLD.id AND status = 'sold')
    BEGIN
        SELECT RAISE(ABORT, 'Нельзя удалить будущий сеанс с проданными билетами — сначала оформите возвраты');
    END;
    """,
    # 5. Нельзя уменьшить зал так, что проданные места окажутся за его границами.
    """
    CREATE TRIGGER IF NOT EXISTS trg_hall_resize_guard
    BEFORE UPDATE OF rows_count, seats_per_row ON halls
    BEGIN
        SELECT RAISE(ABORT, 'Нельзя уменьшить зал: есть проданные билеты на исчезающие места')
        WHERE EXISTS (
            SELECT 1 FROM tickets t JOIN sessions s ON s.id = t.session_id
            WHERE s.hall_id = NEW.id AND t.status = 'sold'
              AND (t.row_num > NEW.rows_count OR t.seat_num > NEW.seats_per_row)
        );
    END;
    """,
]

# 6. Журнал аудита изменений: таблица -> (выражение-описание, доп. условие для UPDATE).
_AUDITED = {
    "films": ("{r}.title || ' (' || {r}.release_year || ')'", None),
    "sessions": (
        "'фильм ' || {r}.film_id || ', зал ' || {r}.hall_id || ', ' || {r}.start_time",
        None,
    ),
    "tickets": (
        (
            "'сеанс ' || {r}.session_id || ', ряд ' || {r}.row_num || ', место ' || {r}.seat_num"
            " || ', ' || {r}.status"
        ),
        # Не логируем автоматическую простановку цены триггером trg_ticket_default_price.
        "NOT (OLD.price IS NULL AND NEW.price IS NOT NULL)",
    ),
}

for _table, (_details, _upd_when) in _AUDITED.items():
    for _action, _row in (("INSERT", "NEW"), ("UPDATE", "NEW"), ("DELETE", "OLD")):
        _when = f"WHEN {_upd_when}" if _action == "UPDATE" and _upd_when else ""
        TRIGGERS.append(f"""
        CREATE TRIGGER IF NOT EXISTS trg_audit_{_table}_{_action.lower()}
        AFTER {_action} ON {_table}
        {_when}
        BEGIN
            INSERT INTO audit_log (table_name, action, record_id, details)
            VALUES ('{_table}', '{_action}', {_row}.id, {_details.format(r=_row)});
        END;
        """)

VIEWS: list[str] = [
    """
    CREATE VIEW IF NOT EXISTS v_session_info AS
    SELECT s.id AS session_id,
           s.start_time,
           datetime(s.start_time, '+' || f.duration_min || ' minutes') AS end_time,
           f.id AS film_id,
           f.title,
           f.age_rating,
           h.id AS hall_id,
           h.name AS hall,
           h.hall_type,
           s.base_price,
           h.rows_count * h.seats_per_row AS capacity,
           (SELECT COUNT(*) FROM tickets t WHERE t.session_id = s.id AND t.status = 'sold') AS sold,
           (SELECT COALESCE(SUM(t.price), 0) FROM tickets t
             WHERE t.session_id = s.id AND t.status = 'sold') AS revenue
    FROM sessions s
    JOIN films f ON f.id = s.film_id
    JOIN halls h ON h.id = s.hall_id;
    """,
    """
    CREATE VIEW IF NOT EXISTS v_hall_stats AS
    SELECT h.id AS hall_id,
           h.name,
           h.hall_type,
           h.rows_count * h.seats_per_row AS capacity,
           COUNT(DISTINCT s.id) AS sessions_count,
           COUNT(t.id) AS tickets_sold,
           COALESCE(SUM(t.price), 0) AS revenue,
           ROUND(100.0 * COUNT(t.id)
                 / NULLIF(COUNT(DISTINCT s.id) * h.rows_count * h.seats_per_row, 0), 1) AS avg_occupancy
    FROM halls h
    LEFT JOIN sessions s ON s.hall_id = h.id
    LEFT JOIN tickets t ON t.session_id = s.id AND t.status = 'sold'
    GROUP BY h.id;
    """,
]

VIEW_NAMES = ("v_session_info", "v_hall_stats")
