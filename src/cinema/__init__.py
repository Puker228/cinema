"""Админка кинотеатра: PyQt6 + SQLite."""

import sys


def main() -> None:
    from PyQt6.QtCore import QLibraryInfo, QLocale, QTranslator
    from PyQt6.QtWidgets import QApplication

    from cinema.db import init_db
    from cinema.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Кинотеатр")
    app.setStyle("Fusion")
    # Русские подписи стандартных кнопок и диалогов Qt (OK/Отмена, выбор файла и т. п.).
    translator = QTranslator(app)
    translations = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(QLocale(QLocale.Language.Russian), "qtbase", "_", translations):
        app.installTranslator(translator)
    init_db()
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
