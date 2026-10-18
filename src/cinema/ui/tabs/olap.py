"""OLAP-куб продаж: сводная таблица по выбранным измерениям и мере."""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cinema.db import olap
from cinema.ui.common import make_item, make_model, make_table

_NONE = "— нет —"


class OlapTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.info = QLabel()
        etl_button = QPushButton("Обновить хранилище (ETL)")
        top = QHBoxLayout()
        top.addWidget(self.info, 1)
        top.addWidget(etl_button)

        self.rows = QComboBox()
        self.rows.addItems(olap.DIMENSIONS)
        self.rows.setCurrentText("Месяц")
        self.cols = QComboBox()
        self.cols.addItems([_NONE, *olap.DIMENSIONS])
        self.cols.setCurrentText("Зал")
        self.measure = QComboBox()
        self.measure.addItems(olap.MEASURES)
        self.filters = {name: QComboBox() for name in olap.FILTERS}

        cube = QGroupBox("Куб")
        grid = QGridLayout(cube)
        grid.addWidget(QLabel("Строки:"), 0, 0)
        grid.addWidget(self.rows, 0, 1)
        grid.addWidget(QLabel("Столбцы:"), 0, 2)
        grid.addWidget(self.cols, 0, 3)
        grid.addWidget(QLabel("Мера:"), 0, 4)
        grid.addWidget(self.measure, 0, 5)
        for i, (name, combo) in enumerate(self.filters.items()):
            grid.addWidget(QLabel(f"Срез «{name}»:"), 1, i * 2)
            grid.addWidget(combo, 1, i * 2 + 1)
        hint = QLabel(
            "Детализация/свёртка (drill-down / roll-up): Год → Квартал → Месяц → Дата, Жанр → Фильм, "
            "Тип зала → Зал. Срезы ограничивают куб по значению измерения (slice/dice)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")

        csv_button = QPushButton("Экспорт CSV…")
        xml_button = QPushButton("Экспорт XML…")
        export_row = QHBoxLayout()
        self.total = QLabel()
        export_row.addWidget(self.total, 1)
        export_row.addWidget(csv_button)
        export_row.addWidget(xml_button)

        self.table = make_table()
        self.table.setSortingEnabled(False)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(cube)
        layout.addWidget(hint)
        layout.addWidget(self.table, 1)
        layout.addLayout(export_row)

        etl_button.clicked.connect(self.run_etl)
        for combo in (self.rows, self.cols, self.measure, *self.filters.values()):
            combo.currentIndexChanged.connect(self.build)
        csv_button.clicked.connect(self.export_csv)
        xml_button.clicked.connect(self.export_xml)
        self.headers: list[str] = []
        self.data: list[list] = []

    def refresh(self) -> None:
        count, first, last = olap.warehouse_info()
        self.info.setText(
            f"Хранилище: {count} фактов (сеансов) за период {first or '—'} … {last or '—'}. "
            "Данные куба — снимок на момент последнего ETL."
        )
        for name, combo in self.filters.items():
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(["Все", *olap.filter_values(name)])
            combo.setCurrentText(current if current else "Все")
            combo.blockSignals(False)
        self.build()

    def run_etl(self) -> None:
        count = olap.refresh_warehouse()
        QMessageBox.information(self, "ETL", f"Хранилище перезагружено: {count} фактов")
        self.refresh()

    def build(self) -> None:
        row_dim = self.rows.currentText()
        col_dim = None if self.cols.currentText() == _NONE else self.cols.currentText()
        if col_dim == row_dim:
            col_dim = None
        measure = self.measure.currentText()
        filters = {
            n: c.currentText()
            for n, c in self.filters.items()
            if c.currentText() not in ("", "Все")
        }
        pivot = olap.build_pivot(row_dim, col_dim, measure, filters)

        if col_dim:
            self.headers = [f"{row_dim} \\ {col_dim}", *pivot.col_keys, "Итого"]
            self.data = [
                [
                    r,
                    *(pivot.cells.get((r, c)) for c in pivot.col_keys),
                    pivot.row_totals[r],
                ]
                for r in pivot.row_keys
            ]
            self.data.append(
                [
                    "Итого",
                    *(pivot.col_totals[c] for c in pivot.col_keys),
                    pivot.grand_total,
                ]
            )
        else:
            self.headers = [row_dim, measure]
            self.data = [[r, pivot.row_totals[r]] for r in pivot.row_keys]
            self.data.append(["Итого", pivot.grand_total])

        model = make_model(self.headers, self.data[:-1])
        bold = QFont()
        bold.setBold(True)
        total_row = [make_item(v) for v in self.data[-1]]
        for item in total_row:
            item.setFont(bold)
        model.appendRow(total_row)
        if col_dim:
            for r in range(model.rowCount()):
                model.item(r, model.columnCount() - 1).setFont(bold)
        self.table.setModel(model)
        self.table.resizeColumnsToContents()
        self.total.setText(
            f"{measure}: итого {pivot.grand_total if pivot.grand_total is not None else '—'}"
        )

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт сводной", "olap.csv", "CSV (*.csv)"
        )
        if path:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(self.headers)
                writer.writerows(self.data)

    def export_xml(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт сводной", "olap.xml", "XML (*.xml)"
        )
        if not path:
            return
        root = ET.Element(
            "olap_report",
            rows=self.rows.currentText(),
            columns=self.cols.currentText(),
            measure=self.measure.currentText(),
        )
        for name, combo in self.filters.items():
            if combo.currentText() != "Все":
                ET.SubElement(root, "slice", dimension=name, value=combo.currentText())
        for row in self.data:
            row_el = ET.SubElement(root, "row", key=str(row[0]))
            for header, value in zip(self.headers[1:], row[1:], strict=True):
                ET.SubElement(row_el, "cell", column=header).text = (
                    "" if value is None else str(value)
                )
        tree = ET.ElementTree(root)
        ET.indent(tree)
        tree.write(path, encoding="utf-8", xml_declaration=True)
