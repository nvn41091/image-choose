from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QLocale, QSettings, QStandardPaths, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from ui.localization import VietnameseQt
from ui.theme import apply_theme
from ui.window import MainWindow

ASSETS = Path(__file__).resolve().parent / 'assets'


def app_data() -> Path:
    local = os.environ.get('LOCALAPPDATA')
    if local:
        return Path(local) / 'ChonAnhCuoi'
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))


def configure_logging(directory: Path):
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(directory / 'ChonAnhCuoi.log', maxBytes=1_000_000,
                                      backupCount=2, encoding='utf-8')
    except OSError:
        handler = logging.StreamHandler()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s',
                        handlers=[handler])


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName('ChonAnhCuoi')
    app.setApplicationName('ChonAnhCuoi')
    app.setApplicationDisplayName('Chọn ảnh cưới')
    app.setWindowIcon(QIcon(str(ASSETS / 'app.ico')))
    app.setFont(QFont('Segoe UI', 10))
    QLocale.setDefault(QLocale(QLocale.Language.Vietnamese, QLocale.Country.Vietnam))
    translator = VietnameseQt(app)
    app.installTranslator(translator)
    local = app_data()
    configure_logging(local)
    settings = QSettings()
    apply_theme(app, settings.value('dark', False, type=bool))
    window = MainWindow(local, ASSETS, settings)
    window.show()
    QTimer.singleShot(0, window.restore)
    result = app.exec()
    for jobs in (window.scan_jobs, window.thumbnails.jobs, window.jobs):
        jobs.pool.waitForDone()
    return result


if __name__ == '__main__':
    sys.exit(main())
