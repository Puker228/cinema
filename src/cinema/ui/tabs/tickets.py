"""Билеты: продажа через схему зала, возврат, редактирование."""

from __future__ import annotations

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cinema.db import procedures
from cinema.db.engine import now_str
from cinema.db.models import TICKET_STATUSES, Ticket
from cinema.ui.common import confirm, fetch
from cinema.ui.crud import CrudTab, Field, ref_choices
from cinema.ui.seat_map import SeatMap

_SESSIONS_ON_DAY = """
    SELECT strftime('%H:%M', start_time) || '  ' || title || '  [' || hall || ']  ' || sold || '/' || capacity,
           session_id
    FROM v_session_info
    WHERE date(start_time) = :day {extra}
    ORDER BY start_time, hall
"""


def fill_sessions_combo(
    combo: QComboBox, day: QDate, future_only: bool, with_all: bool
) -> None:
    current = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    if with_all:
        combo.addItem("Все сеансы дня", None)
    extra = "AND start_time > :now" if future_only else ""
    _, rows = fetch(
        _SESSIONS_ON_DAY.format(extra=extra),
        {"day": day.toString("yyyy-MM-dd"), "now": now_str()},
    )
    for label, session_id in rows:
        combo.addItem(label, session_id)
    combo.setCurrentIndex(max(0, combo.findData(current)))
    combo.blockSignals(False)


class SellTicketsDialog(QDialog):
    def __init__(self, parent: QWidget, session_id: int | None = None):
        super().__init__(parent)
        self.setWindowTitle("Продажа билетов")
        self.resize(760, 560)

        self.day = QDateEdit(QDate.currentDate())
        self.day.setCalendarPopup(True)
        self.session = QComboBox()
        self.session.setMinimumWidth(380)
        self.seats = SeatMap(selectable=True)
        self.customer = QComboBox()
        self.customer.addItem("— без покупателя —", None)
        for label, customer_id in ref_choices(
            "SELECT full_name || ' ' || COALESCE(phone, ''), id FROM customers ORDER BY full_name"
        )():
            self.customer.addItem(label, customer_id)
        self.price = QDoubleSpinBox()
        self.price.setRange(0, 100_000)
        self.price.setDecimals(2)
        self.price.setSpecialValueText("по тарифу")  # 0 => цену рассчитает триггер
        self.summary = QLabel()

        if session_id is not None:
            start = fetch(
                "SELECT date(start_time) FROM sessions WHERE id = :id",
                {"id": session_id},
            )[1][0][0]
            self.day.setDate(QDate.fromString(start, "yyyy-MM-dd"))

        top = QHBoxLayout()
        top.addWidget(QLabel("Дата:"))
        top.addWidget(self.day)
        top.addWidget(QLabel("Сеанс:"))
        top.addWidget(self.session, 1)
        form = QFormLayout()
        form.addRow("Покупатель:", self.customer)
        form.addRow("Цена за билет:", self.price)
        buttons = QDialogButtonBox()
        self.sell_button = buttons.addButton(
            "Продать", QDialogButtonBox.ButtonRole.AcceptRole
        )
        buttons.addButton("Отмена", QDialogButtonBox.ButtonRole.RejectRole)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.seats, 1)
        layout.addLayout(form)
        layout.addWidget(self.summary)
        layout.addWidget(buttons)

        self.day.dateChanged.connect(self.load_sessions)
        self.session.currentIndexChanged.connect(self.load_seats)
        self.seats.selectionChanged.connect(self.update_summary)
        self.price.valueChanged.connect(self.update_summary)
        buttons.accepted.connect(self.sell)
        buttons.rejected.connect(self.reject)

        self.load_sessions()
        if session_id is not None:
            self.session.setCurrentIndex(max(0, self.session.findData(session_id)))

    def load_sessions(self) -> None:
        fill_sessions_combo(
            self.session, self.day.date(), future_only=True, with_all=False
        )
        self.load_seats()

    def load_seats(self) -> None:
        session_id = self.session.currentData()
        if session_id is None:
            self.seats.clear("На эту дату нет сеансов, на которые идёт продажа")
            self.tariff = 0.0
        else:
            _, info = fetch(
                """SELECT h.rows_count, h.seats_per_row,
                          ROUND(s.base_price * price_multiplier(h.hall_type), 2)
                   FROM sessions s JOIN halls h ON h.id = s.hall_id WHERE s.id = :id""",
                {"id": session_id},
            )
            rows, seats, self.tariff = info[0]
            _, sold = fetch(
                "SELECT row_num, seat_num FROM tickets WHERE session_id = :id AND status = 'sold'",
                {"id": session_id},
            )
            self.seats.set_hall(rows, seats, {tuple(s) for s in sold})
        self.update_summary()

    def update_summary(self) -> None:
        selected = self.seats.selected()
        price = self.price.value() or self.tariff
        places = ", ".join(f"{r}-{s}" for r, s in selected) or "—"
        self.summary.setText(
            f"Тариф: {self.tariff:.2f} ₽.  Выбрано мест: {len(selected)} ({places}).  "
            f"Итого: <b>{price * len(selected):.2f} ₽</b>"
        )
        self.sell_button.setEnabled(bool(selected))

    def sell(self) -> None:
        try:
            ids = procedures.sell_tickets(
                self.session.currentData(),
                self.seats.selected(),
                self.customer.currentData(),
                self.price.value() or None,
            )
        except procedures.ProcedureError as exc:
            QMessageBox.warning(self, "Продажа невозможна", str(exc))
            self.load_seats()
            return
        QMessageBox.information(
            self,
            "Продажа",
            f"Продано билетов: {len(ids)} (№ {', '.join(map(str, ids))})",
        )
        self.accept()


class TicketsTab(CrudTab):
    def __init__(self) -> None:
        super().__init__(
            Ticket,
            "Билет",
            [
                Field(
                    "customer_id",
                    "Покупатель",
                    "ref",
                    ref_choices(
                        "SELECT full_name || ' ' || COALESCE(phone, ''), id FROM customers ORDER BY full_name"
                    ),
                    required=False,
                ),
                Field("row_num", "Ряд", "int", minimum=1, maximum=50),
                Field("seat_num", "Место", "int", minimum=1, maximum=60),
                Field("price", "Цена, ₽", "float", maximum=100_000),
                Field("status", "Статус", "choice", TICKET_STATUSES),
            ],
            "",
            [
                "№",
                "Сеанс",
                "Фильм",
                "Зал",
                "Ряд",
                "Место",
                "Цена, ₽",
                "Статус",
                "Покупатель",
                "Продан",
            ],
        )
        self.add_button.setText("Продать…")
        refund_button = QPushButton("Возврат")
        self.toolbar.insertWidget(3, refund_button)
        refund_button.clicked.connect(self.on_refund)

        self.day = QDateEdit(QDate.currentDate())
        self.day.setCalendarPopup(True)
        self.session = QComboBox()
        self.session.setMinimumWidth(320)
        self.status = QComboBox()
        self.status.addItem("Все", None)
        self.status.addItem("Проданные", "sold")
        self.status.addItem("Возвращённые", "refunded")
        for w in (
            QLabel("Дата:"),
            self.day,
            QLabel("Сеанс:"),
            self.session,
            self.status,
        ):
            self.filters.addWidget(w)

        self.day.dateChanged.connect(self.refresh)
        self.session.currentIndexChanged.connect(self.refresh)
        self.status.currentIndexChanged.connect(self.refresh)

    def refresh(self) -> None:
        fill_sessions_combo(
            self.session, self.day.date(), future_only=False, with_all=True
        )
        super().refresh()

    def query(self) -> tuple[str, dict]:
        where = ["date(s.start_time) = :day"]
        params = {"day": self.day.date().toString("yyyy-MM-dd")}
        if self.session.currentData() is not None:
            where.append("t.session_id = :session_id")
            params["session_id"] = self.session.currentData()
        if self.status.currentData() is not None:
            where.append("t.status = :status")
            params["status"] = self.status.currentData()
        sql = f"""SELECT t.id, substr(s.start_time, 1, 16), f.title, h.name, t.row_num, t.seat_num, t.price,
                         CASE t.status WHEN 'sold' THEN 'продан' ELSE 'возврат' END, c.full_name, substr(t.sold_at, 1, 16)
                  FROM tickets t
                  JOIN sessions s ON s.id = t.session_id
                  JOIN films f ON f.id = s.film_id
                  JOIN halls h ON h.id = s.hall_id
                  LEFT JOIN customers c ON c.id = t.customer_id
                  WHERE {" AND ".join(where)}
                  ORDER BY s.start_time, h.name, t.row_num, t.seat_num"""
        return sql, params

    def on_add(self) -> None:
        if SellTicketsDialog(self, self.session.currentData()).exec():
            self.refresh()

    def on_refund(self) -> None:
        ticket_id = self.selected_id()
        if ticket_id is not None and confirm(
            self, f"Оформить возврат билета №{ticket_id}?"
        ):
            self.run_db(lambda: procedures.cancel_ticket(ticket_id))
