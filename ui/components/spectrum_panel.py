import numpy as np
from collections import deque

from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import pyqtSlot
import pyqtgraph as pg

from shared.logger import get_logger

logger = get_logger(__name__)

# How many rows the waterfall keeps in memory
WATERFALL_HISTORY = 100


class WaterfallWidget(pg.GraphicsLayoutWidget):
    """
    Scrolling waterfall (spectrogram) display.
    Rows are added at the top; older rows scroll downward.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackground("#0a0a0a")

        self._history = deque(maxlen=WATERFALL_HISTORY)
        self._img_data = np.zeros((WATERFALL_HISTORY, 1), dtype=np.float32)

        plot = self.addPlot()
        plot.setLabel("left",   "Zaman",   color="#00FF00")
        plot.setLabel("bottom", "Frekans", color="#00FF00")
        plot.getAxis("left").setPen(pg.mkPen("#00FF00"))
        plot.getAxis("bottom").setPen(pg.mkPen("#00FF00"))
        plot.showGrid(x=True, y=True, alpha=0.2)

        self._img_item = pg.ImageItem()
        plot.addItem(self._img_item)

        # Colour map: black → dark blue → cyan → yellow → red
        colors = [
            (0,   (10,  10,  10,  255)),
            (0.3, (0,   0,   180, 255)),
            (0.6, (0,   220, 220, 255)),
            (0.8, (240, 240, 0,   255)),
            (1.0, (255, 0,   0,   255)),
        ]
        cmap = pg.ColorMap(
            pos=[c[0] for c in colors],
            color=[c[1] for c in colors],
        )
        self._img_item.setLookupTable(cmap.getLookupTable())
        self._img_item.setLevels([-120, 0])

        self._plot = plot

    def push_row(self, amplitudes: list) -> None:
        arr = np.array(amplitudes, dtype=np.float32)
        self._history.appendleft(arr)

        n_cols = len(arr)
        img = np.zeros((WATERFALL_HISTORY, n_cols), dtype=np.float32)
        for row_idx, row_data in enumerate(self._history):
            cols = min(len(row_data), n_cols)
            img[row_idx, :cols] = row_data[:cols]

        self._img_item.setImage(img, autoLevels=False)
        self._plot.setXRange(0, n_cols, padding=0)
        self._plot.setYRange(0, WATERFALL_HISTORY, padding=0)


class SpectrumPanel(QGroupBox):
    """
    Top-left panel.

    Contains:
      • A live FFT line plot (pyqtgraph)
      • A WaterfallWidget below it
      • A small status label showing peak frequency and power

    Public interface expected by MainWindow:
      • .waterfall_widget   — the WaterfallWidget instance
      • .last_max_power     — float, dBm of the last peak bin
      • .update_plot(freqs, amplitudes)  — PyQt slot
    """

    def __init__(self, parent=None):
        super().__init__("Spektrum Analizi", parent)

        self.last_max_power: float = -999.0

        # ── Spectrum line plot ────────────────────────────────────────
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("#0a0a0a")
        self._plot_widget.setLabel("left",   "Güç (dBm)",  color="#00FF00")
        self._plot_widget.setLabel("bottom", "Frekans (MHz)", color="#00FF00")
        self._plot_widget.getAxis("left").setPen(pg.mkPen("#00FF00"))
        self._plot_widget.getAxis("bottom").setPen(pg.mkPen("#00FF00"))
        self._plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self._plot_widget.setYRange(-120, 0)
        self._plot_widget.setMinimumHeight(180)

        self._curve = self._plot_widget.plot(
            pen=pg.mkPen(color="#00FF00", width=1),
            name="Spektrum",
        )

        # Peak marker
        self._peak_marker = pg.ScatterPlotItem(
            size=10,
            pen=pg.mkPen(None),
            brush=pg.mkBrush("#FF4444"),
        )
        self._plot_widget.addItem(self._peak_marker)

        # ── Waterfall ─────────────────────────────────────────────────
        self.waterfall_widget = WaterfallWidget()
        self.waterfall_widget.setMinimumHeight(180)

        # ── Status bar ────────────────────────────────────────────────
        self._lbl_peak = QLabel("Tepe: — MHz  |  — dBm")
        self._lbl_peak.setStyleSheet("color: #00FF00; font-size: 11px;")

        # ── Layout ────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 14, 4, 4)
        layout.setSpacing(4)
        layout.addWidget(self._plot_widget,     stretch=1)
        layout.addWidget(self.waterfall_widget, stretch=1)

        status_row = QHBoxLayout()
        status_row.addStretch()
        status_row.addWidget(self._lbl_peak)
        layout.addLayout(status_row)

        logger.debug("SpectrumPanel hazır.")

    # ------------------------------------------------------------------
    # Public slot
    # ------------------------------------------------------------------

    @pyqtSlot(list, list)
    def update_plot(self, freqs: list, amplitudes: list) -> None:
        if not freqs or not amplitudes:
            logger.warning("update_plot: boş veri alındı, atlanıyor.")
            return

        f = np.array(freqs,      dtype=np.float64)
        a = np.array(amplitudes, dtype=np.float32)

        if len(f) != len(a):
            logger.warning(
                "update_plot: freqs(%d) ve amplitudes(%d) uzunlukları eşleşmiyor.",
                len(f), len(a),
            )
            return

        # Convert Hz → MHz for display if values look like Hz
        f_display = f / 1e6 if f.max() > 1e4 else f

        self._curve.setData(f_display, a)

        # Peak detection
        peak_idx = int(np.argmax(a))
        self.last_max_power = float(a[peak_idx])
        peak_freq           = float(f_display[peak_idx])

        self._peak_marker.setData(
            x=[peak_freq],
            y=[self.last_max_power],
        )
        self._lbl_peak.setText(
            f"Tepe: {peak_freq:.3f} MHz  |  {self.last_max_power:.1f} dBm"
        )

        # Push the amplitude row into the waterfall
        self.waterfall_widget.push_row(amplitudes)

        logger.debug(
            "Spektrum güncellendi — %d nokta, tepe %.1f dBm @ %.3f MHz",
            len(f), self.last_max_power, peak_freq,
        )