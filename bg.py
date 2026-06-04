"""Shared background-thread helper — one definition avoids QMetaObject name collisions."""
from PySide6.QtCore import Signal, QObject, QThread

# Module-level strong refs: keep each thread alive until its finished signal fires.
# Without this, callers that null their stored thread ref in the done-callback
# (which runs BEFORE the thread receives quit()) cause premature C++ destruction.
_live: set = set()


class _BgWorker(QObject):
    done = Signal(object)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        self.done.emit(self._fn())


def bg_spawn(fn, callback) -> QThread:
    """Run fn() on a new QThread; deliver result to callback on the main thread."""
    thread = QThread()
    worker = _BgWorker(fn)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.done.connect(callback)
    worker.done.connect(thread.quit)
    worker.done.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread._worker = worker  # strong ref — prevents Python GC from collecting worker
    _live.add(thread)
    thread.finished.connect(lambda: _live.discard(thread))
    thread.start()
    return thread
