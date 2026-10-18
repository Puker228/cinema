"""Сеансы: расписание с фильтрами по залу и дате."""

from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDateEdit, QLabel, QPushButton

from cinema.db import procedures
from cinema.db.models import FilmSession
from cinema.ui.common import fetch
from cinema.ui.crud import CrudTab, Field, FormDialog, ref_choices


def _next_hour() -> datetime:
    return (datetime.now() + timedelta(hours=1)).replace(
        minute=0, second=0, microsecond=0
    )


class SessionsTab(CrudTab):
    def __init__(self) -> None:
        super().__init__(
            FilmSession,
            "Сеанс",
            [
                Field(
                    "film_id",
                    "Фильм",
                    "ref",
                    ref_choices(
                        "SELECT title || ' (' || release_year || ')', id FROM films ORDER BY title"
                    ),
                ),
                Field(
                    "hall_id",
                    "Зал",
                    "ref",
                    ref_choices(
                        "SELECT name || ' [' || hall_type || ']', id FROM halls ORDER BY name"
                    ),
                ),
                Field("start_time", "Начало", "datetime"),
                Field(
                    "base_price",
                    "Базовая цена, ₽",
                    "float",
                    maximum=100_000,
                    default=400,
                ),
            ],
            "",
            [
                "№",
                "Начало",
                "Окончание",
                "Фильм",
                "Возраст",
                "Зал",
                "Тип",
                "Цена, ₽",
                "Продано",
                "Мест",
                "Выручка, ₽",
            ],
        )
        self.hall_filter = QComboBox()
        self.date_filter = QDateEdit(QDate.currentDate())
        self.date_filter.setCalendarPopup(True)
        self.all_dates = QCheckBox("все даты")
        clone_button = QPushButton("Копировать на…")
        self.toolbar.insertWidget(3, clone_button)
        for w in (
            QLabel("Зал:"),
            self.hall_filter,
            QLabel("Дата:"),
            self.date_filter,
            self.all_dates,
        ):
            self.filters.addWidget(w)

        self.hall_filter.currentIndexChanged.connect(self.refresh)
        self.date_filter.dateChanged.connect(self.refresh)
        self.all_dates.toggled.connect(self.refresh)
        clone_button.clicked.connect(self.on_clone)

    def refresh(self) -> None:
        # Список залов мог измениться на другой вкладке.
        current = self.hall_filter.currentData()
        self.hall_filter.blockSignals(True)
        self.hall_filter.clear()
        self.hall_filter.addItem("Все", None)
        for name, hall_id in fetch("SELECT name, id FROM halls ORDER BY name")[1]:
            self.hall_filter.addItem(name, hall_id)
        self.hall_filter.setCurrentIndex(max(0, self.hall_filter.findData(current)))
        self.hall_filter.blockSignals(False)
        self.date_filter.setEnabled(not self.all_dates.isChecked())
        super().refresh()

    def query(self) -> tuple[str, dict]:
        where, params = [], {}
        if self.hall_filter.currentData() is not None:
            where.append("hall_id = :hall_id")
            params["hall_id"] = self.hall_filter.currentData()
        if not self.all_dates.isChecked():
            where.append("date(start_time) = :day")
            params["day"] = self.date_filter.date().toString("yyyy-MM-dd")
        sql = f"""SELECT session_id, substr(start_time, 1, 16), substr(end_time, 1, 16), title, age_rating, hall, hall_type,
                         base_price, sold, capacity, revenue
                  FROM v_session_info
                  {"WHERE " + " AND ".join(where) if where else ""}
                  ORDER BY start_time, hall"""
        return sql, params

    def on_add(self) -> None:
        self.fields[2].default = datetime.combine(
            self.date_filter.date().toPyDate(), _next_hour().time()
        )
        super().on_add()

    def on_clone(self) -> None:
        session_id = self.selected_id()
        if session_id is None:
            return
        dialog = FormDialog(
            self,
            "Копирование сеанса",
            [
                Field(
                    "start_time", "Новое время начала", "datetime", default=_next_hour()
                )
            ],
        )
        if dialog.exec():
            new_start = dialog.values()["start_time"]
            self.run_db(lambda: procedures.clone_session(session_id, new_start))
