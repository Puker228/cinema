"""Запросы реляционной алгебры и журнал аудита."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import SQLAlchemyError

from cinema.db.engine import engine
from cinema.db.queries import OPERATIONS, QUERIES
from cinema.ui.common import fetch, make_table, set_table_data, show_error


class QueriesTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.operation = QComboBox()
        self.operation.addItem("Все операции", None)
        for op in OPERATIONS:
            self.operation.addItem(op, op)
        self.list = QListWidget()

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.operation)
        left_layout.addWidget(self.list)

        self.algebra = QLabel()
        self.algebra.setWordWrap(True)
        self.algebra.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.sql = QPlainTextEdit()
        self.sql.setFont(QFont("Menlo", 12))
        run_button = QPushButton("Выполнить (Ctrl+Enter)")
        run_button.setShortcut("Ctrl+Return")
        self.status = QLabel()
        self.result = make_table()

        run_row = QHBoxLayout()
        run_row.addWidget(run_button)
        run_row.addWidget(self.status, 1)
        right = QSplitter(Qt.Orientation.Vertical)
        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.addWidget(self.algebra)
        editor_layout.addWidget(self.sql)
        editor_layout.addLayout(run_row)
        right.addWidget(editor)
        right.addWidget(self.result)
        right.setSizes([300, 400])

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([330, 770])
        QVBoxLayout(self).addWidget(splitter)

        self.operation.currentIndexChanged.connect(self.fill_list)
        self.list.currentItemChanged.connect(self.show_query)
        run_button.clicked.connect(self.run)
        self.fill_list()

    def fill_list(self) -> None:
        op = self.operation.currentData()
        self.list.clear()
        for query in QUERIES:
            if op is None or op in query.operations:
                item = QListWidgetItem(query.title)
                item.setToolTip(", ".join(query.operations))
                item.setData(Qt.ItemDataRole.UserRole, query)
                self.list.addItem(item)
        self.list.setCurrentRow(0)

    def show_query(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        query = item.data(Qt.ItemDataRole.UserRole)
        self.algebra.setText(
            f"<b>Операции:</b> {', '.join(query.operations)}<br><b>Выражение:</b> {query.algebra}"
        )
        self.sql.setPlainText(query.sql)
        self.run()

    def run(self) -> None:
        sql = self.sql.toPlainText().strip()
        if not sql:
            return
        try:
            # exec_driver_sql — без разбора «:параметров», чтобы литералы вида '10:00' не мешали.
            with engine.begin() as conn:
                result = conn.exec_driver_sql(sql)
                if result.returns_rows:
                    headers, rows = list(result.keys()), [tuple(r) for r in result]
                else:
                    headers, rows = [], []
                    self.status.setText(f"Изменено строк: {result.rowcount}")
        except SQLAlchemyError as exc:
            show_error(self, exc, "Ошибка в запросе")
            return
        set_table_data(self.result, headers, rows)
        if headers:
            self.status.setText(f"Строк: {len(rows)}")


class AuditTab(QWidget):
    """Журнал, который ведут триггеры trg_audit_*."""

    def __init__(self) -> None:
        super().__init__()
        self.table_filter = QComboBox()
        for label, value in (
            ("Все таблицы", None),
            ("films", "films"),
            ("sessions", "sessions"),
            ("tickets", "tickets"),
        ):
            self.table_filter.addItem(label, value)
        refresh_button = QPushButton("Обновить")
        top = QHBoxLayout()
        top.addWidget(
            QLabel("Изменения, записанные триггерами аудита (последние 1000):")
        )
        top.addStretch()
        top.addWidget(self.table_filter)
        top.addWidget(refresh_button)
        self.table = make_table()
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)
        self.table_filter.currentIndexChanged.connect(self.refresh)
        refresh_button.clicked.connect(self.refresh)

    def refresh(self) -> None:
        table = self.table_filter.currentData()
        _, rows = fetch(
            f"""SELECT id, created_at, table_name, action, record_id, details FROM audit_log
                {"WHERE table_name = :t" if table else ""} ORDER BY id DESC LIMIT 1000""",
            {"t": table},
        )
        set_table_data(
            self.table,
            ["№", "Время", "Таблица", "Действие", "id записи", "Подробности"],
            rows,
        )
