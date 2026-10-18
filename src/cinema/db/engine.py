"""Подключение к SQLite: движок, фабрика сессий, пользовательские SQL-функции."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = Path(os.environ.get("CINEMA_DB", PROJECT_ROOT / "cinema.db"))

# Единый формат хранения даты-времени: удобен и для ORM, и для функций datetime() в SQL.
DT_FORMAT = "%Y-%m-%d %H:%M:%S"

engine = create_engine(f"sqlite:///{DB_PATH}")
Session = sessionmaker(engine, expire_on_commit=False)


def now_str() -> str:
    return datetime.now().strftime(DT_FORMAT)


def _occupancy(sold: int | None, capacity: int | None) -> float:
    """occupancy(sold, capacity) — процент заполнения зала."""
    if not capacity:
        return 0.0
    return round(100.0 * (sold or 0) / capacity, 1)


def _end_time(start: str | None, minutes: int | None) -> str | None:
    """end_time(start, minutes) — время окончания сеанса."""
    if start is None or minutes is None:
        return None
    return (datetime.strptime(start, DT_FORMAT) + timedelta(minutes=minutes)).strftime(
        DT_FORMAT
    )


def _price_multiplier(hall_type: str | None) -> float:
    """price_multiplier(hall_type) — наценка за формат зала."""
    return {"IMAX": 1.5, "3D": 1.2}.get(hall_type or "", 1.0)


@event.listens_for(engine, "connect")
def _on_connect(dbapi_conn, _record) -> None:
    dbapi_conn.execute("PRAGMA foreign_keys = ON")
    dbapi_conn.create_function("occupancy", 2, _occupancy, deterministic=True)
    dbapi_conn.create_function("end_time", 2, _end_time, deterministic=True)
    dbapi_conn.create_function(
        "price_multiplier", 1, _price_multiplier, deterministic=True
    )
