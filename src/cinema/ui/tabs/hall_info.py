"""Информация по конкретному залу: статистика за период, сеансы на дату, схема заполнения."""

from __future__ import annotations

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from cinema.db import procedures
from cinema.ui.common import fetch, make_table, selected_value, set_table_data
from cinema.ui.seat_map import SeatMap


def _date_edit(date: QDate) -> QDateEdit:
    edit = QDateEdit(date)
    edit.setCalendarPopup(True)
    return edit


class HallInfoTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.hall = QComboBox()
        self.hall.setMinimumWidth(200)
        self.card = QLabel()
        top = QHBoxLayout()
        top.addWidget(QLabel("Зал:"))
        top.addWidget(self.hall)
        top.addSpacing(20)
        top.addWidget(self.card, 1)

        # Левая часть — статистика за период (процедура hall_report).
        self.date_from = _date_edit(QDate.currentDate().addDays(-30))
        self.date_to = _date_edit(QDate.currentDate())
        period = QHBoxLayout()
        period.addWidget(QLabel("с"))
        period.addWidget(self.date_from)
        period.addWidget(QLabel("по"))
        period.addWidget(self.date_to)
        period.addStretch()
        self.stats = {
            key: QLabel()
            for key in ("sessions_count", "tickets_sold", "revenue", "occupancy")
        }
        stats_form = QFormLayout()
        stats_form.addRow("Сеансов:", self.stats["sessions_count"])
        stats_form.addRow("Продано билетов:", self.stats["tickets_sold"])
        stats_form.addRow("Выручка:", self.stats["revenue"])
        stats_form.addRow("Средняя заполняемость:", self.stats["occupancy"])
        self.films = make_table()
        stats_box = QGroupBox("Статистика за период")
        stats_layout = QVBoxLayout(stats_box)
        stats_layout.addLayout(period)
        stats_layout.addLayout(stats_form)
        stats_layout.addWidget(QLabel("Фильмы в зале за период:"))
        stats_layout.addWidget(self.films)

        # Правая часть — сеансы на выбранную дату и схема зала.
        self.day = _date_edit(QDate.currentDate())
        self.sessions = make_table()
        self.seat_map = SeatMap(selectable=False)
        self.occupancy = QLabel()
        day_row = QHBoxLayout()
        day_row.addWidget(QLabel("Дата:"))
        day_row.addWidget(self.day)
        day_row.addStretch()
        sessions_box = QGroupBox("Сеансы на дату")
        sessions_layout = QVBoxLayout(sessions_box)
        sessions_layout.addLayout(day_row)
        sessions_layout.addWidget(self.sessions, 1)
        sessions_layout.addWidget(self.occupancy)
        sessions_layout.addWidget(self.seat_map, 2)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(stats_box)
        splitter.addWidget(sessions_box)
        splitter.setSizes([420, 680])

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(splitter, 1)

        self.hall.currentIndexChanged.connect(self.load_hall)
        self.date_from.dateChanged.connect(self.load_stats)
        self.date_to.dateChanged.connect(self.load_stats)
        self.day.dateChanged.connect(self.load_sessions)
        set_table_data(
            self.sessions, [], []
        )  # создаёт модель, чтобы подписаться на выбор строки
        self.sessions.selectionModel().selectionChanged.connect(self.load_seats)

    def refresh(self) -> None:
        current = self.hall.currentData()
        self.hall.blockSignals(True)
        self.hall.clear()
        for name, hall_id in fetch("SELECT name, id FROM halls ORDER BY name")[1]:
            self.hall.addItem(name, hall_id)
        self.hall.setCurrentIndex(max(0, self.hall.findData(current)))
        self.hall.blockSignals(False)
        self.load_hall()

    def load_hall(self) -> None:
        hall_id = self.hall.currentData()
        if hall_id is None:
            self.card.setText("Залов нет")
            return
        _, rows = fetch(
            "SELECT h.hall_type, h.rows_count, h.seats_per_row, v.sessions_count, v.tickets_sold, v.revenue, "
            "v.avg_occupancy FROM halls h JOIN v_hall_stats v ON v.hall_id = h.id WHERE h.id = :id",
            {"id": hall_id},
        )
        hall_type, rows_count, seats, sessions, sold, revenue, occupancy = rows[0]
        self.card.setText(
            f"<b>{self.hall.currentText()}</b> — {hall_type}, {rows_count} рядов × {seats} мест = "
            f"{rows_count * seats} мест. За всё время: {sessions} сеансов, {sold} билетов, "
            f"{f'{revenue:,.0f}'.replace(',', ' ')} ₽, заполняемость {occupancy or 0}%"
        )
        self.load_stats()
        self.load_sessions()

    def load_stats(self) -> None:
        hall_id = self.hall.currentData()
        if hall_id is None:
            return
        report = procedures.hall_report(
            hall_id, self.date_from.date().toPyDate(), self.date_to.date().toPyDate()
        )
        self.stats["sessions_count"].setText(str(report["sessions_count"]))
        self.stats["tickets_sold"].setText(str(report["tickets_sold"]))
        self.stats["revenue"].setText(f"{report['revenue']:,.2f} ₽".replace(",", " "))
        self.stats["occupancy"].setText(f"{report['occupancy']}%")
        set_table_data(
            self.films,
            ["Фильм", "Сеансов", "Билетов", "Выручка, ₽", "Заполн., %"],
            report["films"],
        )

    def load_sessions(self) -> None:
        hall_id = self.hall.currentData()
        if hall_id is None:
            return
        _, rows = fetch(
            """SELECT session_id, strftime('%H:%M', start_time), strftime('%H:%M', end_time), title, age_rating,
                      base_price, sold, capacity, occupancy(sold, capacity), revenue
               FROM v_session_info
               WHERE hall_id = :hall_id AND date(start_time) = :day
               ORDER BY start_time""",
            {"hall_id": hall_id, "day": self.day.date().toString("yyyy-MM-dd")},
        )
        set_table_data(
            self.sessions,
            [
                "№",
                "Начало",
                "Конец",
                "Фильм",
                "Возраст",
                "Цена, ₽",
                "Продано",
                "Мест",
                "Заполн., %",
                "Выручка, ₽",
            ],
            rows,
        )
        self.seat_map.clear(
            "Выберите сеанс в таблице" if rows else "В этот день сеансов нет"
        )
        self.occupancy.clear()
        if rows:
            self.sessions.selectRow(0)

    def load_seats(self) -> None:
        session_id = selected_value(self.sessions)
        if session_id is None:
            return
        _, info = fetch(
            "SELECT h.rows_count, h.seats_per_row, v.sold, v.capacity, v.title, v.start_time "
            "FROM v_session_info v JOIN halls h ON h.id = v.hall_id WHERE v.session_id = :id",
            {"id": session_id},
        )
        rows, seats, sold, capacity, title, start = info[0]
        _, taken = fetch(
            "SELECT row_num, seat_num FROM tickets WHERE session_id = :id AND status = 'sold'",
            {"id": session_id},
        )
        self.seat_map.set_hall(rows, seats, {tuple(t) for t in taken})
        self.occupancy.setText(
            f"<b>{title}</b>, {start}: продано {sold} из {capacity} ({100 * sold / capacity:.1f}%), "
            f"свободно {capacity - sold}"
        )
