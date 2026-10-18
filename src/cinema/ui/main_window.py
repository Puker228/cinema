"""Главное окно админки."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
)
from sqlalchemy.exc import SQLAlchemyError

from cinema.db import reset_db
from cinema.db.engine import DB_PATH
from cinema.db.xml_io import ENTITIES, export_xml, import_xml
from cinema.ui.common import confirm, show_error
from cinema.ui.tabs.hall_info import HallInfoTab
from cinema.ui.tabs.olap import OlapTab
from cinema.ui.tabs.queries import AuditTab, QueriesTab
from cinema.ui.tabs.reference import customers_tab, films_tab, genres_tab, halls_tab
from cinema.ui.tabs.sessions import SessionsTab
from cinema.ui.tabs.tickets import TicketsTab


class ExportDialog(QDialog):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setWindowTitle("Экспорт в XML")
        layout = QVBoxLayout(self)
        self.checks = {}
        for key, title in ENTITIES.items():
            check = QCheckBox(title)
            check.setChecked(True)
            layout.addWidget(check)
            self.checks[key] = check
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def entities(self) -> list[str]:
        return [key for key, check in self.checks.items() if check.isChecked()]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Кинотеатр — администрирование")
        self.resize(1250, 780)

        self.tabs = QTabWidget()
        for widget, title in (
            (SessionsTab(), "Сеансы"),
            (TicketsTab(), "Билеты"),
            (HallInfoTab(), "Информация о зале"),
            (films_tab(), "Фильмы"),
            (genres_tab(), "Жанры"),
            (halls_tab(), "Залы"),
            (customers_tab(), "Покупатели"),
            (QueriesTab(), "Запросы (РА)"),
            (OlapTab(), "OLAP-куб"),
            (AuditTab(), "Журнал"),
        ):
            self.tabs.addTab(widget, title)
        self.setCentralWidget(self.tabs)
        # Каждая вкладка перечитывает данные при открытии — так изменения на других вкладках сразу видны.
        self.tabs.currentChanged.connect(self.refresh_current)

        file_menu = self.menuBar().addMenu("Файл")
        self._action(
            file_menu, "Импорт из XML…", self.import_xml, QKeySequence.StandardKey.Open
        )
        self._action(
            file_menu, "Экспорт в XML…", self.export_xml, QKeySequence.StandardKey.Save
        )
        file_menu.addSeparator()
        self._action(
            file_menu, "Пересоздать БД с демо-данными", lambda: self.reset(True)
        )
        self._action(file_menu, "Пересоздать пустую БД", lambda: self.reset(False))
        file_menu.addSeparator()
        self._action(file_menu, "Выход", self.close, QKeySequence.StandardKey.Quit)

        self.statusBar().showMessage(f"База данных: {DB_PATH}")
        self.refresh_current()

    def _action(self, menu, title, slot, shortcut=None) -> None:
        action = QAction(title, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        menu.addAction(action)

    def refresh_current(self) -> None:
        widget = self.tabs.currentWidget()
        if hasattr(widget, "refresh"):
            widget.refresh()

    def import_xml(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Импорт из XML", "", "XML (*.xml)")
        if not path:
            return
        try:
            report = import_xml(path)
        except (ET.ParseError, ValueError, OSError, SQLAlchemyError) as exc:
            show_error(self, exc, "Импорт не выполнен")
            return
        QMessageBox.information(self, "Импорт завершён", report.summary())
        self.refresh_current()

    def export_xml(self) -> None:
        dialog = ExportDialog(self)
        if not dialog.exec() or not dialog.entities():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт в XML", "cinema_export.xml", "XML (*.xml)"
        )
        if not path:
            return
        counts = export_xml(path, dialog.entities())
        lines = [f"{ENTITIES[k]}: {n}" for k, n in counts.items()]
        QMessageBox.information(
            self, "Экспорт завершён", f"Файл: {path}\n\n" + "\n".join(lines)
        )

    def reset(self, with_demo_data: bool) -> None:
        kind = "демонстрационными данными" if with_demo_data else "пустой базой"
        if confirm(
            self, f"Все текущие данные будут удалены и заменены {kind}. Продолжить?"
        ):
            reset_db(with_demo_data)
            self.refresh_current()
