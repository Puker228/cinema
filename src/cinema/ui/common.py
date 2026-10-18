"""Общие помощники интерфейса."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PyQt6.QtCore import QSortFilterProxyModel, Qt
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMessageBox,
    QTableView,
    QWidget,
)
from sqlalchemy import text

from cinema.db.engine import engine
from cinema.db.errors import describe_error


def fetch(sql: str, params: dict | None = None) -> tuple[list[str], list[tuple]]:
    """Выполняет SELECT и возвращает (заголовки, строки)."""
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        return list(result.keys()), [tuple(r) for r in result]


SORT_ROLE = Qt.ItemDataRole.UserRole + 1


def format_number(value: float) -> str:
    """1195170.0 -> '1 195 170', 6.70 -> '6.7'."""
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return text.replace(",", "\u00a0")


def make_item(value: Any) -> QStandardItem:
    item = QStandardItem()
    # Текст — для отображения, SORT_ROLE — чтобы числа сортировались как числа.
    item.setData("" if value is None else value, SORT_ROLE)
    if isinstance(value, float):
        item.setText(format_number(value))
    else:
        item.setText("" if value is None else str(value))
    if isinstance(value, (int, float)):
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
    item.setEditable(False)
    return item


def make_model(
    headers: Sequence[str], rows: Sequence[Sequence[Any]]
) -> QStandardItemModel:
    model = QStandardItemModel(0, len(headers))
    model.setHorizontalHeaderLabels(list(headers))
    for row in rows:
        model.appendRow([make_item(v) for v in row])
    return model


def make_table(parent: QWidget | None = None) -> QTableView:
    view = QTableView(parent)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.setAlternatingRowColors(True)
    view.setSortingEnabled(True)
    # По умолчанию — порядок строк из запроса (ORDER BY), пока пользователь не кликнет заголовок.
    view.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
    view.verticalHeader().setVisible(False)
    view.horizontalHeader().setStretchLastSection(True)
    return view


def set_table_data(
    view: QTableView, headers: Sequence[str], rows: Sequence[Sequence[Any]]
) -> None:
    """Заполняет таблицу (через прокси-модель, чтобы работали сортировка и поиск)."""
    proxy = view.model()
    if not isinstance(proxy, QSortFilterProxyModel):
        proxy = QSortFilterProxyModel(view)
        proxy.setFilterKeyColumn(-1)
        proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        proxy.setSortRole(SORT_ROLE)
        view.setModel(proxy)
    proxy.setSourceModel(make_model(headers, rows))
    view.horizontalHeader().resizeSections(QHeaderView.ResizeMode.ResizeToContents)


def selected_value(view: QTableView, column: int = 0) -> Any:
    """Значение указанного столбца выделенной строки (по умолчанию — id)."""
    indexes = (
        view.selectionModel().selectedRows(column) if view.selectionModel() else []
    )
    return indexes[0].data(SORT_ROLE) if indexes else None


def show_error(parent: QWidget, exc: BaseException, title: str = "Ошибка") -> None:
    QMessageBox.warning(parent, title, describe_error(exc))


def confirm(parent: QWidget, question: str) -> bool:
    answer = QMessageBox.question(parent, "Подтверждение", question)
    return answer == QMessageBox.StandardButton.Yes
