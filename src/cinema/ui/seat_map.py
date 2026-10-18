"""Схема зала: сетка мест с занятыми, свободными и выбранными местами."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

_STYLE = """
QPushButton { background: #d9f2d9; color: #1b4d1b; border: 1px solid #8bc48b; border-radius: 4px;
              font-size: 10px; padding: 0; }
QPushButton:checked { background: #3b82f6; color: white; border-color: #1d4ed8; }
QPushButton:disabled { background: #e57373; color: white; border-color: #c62828; }
"""


class SeatMap(QWidget):
    selectionChanged = pyqtSignal()

    def __init__(self, selectable: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.selectable = selectable
        self.buttons: dict[tuple[int, int], QPushButton] = {}

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        legend = QLabel(
            "<span style='color:#4caf50'>■</span> свободно &nbsp; "
            "<span style='color:#e57373'>■</span> занято"
            + (
                " &nbsp; <span style='color:#3b82f6'>■</span> выбрано"
                if selectable
                else ""
            )
        )
        legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)
        layout.addWidget(legend)
        self.clear()

    def clear(self, message: str = "Выберите сеанс") -> None:
        self.buttons = {}
        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(label)

    def set_hall(self, rows: int, seats: int, occupied: set[tuple[int, int]]) -> None:
        container = QWidget()
        container.setStyleSheet(_STYLE)
        grid = QGridLayout(container)
        grid.setSpacing(3)

        screen = QLabel("Э К Р А Н")
        screen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        screen.setStyleSheet(
            "background: #555; color: white; border-radius: 3px; padding: 2px;"
        )
        grid.addWidget(screen, 0, 1, 1, seats)
        grid.setRowMinimumHeight(1, 12)

        self.buttons = {}
        for r in range(1, rows + 1):
            grid.addWidget(QLabel(f"Ряд {r}"), r + 1, 0)
            for s in range(1, seats + 1):
                button = QPushButton(str(s))
                button.setFixedSize(26, 22)
                button.setToolTip(f"Ряд {r}, место {s}")
                button.setCheckable(self.selectable)
                button.setEnabled((r, s) not in occupied)
                button.toggled.connect(self.selectionChanged)
                grid.addWidget(button, r + 1, s)
                self.buttons[(r, s)] = button
        self.scroll.setWidget(container)

    def selected(self) -> list[tuple[int, int]]:
        return sorted(
            seat for seat, button in self.buttons.items() if button.isChecked()
        )
