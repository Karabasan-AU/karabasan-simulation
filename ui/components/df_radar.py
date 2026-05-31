import math

from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QLabel, QHBoxLayout
from PyQt5.QtCore    import pyqtSlot, Qt, QPointF
from PyQt5.QtGui     import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QPolygonF
)
import pyqtgraph as pg

from shared.logger import get_logger

logger = get_logger(__name__)

SIGNAL_COLORS = {
    "Drone (FHSS)":    "#FF0000",
    "Wi-Fi (802.11)":  "#00FFFF",
    "Bluetooth":       "#4444FF",
    "Analog Telsiz":   "#FFFF00",
    "FSK Data Link":   "#FF00FF",
    "Telemetri":       "#FF00FF",
}
DEFAULT_COLOR = "#00FF00"


class RadarCanvas(pg.GraphicsLayoutWidget):
    """
    Polar compass rose with:
      • Concentric range rings
      • Cardinal / intercardinal tick marks
      • A direction needle that rotates to the current angle
      • Needle colour tracks the last detected signal type
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackground("#0a0a0a")
        self.setMinimumSize(220, 220)

        self._angle_deg:  float = 0.0
        self._power_dbm:  float = -999.0
        self._color:      str   = DEFAULT_COLOR

        self._plot = self.addPlot()
        self._plot.setAspectLocked(True)
        self._plot.hideAxis("left")
        self._plot.hideAxis("bottom")
        self._plot.setXRange(-1.2, 1.2, padding=0)
        self._plot.setYRange(-1.2, 1.2, padding=0)

        self._build_static_layer()

        # Needle: a thick line from centre toward the rim
        self._needle = pg.PlotDataItem(
            pen=pg.mkPen(color=self._color, width=3)
        )
        self._plot.addItem(self._needle)

        # Small dot at needle tip
        self._tip_dot = pg.ScatterPlotItem(
            size=10,
            pen=pg.mkPen(None),
            brush=pg.mkBrush(self._color),
        )
        self._plot.addItem(self._tip_dot)

        self._draw_needle()

    # ------------------------------------------------------------------
    # Static background elements
    # ------------------------------------------------------------------

    def _build_static_layer(self) -> None:
        ring_pen   = pg.mkPen(color="#003300", width=1)
        axis_pen   = pg.mkPen(color="#004400", width=1, style=Qt.DashLine)
        tick_pen   = pg.mkPen(color="#00AA00", width=1)

        # Concentric rings at 25 %, 50 %, 75 %, 100 %
        for r in (0.25, 0.50, 0.75, 1.0):
            circle = pg.QtWidgets.QGraphicsEllipseItem(-r, -r, r * 2, r * 2)
            circle.setPen(ring_pen)
            circle.setBrush(QBrush(Qt.NoBrush))
            self._plot.addItem(circle)

        # Cross-hair axes
        for angle in (0, 90):
            rad = math.radians(angle)
            line = pg.InfiniteLine(
                angle=angle,
                pen=axis_pen,
            )
            self._plot.addItem(line)

        # Cardinal labels  N / E / S / W
        for label, ax, ay in (("N", 0, 1.12), ("E", 1.12, 0),
                               ("S", 0, -1.12), ("W", -1.12, 0)):
            txt = pg.TextItem(label, color="#00CC00", anchor=(0.5, 0.5))
            txt.setPos(ax, ay)
            self._plot.addItem(txt)

        # Tick marks every 30°
        for deg in range(0, 360, 30):
            rad = math.radians(90 - deg)          # pyqtgraph: 0° = East
            outer = 1.0
            inner = 0.88 if deg % 90 == 0 else 0.93
            x0, y0 = inner * math.cos(rad), inner * math.sin(rad)
            x1, y1 = outer * math.cos(rad), outer * math.sin(rad)
            tick = pg.PlotDataItem([x0, x1], [y0, y1], pen=tick_pen)
            self._plot.addItem(tick)

    # ------------------------------------------------------------------
    # Needle drawing
    # ------------------------------------------------------------------

    def _draw_needle(self) -> None:
        # Convert: 0° = North, clockwise → pyqtgraph angle (0° = East, CCW)
        rad = math.radians(90.0 - self._angle_deg)
        tip_x = math.cos(rad)
        tip_y = math.sin(rad)

        pen   = pg.mkPen(color=self._color, width=3)
        brush = pg.mkBrush(self._color)

        self._needle.setData([0.0, tip_x * 0.9], [0.0, tip_y * 0.9])
        self._needle.setPen(pen)
        self._tip_dot.setData([tip_x * 0.9], [tip_y * 0.9])
        self._tip_dot.setBrush(brush)

    # ------------------------------------------------------------------
    # Public update methods
    # ------------------------------------------------------------------

    def set_angle(self, angle_deg: int) -> None:
        self._angle_deg = float(angle_deg % 360)
        self._draw_needle()

    def set_power(self, power_dbm: float) -> None:
        self._power_dbm = power_dbm

    def set_color(self, hex_color: str) -> None:
        self._color = hex_color
        self._draw_needle()


class DFRadar(QGroupBox):
    """
    Direction-finding radar panel.

    Public interface expected by MainWindow:
      • update_angle(angle_deg: int)
      • update_power(power_dbm: float)
      • set_last_signal_type(target_data: dict)
    """

    def __init__(self, parent=None):
        super().__init__("Yön Bulma (DF)", parent)

        self._last_angle: int   = 0
        self._last_power: float = -999.0
        self._last_type:  str   = "—"

        self._canvas = RadarCanvas()

        # Status labels
        self._lbl_angle = QLabel("Açı:  —°")
        self._lbl_power = QLabel("Güç:  — dBm")
        self._lbl_type  = QLabel("Tür:  —")
        for lbl in (self._lbl_angle, self._lbl_power, self._lbl_type):
            lbl.setStyleSheet("color: #00FF00; font-size: 11px;")
            lbl.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 14, 4, 4)
        layout.setSpacing(4)
        layout.addWidget(self._canvas)

        info_row = QHBoxLayout()
        info_row.addWidget(self._lbl_angle)
        info_row.addWidget(self._lbl_power)
        info_row.addWidget(self._lbl_type)
        layout.addLayout(info_row)

        logger.debug("DFRadar hazır.")

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    @pyqtSlot(int)
    def update_angle(self, angle_deg: int) -> None:
        self._last_angle = angle_deg
        self._canvas.set_angle(angle_deg)
        self._lbl_angle.setText(f"Açı:  {angle_deg}°")
        logger.debug("DF açı güncellendi: %d°", angle_deg)

    @pyqtSlot(float)
    def update_power(self, power_dbm: float) -> None:
        self._last_power = power_dbm
        self._canvas.set_power(power_dbm)
        self._lbl_power.setText(f"Güç:  {power_dbm:.1f} dBm")
        logger.debug("DF güç güncellendi: %.1f dBm", power_dbm)

    @pyqtSlot(dict)
    def set_last_signal_type(self, target_data: dict) -> None:
        sig_type = target_data.get("modulation") or target_data.get("type") or "—"
        color    = SIGNAL_COLORS.get(sig_type, DEFAULT_COLOR)
        self._last_type = sig_type
        self._canvas.set_color(color)
        self._lbl_type.setText(f"Tür:  {sig_type}")
        logger.debug("DF sinyal türü güncellendi: %s (%s)", sig_type, color)