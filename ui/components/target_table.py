from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel
)
from PyQt5.QtCore  import pyqtSlot, Qt
from PyQt5.QtGui   import QColor, QFont

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
DEFAULT_COLOR = "#00FF00"

# Column definitions: (header_label, target_data_key, format_fn)
_COLUMNS = [
    ("ID",           "signal_id",       lambda v: str(v)),
    ("Frekans (MHz)","center_freq_hz",  lambda v: f"{float(v)/1e6:.3f}" if v else "—"),
    ("BW (kHz)",     "bandwidth_hz",    lambda v: f"{float(v)/1e3:.1f}" if v else "—"),
    ("Güç (dBm)",    "power_dbm",       lambda v: f"{float(v):.1f}"     if v else "—"),
    ("Mod.",         "modulation",      lambda v: str(v) if v else "—"),
    ("Azimut (°)",   "azimuth_deg",     lambda v: f"{float(v):.1f}"     if v else "—"),
    ("X (m)",        "estimated_x_m",   lambda v: f"{float(v):.1f}"     if v else "—"),
    ("Y (m)",        "estimated_y_m",   lambda v: f"{float(v):.1f}"     if v else "—"),
]

_HDR  = [c[0] for c in _COLUMNS]
_KEYS = [c[1] for c in _COLUMNS]
_FMTS = [c[2] for c in _COLUMNS]


class TargetTable(QGroupBox):
    """
    Scrollable table of detected targets.

    Rows are keyed on signal_id — an incoming dict updates an existing
    row in place or appends a new one.

    Public interface expected by MainWindow:
      • update(target_data: dict)  — PyQt slot
    """

    def __init__(self, parent=None):
        super().__init__("Hedef Tablosu", parent)

        self._id_to_row: dict[str, int] = {}

        # ── Table widget ──────────────────────────────────────────────
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_HDR)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        self._table.setSortingEnabled(False)

        # Stretch last column, resize others to content
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self._table.horizontalHeader().setStretchLastSection(True)

        self._apply_table_style()

        # ── Status label ──────────────────────────────────────────────
        self._lbl_count = QLabel("Hedef: 0")
        self._lbl_count.setStyleSheet("color: #00FF00; font-size: 11px;")
        self._lbl_count.setAlignment(Qt.AlignRight)

        # ── Layout ────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 14, 4, 4)
        layout.setSpacing(4)
        layout.addWidget(self._table)
        layout.addWidget(self._lbl_count)

        logger.debug("TargetTable hazır.")

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def _apply_table_style(self) -> None:
        self._table.setStyleSheet(
            "QTableWidget {"
            "  background-color: #0a0a0a;"
            "  color: #00FF00;"
            "  gridline-color: #003300;"
            "  font-size: 11px;"
            "}"
            "QTableWidget::item:selected {"
            "  background-color: #003300;"
            "  color: #00FF00;"
            "}"
            "QHeaderView::section {"
            "  background-color: #121212;"
            "  color: #00AA00;"
            "  border: 1px solid #003300;"
            "  font-size: 11px;"
            "  font-weight: bold;"
            "  padding: 2px;"
            "}"
            "QScrollBar:vertical {"
            "  background: #0a0a0a;"
            "  width: 8px;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: #004400;"
            "  border-radius: 4px;"
            "}"
        )

    # ------------------------------------------------------------------
    # Public slot
    # ------------------------------------------------------------------

    @pyqtSlot(dict)
    def update(self, target_data: dict) -> None:
        signal_id = str(target_data.get("signal_id", ""))
        if not signal_id:
            logger.warning("update: signal_id eksik, satır atlanıyor.")
            return

        # Determine row index — insert new row if unseen ID
        if signal_id in self._id_to_row:
            row = self._id_to_row[signal_id]
        else:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._id_to_row[signal_id] = row
            logger.debug("Yeni hedef eklendi: %s (satır %d)", signal_id, row)

        # Resolve colour from modulation field
        modulation = target_data.get("modulation", "")
        hex_color  = SIGNAL_COLORS.get(modulation, DEFAULT_COLOR)
        fg_color   = QColor(hex_color)

        # Fill / update every cell in the row
        for col, (key, fmt) in enumerate(zip(_KEYS, _FMTS)):
            raw   = target_data.get(key)
            text  = fmt(raw) if raw is not None else "—"
            item  = QTableWidgetItem(text)
            item.setForeground(fg_color)
            item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, col, item)

        self._lbl_count.setText(f"Hedef: {self._table.rowCount()}")
        logger.debug(
            "Hedef güncellendi: %s  mod=%s  renk=%s",
            signal_id, modulation, hex_color,
        )