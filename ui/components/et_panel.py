from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
)
from PyQt5.QtCore import pyqtSignal, Qt
import requests

from shared.logger import get_logger
import json, os

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Load ET endpoint from shared config at import time
# ---------------------------------------------------------------------------

def _load_et_address() -> str:
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "shared", "config.json"
    )
    try:
        with open(os.path.abspath(config_path)) as f:
            cfg = json.load(f)
        address = cfg["sockets"]["ui_to_et"]["address"]
        logger.info("ET adresi yüklendi: %s", address)
        return address
    except Exception as exc:
        logger.error("config.json okunamadı, varsayılan adres kullanılıyor: %s", exc)
        return "http://localhost:8000"


_ET_ADDRESS = _load_et_address()

# REST endpoint paths
_ENDPOINTS = {
    "jam_continuous": "/jam/continuous/start",
    "jam_sweep":      "/jam/sweep/start",
    "spoof_voice":    "/spoof/voice/start",
    "spoof_gnss":     "/spoof/gnss/start",
}


class ETPanel(QGroupBox):
    """
    Electronic attack control panel.

    Emits a Qt signal for each action (wired to LogConsole in MainWindow)
    AND fires a REST POST to the ET system.

    Public interface expected by MainWindow:
      • jam_continuous_requested  (signal)
      • jam_sweep_requested       (signal)
      • spoof_voice_requested     (signal)
      • spoof_gnss_requested      (signal)
    """

    jam_continuous_requested = pyqtSignal()
    jam_sweep_requested      = pyqtSignal()
    spoof_voice_requested    = pyqtSignal()
    spoof_gnss_requested     = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Elektronik Taarruz", parent)

        # ── Buttons ───────────────────────────────────────────────────
        self._btn_jam_cont  = self._make_button("🔴  Sürekli Jamming",  "#8B0000", "#FF4444")
        self._btn_jam_sweep = self._make_button("🟠  Sweep Jamming",    "#7A3B00", "#FFA500")
        self._btn_spoof_voice = self._make_button("🟣  Ses Aldatması",  "#4B0082", "#FF00FF")
        self._btn_spoof_gnss  = self._make_button("🔵  GNSS Spoofing",  "#003366", "#00CCFF")

        # ── Status label ──────────────────────────────────────────────
        self._lbl_status = QLabel("Hazır")
        self._lbl_status.setAlignment(Qt.AlignCenter)
        self._lbl_status.setStyleSheet(
            "color: #00FF00; font-size: 11px; padding: 2px;"
        )

        # ── Layout ────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 14, 4, 4)
        layout.setSpacing(6)

        row1 = QHBoxLayout()
        row1.addWidget(self._btn_jam_cont)
        row1.addWidget(self._btn_jam_sweep)

        row2 = QHBoxLayout()
        row2.addWidget(self._btn_spoof_voice)
        row2.addWidget(self._btn_spoof_gnss)

        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addWidget(self._lbl_status)

        # ── Wire buttons ──────────────────────────────────────────────
        self._btn_jam_cont.clicked.connect(
            lambda: self._handle("jam_continuous", self.jam_continuous_requested)
        )
        self._btn_jam_sweep.clicked.connect(
            lambda: self._handle("jam_sweep", self.jam_sweep_requested)
        )
        self._btn_spoof_voice.clicked.connect(
            lambda: self._handle("spoof_voice", self.spoof_voice_requested)
        )
        self._btn_spoof_gnss.clicked.connect(
            lambda: self._handle("spoof_gnss", self.spoof_gnss_requested)
        )

        logger.debug("ETPanel hazır, ET adresi: %s", _ET_ADDRESS)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_button(label: str, bg: str, border: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setMinimumHeight(36)
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {bg};"
            f"  color: #FFFFFF;"
            f"  border: 1px solid {border};"
            f"  border-radius: 4px;"
            f"  font-weight: bold;"
            f"  font-size: 12px;"
            f"  padding: 4px 8px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {border};"
            f"  color: #000000;"
            f"}}"
            f"QPushButton:pressed {{"
            f"  background-color: #000000;"
            f"  color: {border};"
            f"}}"
        )
        return btn

    def _handle(self, action: str, signal: pyqtSignal) -> None:
        """Emit the Qt signal then fire the REST call (best-effort)."""
        signal.emit()
        self._post(action)

    def _post(self, action: str) -> None:
        endpoint = _ENDPOINTS.get(action)
        if not endpoint:
            logger.error("Bilinmeyen aksiyon: %s", action)
            return

        url = f"{_ET_ADDRESS}{endpoint}"
        try:
            resp = requests.post(url, timeout=2)
            if resp.ok:
                self._lbl_status.setText(f"✓ {action} gönderildi")
                logger.info("ET komutu gönderildi: POST %s → %d", url, resp.status_code)
            else:
                self._lbl_status.setText(f"⚠ HTTP {resp.status_code}")
                logger.warning(
                    "ET komutu başarısız: POST %s → %d", url, resp.status_code
                )
        except requests.exceptions.ConnectionError:
            self._lbl_status.setText("⚠ ET sistemine bağlanılamadı")
            logger.error("ET bağlantı hatası: %s", url)
        except requests.exceptions.Timeout:
            self._lbl_status.setText("⚠ ET zaman aşımı")
            logger.error("ET zaman aşımı: %s", url)
        except Exception as exc:
            self._lbl_status.setText("⚠ Hata")
            logger.error("ET beklenmeyen hata: %s — %s", url, exc)