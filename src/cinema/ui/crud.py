"""Универсальная вкладка «таблица + добавить/изменить/удалить» и форма редактирования."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from PyQt6.QtCore import QDate, QDateTime, QTime
from PyQt6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import SQLAlchemyError

from cinema.db.engine import Session
from cinema.db.errors import ProcedureError
from cinema.ui.common import (
    confirm,
    fetch,
    make_table,
    selected_value,
    set_table_data,
    show_error,
)

Choices = Sequence[str] | Callable[[], list[tuple[str, Any]]]


@dataclass
class Field:
    name: str
    label: str
    kind: str = "text"  # text | multiline | int | float | choice | ref | datetime
    choices: Choices | None = (
        None  # для choice — список строк, для ref — функция [(подпись, id)]
    )
    minimum: float = 0
    maximum: float = 1_000_000
    required: bool = True
    default: Any = None


def ref_choices(sql: str) -> Callable[[], list[tuple[str, Any]]]:
    """Варианты для поля-ссылки: SQL должен возвращать (подпись, id)."""
    return lambda: [tuple(r) for r in fetch(sql)[1]]


def to_qdatetime(value: datetime) -> QDateTime:
    return QDateTime(
        QDate(value.year, value.month, value.day), QTime(value.hour, value.minute)
    )


class FormDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        title: str,
        fields: list[Field],
        values: dict | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self.fields = fields
        self.widgets: dict[str, QWidget] = {}
        values = values or {}

        form = QFormLayout()
        for f in fields:
            value = values.get(f.name, f.default)
            widget = self._make_widget(f, value)
            self.widgets[f.name] = widget
            form.addRow(f.label + (" *" if f.required else ""), widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _make_widget(self, f: Field, value: Any) -> QWidget:
        if f.kind == "multiline":
            w = QPlainTextEdit(value or "")
            w.setFixedHeight(80)
        elif f.kind == "int":
            w = QSpinBox()
            w.setRange(int(f.minimum), int(f.maximum))
            w.setValue(int(value if value is not None else f.minimum))
        elif f.kind == "float":
            w = QDoubleSpinBox()
            w.setRange(f.minimum, f.maximum)
            w.setDecimals(2)
            w.setSingleStep(50)
            w.setValue(float(value or 0))
        elif f.kind in ("choice", "ref"):
            w = QComboBox()
            if f.kind == "choice":
                options = [(c, c) for c in f.choices]
            else:
                options = f.choices()
                if not f.required:
                    options = [("—", None), *options]
            for label, data in options:
                w.addItem(label, data)
            index = w.findData(value)
            if index >= 0:
                w.setCurrentIndex(index)
        elif f.kind == "datetime":
            w = QDateTimeEdit()
            w.setCalendarPopup(True)
            w.setDisplayFormat("dd.MM.yyyy HH:mm")
            w.setDateTime(to_qdatetime(value) if value else QDateTime.currentDateTime())
        else:
            w = QLineEdit("" if value is None else str(value))
        return w

    def values(self) -> dict[str, Any]:
        result = {}
        for f in self.fields:
            w = self.widgets[f.name]
            if isinstance(w, QPlainTextEdit):
                result[f.name] = w.toPlainText().strip()
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                result[f.name] = w.value()
            elif isinstance(w, QComboBox):
                result[f.name] = w.currentData()
            elif isinstance(w, QDateTimeEdit):
                result[f.name] = (
                    w.dateTime().toPyDateTime().replace(second=0, microsecond=0)
                )
            else:
                result[f.name] = w.text().strip() or None
        return result

    def _accept(self) -> None:
        values = self.values()
        missing = [
            f.label for f in self.fields if f.required and values[f.name] in (None, "")
        ]
        if missing:
            QMessageBox.warning(
                self, "Проверка", "Заполните поля: " + ", ".join(missing)
            )
            return
        self.accept()


class CrudTab(QWidget):
    """Список записей таблицы с поиском и операциями добавления, изменения и удаления.

    list_sql должен первым столбцом возвращать id записи.
    """

    def __init__(
        self,
        model_cls,
        entity_title: str,
        fields: list[Field],
        list_sql: str,
        headers: list[str],
    ):
        super().__init__()
        self.model_cls = model_cls
        self.entity_title = entity_title
        self.fields = fields
        self.list_sql = list_sql
        self.headers = headers

        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск…")
        self.search.setClearButtonEnabled(True)
        self.add_button = QPushButton("Добавить")
        self.edit_button = QPushButton("Изменить")
        self.delete_button = QPushButton("Удалить")
        refresh_button = QPushButton("Обновить")

        self.toolbar = QHBoxLayout()
        for b in (self.add_button, self.edit_button, self.delete_button):
            self.toolbar.addWidget(b)
        self.toolbar.addStretch()
        self.filters = QHBoxLayout()  # место для фильтров в наследниках
        self.toolbar.addLayout(self.filters)
        self.toolbar.addWidget(self.search, 1)
        self.toolbar.addWidget(refresh_button)

        self.table = make_table(self)
        layout = QVBoxLayout(self)
        layout.addLayout(self.toolbar)
        layout.addWidget(self.table)

        self.add_button.clicked.connect(self.on_add)
        self.edit_button.clicked.connect(self.on_edit)
        self.delete_button.clicked.connect(self.on_delete)
        refresh_button.clicked.connect(self.refresh)
        self.table.doubleClicked.connect(lambda _index: self.on_edit())
        self.search.textChanged.connect(
            lambda s: self.table.model().setFilterFixedString(s)
        )

    # --- данные

    def query(self) -> tuple[str, dict]:
        return self.list_sql, {}

    def refresh(self) -> None:
        sql, params = self.query()
        _, rows = fetch(sql, params)
        set_table_data(self.table, self.headers, rows)
        self.table.model().setFilterFixedString(self.search.text())

    def selected_id(self) -> int | None:
        record_id = selected_value(self.table)
        if record_id is None:
            QMessageBox.information(
                self, self.entity_title, "Выберите запись в таблице"
            )
        return record_id

    def run_db(self, action: Callable[[], Any]) -> bool:
        """Выполняет действие с БД, показывает ошибку (включая сообщения триггеров) и обновляет список."""
        try:
            action()
        except (SQLAlchemyError, ProcedureError) as exc:
            show_error(self, exc)
            return False
        self.refresh()
        return True

    # --- операции

    def on_add(self) -> None:
        dialog = FormDialog(self, f"{self.entity_title}: добавление", self.fields)
        if dialog.exec():

            def add() -> None:
                with Session() as session:
                    session.add(self.model_cls(**dialog.values()))
                    session.commit()

            self.run_db(add)

    def on_edit(self) -> None:
        record_id = self.selected_id()
        if record_id is None:
            return
        with Session() as session:
            obj = session.get(self.model_cls, record_id)
            values = {f.name: getattr(obj, f.name) for f in self.fields}
        dialog = FormDialog(
            self, f"{self.entity_title}: изменение", self.fields, values
        )
        if dialog.exec():

            def update() -> None:
                with Session() as session:
                    obj = session.get(self.model_cls, record_id)
                    for name, value in dialog.values().items():
                        setattr(obj, name, value)
                    session.commit()

            self.run_db(update)

    def on_delete(self) -> None:
        record_id = self.selected_id()
        if record_id is None or not confirm(self, f"Удалить запись №{record_id}?"):
            return

        def delete() -> None:
            with Session() as session:
                session.delete(session.get(self.model_cls, record_id))
                session.commit()

        self.run_db(delete)
