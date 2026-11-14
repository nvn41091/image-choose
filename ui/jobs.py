from __future__ import annotations

import logging
from itertools import count

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage

log = logging.getLogger(__name__)


class Task(QRunnable):
    def __init__(self, broker, token, work):
        super().__init__()
        self.broker = broker
        self.token = token
        self.work = work

    def run(self):
        def progress(value):
            self.broker.progress.emit(self.token, value)

        try:
            result = self.work(progress)
        except Exception as error:
            log.warning('Tác vụ nền gặp lỗi: %s', error, exc_info=True)
            self.broker.done.emit(self.token, None, error)
        else:
            self.broker.done.emit(self.token, result, None)


class Jobs(QObject):
    done = Signal(int, object, object)
    progress = Signal(int, int)

    def __init__(self, parent=None, threads=3):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(threads)
        self.tokens = count()
        self.handlers = {}
        self.done.connect(self._done, Qt.ConnectionType.QueuedConnection)
        self.progress.connect(self._progress, Qt.ConnectionType.QueuedConnection)

    def start(self, work, finished, progress=None):
        token = next(self.tokens)
        self.handlers[token] = (finished, progress)
        self.pool.start(Task(self, token, work))
        return token

    def forget(self, token):
        self.handlers.pop(token, None)

    @Slot(int, object, object)
    def _done(self, token, result, error):
        handler = self.handlers.pop(token, None)
        if handler:
            handler[0](result, error)

    @Slot(int, int)
    def _progress(self, token, value):
        handler = self.handlers.get(token)
        if handler and handler[1]:
            handler[1](value)


def to_qimage(image):
    width, height = image.size
    pixels = image.tobytes()
    # Sao chép bộ đệm trước khi kết thúc luồng nền.
    return QImage(pixels, width, height, width * 4, QImage.Format.Format_RGBA8888).copy()
