from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter
)
from PyQt5.QtCore import Qt

from ui.components.spectrum_panel import SpectrumPanel
from ui.components.df_radar import DFRadar
from ui.components.target_table import TargetTable
from ui.components.et_panel import ETPanel
from ui.components.log_console import LogConsole
from ui.listeners.zmq_listener import ZMQListener
from shared.logger import get_logger
import logging
from ui.utils.qt_log_handler import QtLogHandler

logger = get_logger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EH Komuta Kontrol Merkezi")
        self.setGeometry(50, 50, 1500, 900)
        self.setStyleSheet(
            "QMainWindow { background-color: #121212; }"
            "QGroupBox { color: #00FF00; font-weight: bold;"
            "            border: 1px solid #00FF00;"
            "            margin-top: 6px; padding-top: 6px; }"
            "QGroupBox::title { subcontrol-origin: margin;"
            "                   subcontrol-position: top left;"
            "                   padding: 0 4px; }"
            "QLabel { color: #00FF00; }"
            "QWidget { background-color: #121212; }"
        )

        # --- Build components ---
        self.spectrum_panel = SpectrumPanel()
        self.df_radar       = DFRadar()
        self.target_table   = TargetTable()
        self.et_panel       = ETPanel()
        self.log_console    = LogConsole()
        
        self._qt_log_handler = QtLogHandler(level=logging.WARNING)
        self._qt_log_handler.attach(self.log_console)
        logging.getLogger().addHandler(self._qt_log_handler)

        # --- Layout ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # Left column: spectrum panel only (waterfall lives INSIDE it)
        left_splitter = QSplitter(Qt.Vertical)
        left_splitter.addWidget(self.spectrum_panel)
        main_layout.addWidget(left_splitter, stretch=6)

        # Right column: table → radar → ET buttons → logs
        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(self.target_table)
        right_splitter.addWidget(self.df_radar)
        right_splitter.addWidget(self.et_panel)
        right_splitter.addWidget(self.log_console)
        main_layout.addWidget(right_splitter, stretch=4)

        # --- Wire ET panel signals → log console ---
        self.et_panel.jam_continuous_requested.connect(
            lambda: self.log_console.append_attack(
                "Sürekli Jamming başlatıldı!", "#FF4444"
            )
        )
        self.et_panel.jam_sweep_requested.connect(
            lambda: self.log_console.append_attack(
                "Sweep Jamming başlatıldı!", "#FFA500"
            )
        )
        self.et_panel.spoof_voice_requested.connect(
            lambda: self.log_console.append_attack(
                "Telsiz Ses Aldatması devrede!", "#FF00FF"
            )
        )
        self.et_panel.spoof_gnss_requested.connect(
            lambda: self.log_console.append_attack(
                "GNSS Spoofing uygulanıyor!", "#00FFFF"
            )
        )

        # --- Start listener and wire its signals ---
        self.listener = ZMQListener()
        self.listener.spectrum_received.connect(self.spectrum_panel.update_plot)
        self.listener.target_received.connect(self.target_table.update)
        self.listener.target_received.connect(self.df_radar.set_last_signal_type)
        self.listener.df_received.connect(self.df_radar.update_angle)
        self.listener.df_received.connect(self._on_df_received)
        self.listener.sigint_received.connect(self.log_console.append_sigint)
        self.listener.start()

        logger.info("Ana pencere bileşenleri yüklendi ve dinleyici başlatıldı.")

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_df_received(self, angle: int) -> None:
        """Forward the latest max power to the radar whenever a DF update arrives."""
        self.df_radar.update_power(self.spectrum_panel.last_max_power)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        logger.info("Arayüz kapatılıyor, dinleyici durduruluyor.")
        self.listener.stop()
        self.listener.wait()
        event.accept()