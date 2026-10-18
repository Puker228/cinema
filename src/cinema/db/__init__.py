"""Слой доступа к данным."""

from __future__ import annotations

from sqlalchemy import select

from cinema.db import ddl
from cinema.db.engine import DB_PATH, Session, engine
from cinema.db.models import Base, Hall


def create_schema() -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for statement in ddl.TRIGGERS + ddl.VIEWS:
            conn.exec_driver_sql(statement)


def init_db() -> None:
    """Создаёт схему при первом запуске и заполняет её демо-данными."""
    create_schema()
    with Session() as session:
        empty = session.scalar(select(Hall.id).limit(1)) is None
    if empty:
        from cinema.db.seed import seed

        seed()


def reset_db(with_demo_data: bool = True) -> None:
    """Пересоздаёт файл БД с нуля."""
    engine.dispose()
    DB_PATH.unlink(missing_ok=True)
    create_schema()
    if with_demo_data:
        from cinema.db.seed import seed

        seed()
