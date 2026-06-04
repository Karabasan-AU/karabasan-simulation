"""
et_system/duty_cycle.py — TX Süresi Koruyucu

TASKS.md'de "en önemli güvence" olarak tanımlanmıştır.
Sürekli TX modunda SDR donanımının aşırı ısınmasını önler.

Mantık:
    - Her TX isteğinde toplam TX süresi izlenir.
    - max_tx_seconds aşılırsa TX reddedilir, cooldown beklenir.
    - cooldown_seconds sonra TX tekrar izin verilir.
"""

import threading
import time

from shared.logger import get_logger

logger = get_logger("et_system.duty_cycle")


class DutyCycleGuard:
    """
    Donanım koruma mekanizması.

    Parametreler
    ----------
    max_tx_seconds : float
        Kesintisiz maksimum TX süresi (saniye). Varsayılan: 30 s.
    cooldown_seconds : float
        TX sonrası zorunlu bekleme süresi (saniye). Varsayılan: 10 s.
    """

    def __init__(
        self,
        max_tx_seconds: float = 30.0,
        cooldown_seconds: float = 10.0,
    ):
        self._max_tx = max_tx_seconds
        self._cooldown = cooldown_seconds

        self._tx_active = False
        self._tx_start: float | None = None
        self._cooldown_until: float = 0.0
        self._lock = threading.Lock()

        logger.info(
            "DutyCycleGuard başlatıldı — maks TX: %.0f s, soğuma: %.0f s",
            max_tx_seconds,
            cooldown_seconds,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def request_tx(self) -> None:
        """
        TX başlatma isteği.

        Cooldown süresindeyse RuntimeError fırlatır.
        """
        with self._lock:
            now = time.time()

            if now < self._cooldown_until:
                remaining = self._cooldown_until - now
                logger.warning(
                    "TX reddedildi — soğuma süresi: %.1f s kaldı", remaining
                )
                raise RuntimeError(
                    f"Donanım soğuma süresinde. {remaining:.1f} saniye bekleyin."
                )

            self._tx_active = True
            self._tx_start = now
            logger.info("TX başlatıldı — maks süre: %.0f s", self._max_tx)

    def release_tx(self) -> None:
        """TX serbest bırak, cooldown başlat."""
        with self._lock:
            if not self._tx_active:
                return

            tx_duration = time.time() - (self._tx_start or time.time())
            self._tx_active = False
            self._tx_start = None
            self._cooldown_until = time.time() + self._cooldown

            logger.info(
                "TX durduruldu — toplam TX süresi: %.1f s, soğuma: %.0f s",
                tx_duration,
                self._cooldown,
            )

    def tx_allowed(self) -> bool:
        """
        TX devam edebilir mi?

        max_tx_seconds aşıldıysa False döner ve otomatik release yapar.
        """
        with self._lock:
            if not self._tx_active:
                return False

            elapsed = time.time() - (self._tx_start or time.time())

            if elapsed >= self._max_tx:
                logger.warning(
                    "Maks TX süresi aşıldı (%.1f s >= %.0f s), TX zorla durduruluyor.",
                    elapsed,
                    self._max_tx,
                )
                self._tx_active = False
                self._cooldown_until = time.time() + self._cooldown
                return False

            return True

    def status(self) -> dict:
        with self._lock:
            now = time.time()
            elapsed = (
                now - self._tx_start
                if self._tx_active and self._tx_start
                else 0.0
            )
            cooldown_remaining = max(0.0, self._cooldown_until - now)
            return {
                "tx_active": self._tx_active,
                "tx_elapsed_s": round(elapsed, 2),
                "max_tx_seconds": self._max_tx,
                "cooldown_remaining_s": round(cooldown_remaining, 2),
            }