
import json
import threading
import time

import numpy as np
import zmq

from shared.logger import get_logger
from et_system.duty_cycle import DutyCycleGuard

logger = get_logger("et_system.jammer")


class Jammer:
    """
    RF Karıştırma sınıfı.

    Parametreler
    ----------
    zmq_pub : zmq.Socket
        et_to_sim ZMQ PUB soketi — main.py tarafından enjekte edilir.
    duty_guard : DutyCycleGuard
        TX süresi koruyucu — donanım aşırı ısınma önlemi.
    """

    FRAME_SIZE = 1024  # I/Q örnek sayısı

    def __init__(self, zmq_pub: zmq.Socket, duty_guard: DutyCycleGuard):
        self._pub = zmq_pub
        self._duty = duty_guard
        self._active = False
        self._mode: str | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start_continuous(
        self,
        frequency_hz: float,
        power_w: float = 20.0,
        duration_s: float | None = None,
    ) -> None:
        """
        Sürekli karıştırma başlat.

        JSR analizi:
            Tüm PA gücü tek hedefe yönlendirilir → maksimum JSR.
            JSR(dB) = [Pj + Gj] - [Ps + Gs] + 20·log10(Rs/Rj)
        """
        self._ensure_stopped()
        self._duty.request_tx()  # DutyCycleGuard onayı — reddederse RuntimeError

        self._active = True
        self._mode = "CONTINUOUS"
        self._stop_event.clear()

        logger.info(
            "Sürekli karıştırma başlatıldı — frekans: %.3f MHz, güç: %.1f W",
            frequency_hz / 1e6,
            power_w,
        )

        self._thread = threading.Thread(
            target=self._tx_loop,
            args=(frequency_hz, power_w, duration_s, "CONTINUOUS"),
            daemon=True,
        )
        self._thread.start()

    def start_barrage(
        self,
        frequency_hz: float,
        bandwidth_hz: float = 10_000_000.0,
        power_w: float = 20.0,
        duration_s: float | None = None,
    ) -> None:
        """
        Baraj karıştırma başlat.

        Güç yoğunluğu kaybı:
            J_baraj = P_PA / B_baraj
            B_baraj = 10 MHz, B_hedef = 200 kHz için
            ΔJ = 10·log10(10e6/200e3) ≈ 17 dB kayıp
            → sabit frekanslı dar bant hedeflere karşı tekli mod daha etkin.
            → frekans belirsiz hedeflere karşı baraj mod tercih edilir.
        """
        self._ensure_stopped()
        self._duty.request_tx()

        self._active = True
        self._mode = "BARRAGE"
        self._stop_event.clear()

        logger.info(
            "Baraj karıştırma başlatıldı — merkez: %.3f MHz, bant: %.1f MHz, güç: %.1f W",
            frequency_hz / 1e6,
            bandwidth_hz / 1e6,
            power_w,
        )

        self._thread = threading.Thread(
            target=self._tx_loop_barrage,
            args=(frequency_hz, bandwidth_hz, power_w, duration_s),
            daemon=True,
        )
        self._thread.start()

    def start_interleaved(
        self,
        frequency_hz: float,
        power_w: float = 20.0,
        tx_ms: int = 90,
        rx_ms: int = 10,
    ) -> None:
        """
        Arabakışlı karıştırma başlat.

        Duty-cycle: DC = tx_ms / (tx_ms + rx_ms) = 90/100 = 0.90
        Ortalama güç: P_ort = DC · P_tepe = 0.9 · 20W = 18W
        JSR kaybı: ΔP = 10·log10(0.9) ≈ -0.46 dB — ihmal edilebilir.

        rx_ms penceresinde ED sistemi dinleme yapar:
            → sinyal varlığı → karıştırma devam
            → sinyal yok → karıştırma durdur
        """
        self._ensure_stopped()
        self._duty.request_tx()

        self._active = True
        self._mode = "INTERLEAVED"
        self._stop_event.clear()

        logger.info(
            "Arabakışlı karıştırma başlatıldı — frekans: %.3f MHz, TX: %d ms, RX: %d ms",
            frequency_hz / 1e6,
            tx_ms,
            rx_ms,
        )

        self._thread = threading.Thread(
            target=self._tx_loop_interleaved,
            args=(frequency_hz, power_w, tx_ms, rx_ms),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._active = False
        self._duty.release_tx()
        logger.info("Karıştırma durduruldu — mod: %s", self._mode)
        self._mode = None

    def status(self) -> dict:
        return {"active": self._active, "mode": self._mode}

    # ------------------------------------------------------------------
    # TX döngüleri
    # ------------------------------------------------------------------

    def _tx_loop(
        self,
        frequency_hz: float,
        power_w: float,
        duration_s: float | None,
        mode: str,
    ) -> None:
        """Sürekli ve tekli karıştırma TX döngüsü."""
        start = time.time()

        while not self._stop_event.is_set():
            if duration_s and (time.time() - start) >= duration_s:
                logger.info("Karıştırma süresi doldu (%.1f s), durduruluyor.", duration_s)
                self.stop()
                break

            if not self._duty.tx_allowed():
                logger.warning("DutyCycleGuard TX'i engelledi, bekleniyor...")
                time.sleep(1)
                continue

            noise = self._generate_noise(power_w)
            msg = self._build_zmq_message(mode, frequency_hz, noise)
            self._pub.send_multipart([b"et.iq", msg])

            logger.debug(
                "TX frame gönderildi — mod: %s, frekans: %.3f MHz",
                mode,
                frequency_hz / 1e6,
            )

    def _tx_loop_barrage(
        self,
        frequency_hz: float,
        bandwidth_hz: float,
        power_w: float,
        duration_s: float | None,
    ) -> None:
        """Baraj karıştırma TX döngüsü — gürültü tüm bant genişliğine yayılır."""
        start = time.time()
        # Güç yoğunluğu bant genişliğine dağıtılır
        power_density = power_w / bandwidth_hz
        logger.debug(
            "Baraj güç yoğunluğu: %.6f W/Hz (toplam: %.1f W, bant: %.1f MHz)",
            power_density,
            power_w,
            bandwidth_hz / 1e6,
        )

        while not self._stop_event.is_set():
            if duration_s and (time.time() - start) >= duration_s:
                self.stop()
                break

            if not self._duty.tx_allowed():
                time.sleep(1)
                continue

            noise = self._generate_noise(power_w)
            msg = self._build_zmq_message(
                "BARRAGE", frequency_hz, noise, bandwidth_hz=bandwidth_hz
            )
            self._pub.send_multipart([b"et.iq", msg])

    def _tx_loop_interleaved(
        self,
        frequency_hz: float,
        power_w: float,
        tx_ms: int,
        rx_ms: int,
    ) -> None:
        """
        Arabakışlı TX döngüsü.

        tx_ms boyunca gürültü ilet → rx_ms boyunca sus (ED dinler).
        """
        while not self._stop_event.is_set():
            if not self._duty.tx_allowed():
                time.sleep(1)
                continue

            # TX fazı
            tx_end = time.time() + tx_ms / 1000
            while time.time() < tx_end and not self._stop_event.is_set():
                noise = self._generate_noise(power_w)
                msg = self._build_zmq_message("INTERLEAVED", frequency_hz, noise)
                self._pub.send_multipart([b"et.iq", msg])

            logger.debug("Arabakışlı RX penceresi — %d ms sessizlik", rx_ms)

            # RX fazı — sadece bekle, ED bu pencerede dinler
            time.sleep(rx_ms / 1000)

    # ------------------------------------------------------------------
    # Yardımcı metodlar
    # ------------------------------------------------------------------

    def _generate_noise(self, power_w: float) -> np.ndarray:
        """
        Gaussian gürültü üret.

        Karmaşık gürültü: N(0, σ²/2) her bileşen için
        σ² = power_w (normalize)
        """
        sigma = np.sqrt(power_w / 2)
        noise = sigma * (
            np.random.randn(self.FRAME_SIZE).astype(np.float32)
            + 1j * np.random.randn(self.FRAME_SIZE).astype(np.float32)
        )
        return noise.astype(np.complex64)

    def _build_zmq_message(
        self,
        mode: str,
        frequency_hz: float,
        iq: np.ndarray,
        bandwidth_hz: float | None = None,
    ) -> bytes:
        """ZMQ mesaj formatı: JSON header + IQ bytes."""
        header = {
            "mode": mode,
            "frequency_hz": frequency_hz,
            "bandwidth_hz": bandwidth_hz,
            "timestamp": time.time(),
        }
        header_bytes = json.dumps(header).encode("utf-8")
        iq_bytes = iq.tobytes()
        # header uzunluğu (4 byte) + header + iq
        header_len = len(header_bytes).to_bytes(4, "big")
        return header_len + header_bytes + iq_bytes

    def _ensure_stopped(self) -> None:
        if self._active:
            self.stop()
            if self._thread:
                self._thread.join(timeout=2)