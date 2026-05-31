from datetime import datetime

from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLabel, QPushButton
)
from PyQt5.QtCore  import Qt
from PyQt5.QtGui   import QColor, QTextCursor, QFont

from shared.logger import get_logger

logger = get_logger(__name__)

SIGNAL_COLORS = {
    "Drone (FHSS)":   "#FF0000",
    "Wi-Fi (802.11)": "#00FFFF",
    "Bluetooth":      "#4444FF",
    "Analog Telsiz":  "#FFFF00",
    "FSK Data Link":  "#FF00FF",
    "Telemetri":      "#FF00FF",
}
DEFAULT_COLOR  = "#00FF00"
MAX_LOG_LINES  = 500


class LogConsole(QGroupBox):
    """
    Scrollable HTML log console with two feeds:

      • Attack log  — operator-initiated ET actions
      • SIGINT log  — incoming detection / location / demodulation events

    Public interface expected by MainWindow:
      • append_attack(msg: str, color: str)
      • append_sigint(data: dict)
    """

    def __init__(self, parent=None):
        super().__init__("Olay Günlüğü", parent)

        self._line_count = 0

        # ── Text area ─────────────────────────────────────────────────
        self._console = QTextEdit()
        self._console.setReadOnly(True)
        self._console.setLineWrapMode(QTextEdit.NoWrap)
        self._console.setStyleSheet(
            "QTextEdit {"
            "  background-color: #0a0a0a;"
            "  color: #00FF00;"
            "  font-family: 'Courier New', monospace;"
            "  font-size: 11px;"
            "  border: 1px solid #003300;"
            "}"
            "QScrollBar:vertical {"
            "  background: #0a0a0a; width: 8px;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: #004400; border-radius: 4px;"
            "}"
            "QScrollBar:horizontal {"
            "  background: #0a0a0a; height: 8px;"
            "}"
            "QScrollBar::handle:horizontal {"
            "  background: #004400; border-radius: 4px;"
            "}"
        )

        # ── Toolbar ───────────────────────────────────────────────────
        self._lbl_count = QLabel("0 olay")
        self._lbl_count.setStyleSheet("color: #00AA00; font-size: 10px;")

        btn_clear = QPushButton("Temizle")
        btn_clear.setFixedWidth(64)
        btn_clear.setFixedHeight(20)
        btn_clear.setStyleSheet(
            "QPushButton {"
            "  background-color: #1a1a1a;"
            "  color: #00AA00;"
            "  border: 1px solid #004400;"
            "  border-radius: 3px;"
            "  font-size: 10px;"
            "}"
            "QPushButton:hover { background-color: #003300; }"
        )
        btn_clear.clicked.connect(self._clear)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._lbl_count)
        toolbar.addStretch()
        toolbar.addWidget(btn_clear)

        # ── Layout ────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 14, 4, 4)
        layout.setSpacing(4)
        layout.addLayout(toolbar)
        layout.addWidget(self._console)

        logger.debug("LogConsole hazır.")


    def append_log(self, module: str, levelname: str, message: str) -> None:
        """
        Display a Python log record forwarded by QtLogHandler.
        Visually distinct from SIGINT events — shown in dimmer colors
        so operator-relevant events stand out.
        """
        _LEVEL_COLORS = {
            "DEBUG":    "#555555",
            "INFO":     "#007700",
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
        color = _LEVEL_COLORS.get(levelname, "#555555")
        label = _LEVEL_LABELS.get(levelname, levelname[:3])
        ts    = self._timestamp()
        html  = (
            f'<span style="color:#333333;">{ts}</span> '
            f'<span style="color:{color};font-weight:bold;">[{label}]</span> '
            f'<span style="color:#444444;">{module}:</span> '
            f'<span style="color:{color};">{message}</span>'
        )
        self._append_html(html)
        # Do not call logger here — would create a feedback loop

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append_attack(self, msg: str, color: str = DEFAULT_COLOR) -> None:
        """
        Log an operator-initiated electronic attack event.

        Args:
            msg:   Human-readable description of the action.
            color: Hex color string for the message text.
        """
        ts   = self._timestamp()
        html = (
            f'<span style="color:#555555;">{ts}</span> '
            f'<span style="color:#FF8800;font-weight:bold;">[TAARRUZ]</span> '
            f'<span style="color:{color};">{msg}</span>'
        )
        self._append_html(html)
        logger.info("Taarruz logu: %s", msg)

    def append_sigint(self, data: dict) -> None:
        """
        Log an incoming SIGINT event (detection / location / demodulation).

        Dispatches to a dedicated formatter based on the 'type' key.
        """
        event_type = data.get("type", "unknown")
        handler = {
            "detection":     self._fmt_detection,
            "location":      self._fmt_location,
            "demodulation":  self._fmt_demodulation,
            "jamming_status":self._fmt_jamming_status,
        }.get(event_type, self._fmt_generic)

        html = handler(data)
        self._append_html(html)
        logger.debug("SIGINT logu: tip=%s id=%s", event_type, data.get("signal_id", "?"))

    # ------------------------------------------------------------------
    # SIGINT formatters
    # ------------------------------------------------------------------

    def _fmt_detection(self, d: dict) -> str:
        modulation = d.get("modulation", "?")
        color      = SIGNAL_COLORS.get(modulation, DEFAULT_COLOR)
        freq_mhz   = self._hz_to_mhz(d.get("center_freq_hz"))
        bw_khz     = self._hz_to_khz(d.get("bandwidth_hz"))
        power      = self._fmt_val(d.get("power_dbm"), ".1f", "dBm")
        ts         = self._timestamp()
        return (
            f'<span style="color:#555555;">{ts}</span> '
            f'<span style="color:#00AAFF;font-weight:bold;">[TESPİT]</span> '
            f'<span style="color:{color};font-weight:bold;">{modulation}</span> '
            f'<span style="color:#AAAAAA;">'
            f'id={d.get("signal_id","?")}  '
            f'f={freq_mhz}  bw={bw_khz}  pwr={power}'
            f'</span>'
        )

    def _fmt_location(self, d: dict) -> str:
        ts  = self._timestamp()
        az  = self._fmt_val(d.get("azimuth_deg"),   ".1f", "°")
        x   = self._fmt_val(d.get("estimated_x_m"), ".1f", "m")
        y   = self._fmt_val(d.get("estimated_y_m"), ".1f", "m")
        return (
            f'<span style="color:#555555;">{ts}</span> '
            f'<span style="color:#FFFF00;font-weight:bold;">[KONUM]</span> '
            f'<span style="color:#AAAAAA;">'
            f'id={d.get("signal_id","?")}  '
            f'azimut={az}  x={x}  y={y}'
            f'</span>'
        )

    def _fmt_demodulation(self, d: dict) -> str:
        ts = self._timestamp()
        return (
            f'<span style="color:#555555;">{ts}</span> '
            f'<span style="color:#AA00FF;font-weight:bold;">[DEMOD]</span> '
            f'<span style="color:#AAAAAA;">'
            f'id={d.get("signal_id","?")}  ses chunk alındı'
            f'</span>'
        )

    def _fmt_jamming_status(self, d: dict) -> str:
        ts     = self._timestamp()
        active = d.get("active", False)
        mode   = d.get("mode", "?")
        jsr    = self._fmt_val(d.get("jsr_db"), ".1f", "dB")
        color  = "#FF4444" if active else "#888888"
        state  = "AKTİF" if active else "KAPALI"
        return (
            f'<span style="color:#555555;">{ts}</span> '
            f'<span style="color:{color};font-weight:bold;">[JAM-DURUM]</span> '
            f'<span style="color:#AAAAAA;">'
            f'durum={state}  mod={mode}  JSR={jsr}'
            f'</span>'
        )

    def _fmt_generic(self, d: dict) -> str:
        ts = self._timestamp()
        return (
            f'<span style="color:#555555;">{ts}</span> '
            f'<span style="color:#888888;">[{d.get("type","?").upper()}]</span> '
            f'<span style="color:#666666;">{d}</span>'
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append_html(self, html: str) -> None:
        # Trim oldest lines when buffer is full
        if self._line_count >= MAX_LOG_LINES:
            cursor = QTextCursor(self._console.document())
            cursor.movePosition(QTextCursor.Start)
            cursor.select(QTextCursor.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()          # remove the trailing newline
            self._line_count -= 1

        self._console.append(html)
        self._line_count += 1
        self._lbl_count.setText(f"{self._line_count} olay")

        # Auto-scroll to bottom
        self._console.moveCursor(QTextCursor.End)

    def _clear(self) -> None:
        self._console.clear()
        self._line_count = 0
        self._lbl_count.setText("0 olay")
        logger.debug("LogConsole temizlendi.")

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]

    @staticmethod
    def _hz_to_mhz(val) -> str:
        if val is None:
            return "—"
        return f"{float(val)/1e6:.3f} MHz"

    @staticmethod
    def _hz_to_khz(val) -> str:
        if val is None:
            return "—"
        return f"{float(val)/1e3:.1f} kHz"

    @staticmethod
    def _fmt_val(val, fmt: str, unit: str) -> str:
        if val is None:
            return "—"
        return f"{float(val):{fmt}} {unit}"