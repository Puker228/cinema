"""Реляционная модель базы данных кинотеатра (ORM SQLAlchemy)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.sqlite import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DateTime = DATETIME(
    storage_format="%(year)04d-%(month)02d-%(day)02d %(hour)02d:%(minute)02d:%(second)02d",
    regexp=r"(\d+)-(\d+)-(\d+) (\d+):(\d+):(\d+)",
)

HALL_TYPES = ("2D", "3D", "IMAX")
AGE_RATINGS = ("0+", "6+", "12+", "16+", "18+")
TICKET_STATUSES = ("sold", "refunded")


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------- операционные таблицы


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)


class Film(Base):
    __tablename__ = "films"
    __table_args__ = (
        UniqueConstraint("title", "release_year", name="uq_film_title_year"),
        CheckConstraint("duration_min > 0", name="ck_film_duration"),
        CheckConstraint("release_year BETWEEN 1895 AND 2100", name="ck_film_year"),
        CheckConstraint(f"age_rating IN {AGE_RATINGS}", name="ck_film_age"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    genre_id: Mapped[int] = mapped_column(ForeignKey("genres.id", ondelete="RESTRICT"))
    duration_min: Mapped[int]
    age_rating: Mapped[str] = mapped_column(String(3))
    release_year: Mapped[int]
    description: Mapped[str] = mapped_column(Text, default="")


class Hall(Base):
    __tablename__ = "halls"
    __table_args__ = (
        CheckConstraint("rows_count BETWEEN 1 AND 50", name="ck_hall_rows"),
        CheckConstraint("seats_per_row BETWEEN 1 AND 60", name="ck_hall_seats"),
        CheckConstraint(f"hall_type IN {HALL_TYPES}", name="ck_hall_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    rows_count: Mapped[int]
    seats_per_row: Mapped[int]
    hall_type: Mapped[str] = mapped_column(String(10))


class FilmSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("base_price >= 0", name="ck_session_price"),
        Index("ix_sessions_hall_start", "hall_id", "start_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    film_id: Mapped[int] = mapped_column(ForeignKey("films.id", ondelete="RESTRICT"))
    hall_id: Mapped[int] = mapped_column(ForeignKey("halls.id", ondelete="RESTRICT"))
    start_time: Mapped[datetime] = mapped_column(DateTime)
    base_price: Mapped[float]


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    email: Mapped[str | None] = mapped_column(String(100))


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("price IS NULL OR price >= 0", name="ck_ticket_price"),
        CheckConstraint(f"status IN {TICKET_STATUSES}", name="ck_ticket_status"),
        # Место может быть продано только один раз; возвращённые билеты место не занимают.
        Index(
            "ux_tickets_sold_seat",
            "session_id",
            "row_num",
            "seat_num",
            unique=True,
            sqlite_where=text("status = 'sold'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE")
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL")
    )
    row_num: Mapped[int]
    seat_num: Mapped[int]
    price: Mapped[float | None]
    sold_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(10), default="sold")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    table_name: Mapped[str] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(10))
    record_id: Mapped[int]
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(
        String(19), server_default=text("(datetime('now', 'localtime'))")
    )


# ---------------------------------------------------------------- хранилище (звезда)


class DimDate(Base):
    __tablename__ = "dim_date"

    date_key: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=False
    )  # YYYYMMDD
    full_date: Mapped[str] = mapped_column(String(10))
    day: Mapped[int]
    month: Mapped[int]
    month_name: Mapped[str] = mapped_column(String(20))
    quarter: Mapped[int]
    year: Mapped[int]
    weekday: Mapped[int]  # 1 = понедельник
    weekday_name: Mapped[str] = mapped_column(String(5))


class DimFilm(Base):
    __tablename__ = "dim_film"

    film_key: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(200))
    genre: Mapped[str] = mapped_column(String(50))
    age_rating: Mapped[str] = mapped_column(String(3))
    release_year: Mapped[int]


class DimHall(Base):
    __tablename__ = "dim_hall"

    hall_key: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(50))
    hall_type: Mapped[str] = mapped_column(String(10))
    capacity: Mapped[int]


class FactSales(Base):
    """Факт продаж; зерно — один сеанс."""

    __tablename__ = "fact_sales"

    session_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    date_key: Mapped[int] = mapped_column(ForeignKey("dim_date.date_key"))
    film_key: Mapped[int] = mapped_column(ForeignKey("dim_film.film_key"))
    hall_key: Mapped[int] = mapped_column(ForeignKey("dim_hall.hall_key"))
    start_hour: Mapped[int]
    tickets_count: Mapped[int]
    revenue: Mapped[float]
    capacity: Mapped[int]
