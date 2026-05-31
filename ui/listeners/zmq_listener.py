import json
import threading

from PyQt5.QtCore import QThread, pyqtSignal
import websocket  # websocket-client library

from shared.logger import get_logger
import json as _json
import os

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Load WebSocket address from shared config at import time
# ---------------------------------------------------------------------------

def _load_ws_address() -> str:
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "shared", "config.json"
    )
    try:
        with open(os.path.abspath(config_path)) as f:
            cfg = _json.load(f)
        address = cfg["sockets"]["ed_to_ui"]["address"]
        logger.info("WebSocket adresi yüklendi: %s", address)
        return address
    except Exception as exc:
        logger.error(
            "config.json okunamadı, varsayılan adres kullanılıyor: %s", exc
        )
        return "ws://localhost:8765"


_WS_ADDRESS = _load_ws_address()

# ---------------------------------------------------------------------------
# Event type routing
# ---------------------------------------------------------------------------

# These event types carry signal_id and are forwarded as target_received
_TARGET_TYPES = {"detection", "location"}


class ZMQListener(QThread):
    """
    Background thread that maintains a WebSocket connection to ed_system
    and emits Qt signals for each incoming event type.

    Despite the legacy name (zmq_listener.py), transport is WebSocket.

    Signals:
        spectrum_received(list, list)  — freqs, amplitudes
        target_received(dict)          — detection or location event
        df_received(int)               — azimuth_deg as int
        sigint_received(dict)          — any event forwarded to log console
    """

    spectrum_received = pyqtSignal(list, list)
    target_received   = pyqtSignal(dict)
    df_received       = pyqtSignal(int)
    sigint_received   = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._ws: websocket.WebSocketApp | None = None

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        logger.info("ZMQListener başlatıldı, bağlanılıyor: %s", _WS_ADDRESS)
        while not self._stop_event.is_set():
            try:
                self._ws = websocket.WebSocketApp(
                    _WS_ADDRESS,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                # run_forever blocks until the connection drops or
                # dispatcher calls self._ws.close()
                self._ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as exc:
                logger.error("WebSocket bağlantı hatası: %s", exc)

            if self._stop_event.is_set():
                break

            logger.info("WebSocket bağlantısı kesildi, 3 saniye sonra yeniden denenecek.")
            self._stop_event.wait(timeout=3)

        logger.info("ZMQListener durdu.")

    # ------------------------------------------------------------------
    # Public control
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Signal the thread to stop and close the WebSocket cleanly."""
        logger.info("ZMQListener durdurma isteği alındı.")
        self._stop_event.set()
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception as exc:
                logger.warning("WebSocket kapatılırken hata: %s", exc)

    # ------------------------------------------------------------------
    # WebSocketApp callbacks
    # ------------------------------------------------------------------

    def _on_open(self, ws) -> None:
        logger.info("WebSocket bağlantısı kuruldu: %s", _WS_ADDRESS)

    def _on_message(self, ws, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Geçersiz JSON alındı: %s — %s", exc, raw[:120])
            return

        event_type = data.get("type", "")

        # Always forward to log console
        self.sigint_received.emit(data)

        if event_type == "spectrum":
            self._handle_spectrum(data)

        elif event_type in _TARGET_TYPES:
            self.target_received.emit(data)
            if event_type == "location":
                self._handle_location(data)

        elif event_type == "demodulation":
            # audio_chunk_b64 is large — log console receives the dict
            # but we do not emit a dedicated signal for audio playback yet
            logger.debug("Demodülasyon chunk alındı: id=%s", data.get("signal_id"))

        elif event_type == "jamming_status":
            logger.debug(
                "Jamming durum: active=%s mode=%s jsr=%s",
                data.get("active"), data.get("mode"), data.get("jsr_db"),
            )

        else:
            logger.warning("Bilinmeyen olay tipi: %s", event_type)

    def _on_error(self, ws, error) -> None:
        logger.error("WebSocket hatası: %s", error)

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        logger.info(
            "WebSocket kapatıldı: kod=%s mesaj=%s",
            close_status_code, close_msg,
        )

    # ------------------------------------------------------------------
    # Per-type handlers
    # ------------------------------------------------------------------

    def _handle_spectrum(self, data: dict) -> None:
        freqs      = data.get("freqs", [])
        amplitudes = data.get("amplitudes", [])
        if not freqs or not amplitudes:
            logger.warning("Spektrum verisi eksik alanlar içeriyor, atlanıyor.")
            return
        if len(freqs) != len(amplitudes):
            logger.warning(
                "Spektrum freqs(%d) / amplitudes(%d) uzunluk uyuşmazlığı.",
                len(freqs), len(amplitudes),
            )
            return
        self.spectrum_received.emit(freqs, amplitudes)

    def _handle_location(self, data: dict) -> None:
        azimuth = data.get("azimuth_deg")
        if azimuth is None:
            logger.warning(
                "Konum eventi azimuth_deg içermiyor: id=%s", data.get("signal_id")
            )
            return
        try:
            self.df_received.emit(int(round(float(azimuth))))
        except (TypeError, ValueError) as exc:
            logger.warning("azimuth_deg dönüştürülemedi: %s — %s", azimuth, exc)