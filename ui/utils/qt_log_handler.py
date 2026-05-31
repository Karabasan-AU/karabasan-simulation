import logging

from PyQt5.QtCore import QObject, pyqtSignal

from shared.logger import get_logger

logger = get_logger(__name__)

# Mapping from Python log level to display color
_LEVEL_COLORS = {
    "DEBUG":    "#888888",
    "INFO":     "#00FF00",
    "WARNING":  "#FFA500",
    "ERROR":    "#FF4444",
    "CRITICAL": "#FF0000",
}

_LEVEL_LABELS = {
    "DEBUG":    "DBG",
    "INFO":     "INF",
    "WARNING":  "WRN",
    "ERROR":    "ERR",
    "CRITICAL": "CRT",
}


class _QtLogSignaller(QObject):
    """
    Thin QObject wrapper that owns the Qt signal.
    Needed because logging.Handler is not a QObject
    and cannot emit signals directly.
    """
    log_record = pyqtSignal(str, str, str)  # module, levelname, message


class QtLogHandler(logging.Handler):
    """
    A logging.Handler that forwards log records to LogConsole.

    Usage (in MainWindow.__init__, after LogConsole is created):

        from ui.utils.qt_log_handler import QtLogHandler
        import logging

        self._qt_log_handler = QtLogHandler()
        self._qt_log_handler.attach(self.log_console)
        logging.getLogger().addHandler(self._qt_log_handler)

    Only records at WARNING and above are forwarded by default to avoid
    flooding the console with DEBUG/INFO noise from pyqtgraph internals.
    The threshold can be changed at runtime via set_console_level().
    """

    def __init__(self, level: int = logging.WARNING):
        super().__init__(level)
        self._signaller = _QtLogSignaller()
        self._log_console = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def attach(self, log_console) -> None:
        """
        Wire the handler to a LogConsole instance.
        Must be called before any records are emitted.
        """
        self._log_console = log_console
        self._signaller.log_record.connect(self._log_console.append_log)
        logger.debug("QtLogHandler LogConsole'a bağlandı.")

    def set_console_level(self, level: str) -> None:
        """
        Change the minimum level forwarded to LogConsole at runtime.
        Example: handler.set_console_level("DEBUG")
        """
        numeric = getattr(logging, level.upper(), None)
        if numeric is None:
            raise ValueError(f"Geçersiz seviye: {level}")
        self.setLevel(numeric)

    # ------------------------------------------------------------------
    # logging.Handler interface
    # ------------------------------------------------------------------

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Skip records coming from the handler itself to avoid loops
            if record.name.startswith("ui.utils.qt_log_handler"):
                return

            module   = record.name
            levelname = record.levelname
            message  = self.format(record) if self.formatter else record.getMessage()

            # Signal is thread-safe — Qt queues it to the GUI thread
            self._signaller.log_record.emit(module, levelname, message)

        except Exception:
            self.handleError(record)