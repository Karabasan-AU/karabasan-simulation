"""
et_system/spoofer.py — RF Aldatma Modülü

Analog telsiz ses aldatma (replay + ses enjeksiyonu) ve
GPS L1 C/A GNSS aldatma modlarını yönetir.

ED ile ilişki:
    ed_system/src/sensor_fusion.py'den gelen et.trigger →
    analog telsiz parametreleri ed.params topic'inden okunur (frequency_hz, ctcss_hz)
    GNSS aldatma sim_engine üzerinden GPS L1 bandını etkiler.
"""

import json
import threading
import time
import struct

import numpy as np
import zmq

from shared.logger import get_logger
from et_system.duty_cycle import DutyCycleGuard

logger = get_logger("et_system.spoofer")

# GPS L1 sabitleri
_GPS_L1_FREQ_HZ = 1_575_420_000.0
_GPS_CHIP_RATE = 1_023_000       # 1.023 Mcps
_GPS_NAV_RATE = 50               # 50 bps navigasyon mesajı
_GPS_PRN_LENGTH = 1023           # C/A kodu uzunluğu

# GPS Gold kodu üreteci için register başlangıç değerleri (PRN 1-4)
_GPS_PRN_G2_TAPS = {
    1:  [2, 6],
    2:  [3, 7],
    3:  [4, 8],
    4:  [5, 9],
}


class Spoofer:
    """
    RF Aldatma sınıfı.

    Parametreler
    ----------
    zmq_pub : zmq.Socket
        et_to_sim ZMQ PUB soketi.
    duty_guard : DutyCycleGuard
        TX süresi koruyucu.
    """

    def __init__(self, zmq_pub: zmq.Socket, duty_guard: DutyCycleGuard):
        self._pub = zmq_pub
        self._duty = duty_guard
        self._active = False
        self._mode: str | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_voice(
        self,
        frequency_hz: float,
        ctcss_hz: float = 88.5,
        audio_file: str = "inject.wav",
    ) -> None:
        """
        Analog telsiz ses aldatma başlat.

        NBFM modülasyonu:
            s(t) = Ac · cos(2π·fc·t + 2π·kf·∫m(τ)dτ)
            Bant genişliği: BW ≈ 2(Δf + fm) — Carson kuralı
            NBFM için Δf ≈ 2.5 kHz, fm ≈ 3.5 kHz → BW ≈ 12 kHz

        CTCSS tonu hedef telsizin squelch kapısını açmak için zorunludur.
        """
        self._ensure_stopped()
        self._duty.request_tx()

        self._active = True
        self._mode = "VOICE_SPOOF"
        self._stop_event.clear()

        logger.info(
            "Ses aldatma başlatıldı — frekans: %.3f MHz, CTCSS: %.1f Hz, dosya: %s",
            frequency_hz / 1e6,
            ctcss_hz,
            audio_file,
        )

        self._thread = threading.Thread(
            target=self._voice_loop,
            args=(frequency_hz, ctcss_hz, audio_file),
            daemon=True,
        )
        self._thread.start()

    def start_gnss(
        self,
        target_lat: float,
        target_lon: float,
        target_alt_m: float = 100.0,
        num_sats: int = 4,
    ) -> None:
        """
        GPS L1 C/A GNSS aldatma başlat.

        Sinyal modeli:
            s_L1(t) = √(2Ps) · d(t) · c(t) · cos(2π·fL1·t + φ₀)
            d(t): navigasyon mesajı (manipüle konum)
            c(t): C/A PRN kodu (1023 chip, 1 ms periyot)
            fL1 = 1575.42 MHz

        İki aşamalı yaklaşım:
            1. Hafif L1 karıştırma → alıcı kilit kaybeder
            2. Sahte sinyal → alıcı sahte konuma kilit oluşturur

        Minimum 4 uydu eş zamanlı üretilir (3D konum + zaman çözümü için).
        """
        self._ensure_stopped()
        self._duty.request_tx()

        self._active = True
        self._mode = "GNSS_SPOOF"
        self._stop_event.clear()

        logger.info(
            "GNSS aldatma başlatıldı — hedef konum: (%.5f, %.5f, %.1f m), uydu sayısı: %d",
            target_lat,
            target_lon,
            target_alt_m,
            num_sats,
        )

        self._thread = threading.Thread(
            target=self._gnss_loop,
            args=(target_lat, target_lon, target_alt_m, num_sats),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._active = False
        self._duty.release_tx()
        logger.info("Aldatma durduruldu — mod: %s", self._mode)
        self._mode = None

    def status(self) -> dict:
        return {"active": self._active, "mode": self._mode}

    # ------------------------------------------------------------------
    # Ses aldatma döngüsü
    # ------------------------------------------------------------------

    def _voice_loop(
        self,
        frequency_hz: float,
        ctcss_hz: float,
        audio_file: str,
    ) -> None:
        """
        NBFM ses enjeksiyonu döngüsü.

        Gerçek donanımda: WAV → CTCSS ekle → NBFM mod → HackRF TX
        Simülasyonda: sentetik NBFM I/Q üret → ZMQ'ya gönder
        """
        sample_rate = 2_400_000
        audio_rate = 8_000
        deviation_hz = 2_500.0

        logger.debug(
            "Ses enjeksiyonu — NBFM sapma: %.0f Hz, CTCSS: %.1f Hz",
            deviation_hz,
            ctcss_hz,
        )

        frame_duration = 1024 / sample_rate  # her frame'in süresi
        t = 0.0

        while not self._stop_event.is_set():
            if not self._duty.tx_allowed():
                time.sleep(0.1)
                continue

            # Ses sinyali simülasyonu: 1 kHz test tonu + CTCSS
            t_arr = np.arange(1024) / sample_rate + t
            audio = (
                0.7 * np.sin(2 * np.pi * 1000 * t_arr)       # 1 kHz ses
                + 0.1 * np.sin(2 * np.pi * ctcss_hz * t_arr)  # CTCSS alt tonu
            )

            # NBFM modülasyonu: FM integral → karmaşık I/Q
            phase = 2 * np.pi * deviation_hz / sample_rate * np.cumsum(audio)
            iq = np.exp(1j * phase).astype(np.complex64)

            msg = self._build_zmq_message("VOICE_SPOOF", frequency_hz, iq)
            self._pub.send_multipart([b"et.iq", msg])

            t += frame_duration

    # ------------------------------------------------------------------
    # GNSS aldatma döngüsü
    # ------------------------------------------------------------------

    def _gnss_loop(
        self,
        target_lat: float,
        target_lon: float,
        target_alt_m: float,
        num_sats: int,
    ) -> None:
        """
        GPS L1 C/A aldatma döngüsü.

        Her iterasyonda num_sats uyduya ait PRN kodları üretilir,
        BPSK modülasyonu uygulanır ve koherent olarak toplanır.

        Link bütçesi:
            Gerçek GPS: -130 dBm ila -125 dBm
            Hedef aldatma gücü: -122 dBm (DSR > 3 dB)
            P_TX = P_hedef - G_TX - G_RX + FSPL + kayıplar
            10 m mesafe, 1575.42 MHz → FSPL ≈ 56.4 dB
            → P_TX ≈ -66.6 dBm (PA gerektirmez)
        """
        sample_rate = 2_400_000
        # Normalize chip hızı
        chips_per_sample = _GPS_CHIP_RATE / sample_rate  # ≈ 0.426

        logger.info(
            "GPS L1 C/A üretimi — %d uydu, hedef: (%.5f, %.5f)",
            num_sats,
            target_lat,
            target_lon,
        )

        prn_codes = [
            self._generate_prn(prn_id)
            for prn_id in range(1, num_sats + 1)
        ]

        frame_idx = 0

        while not self._stop_event.is_set():
            if not self._duty.tx_allowed():
                time.sleep(0.1)
                continue

            combined = np.zeros(1024, dtype=np.complex64)

            for prn_id, prn_code in enumerate(prn_codes, start=1):
                # Doppler kayması simülasyonu (±4 kHz arası)
                doppler_hz = np.random.uniform(-4000, 4000)

                # C/A kodu örnekleme
                chip_indices = (
                    np.arange(1024) * chips_per_sample
                ).astype(int) % _GPS_PRN_LENGTH
                ca_chips = prn_code[chip_indices].astype(np.float32)

                # BPSK: d(t)·c(t) — navigasyon mesajı sabit +1 (manipüle konum)
                nav_bit = 1.0  # manipüle edilmiş navigasyon biti
                bpsk = nav_bit * ca_chips

                # Taşıyıcı + Doppler
                t_arr = np.arange(1024) / sample_rate
                carrier = np.exp(
                    1j * 2 * np.pi * doppler_hz * t_arr
                ).astype(np.complex64)

                combined += (bpsk * carrier).astype(np.complex64)

                logger.debug(
                    "PRN %d üretildi — Doppler: %.0f Hz", prn_id, doppler_hz
                )

            # Normalize et
            max_amp = np.max(np.abs(combined))
            if max_amp > 0:
                combined = (combined / max_amp * 0.1).astype(np.complex64)

            header = {
                "mode": "GNSS_SPOOF",
                "frequency_hz": _GPS_L1_FREQ_HZ,
                "target_lat": target_lat,
                "target_lon": target_lon,
                "target_alt_m": target_alt_m,
                "num_sats": num_sats,
                "timestamp": time.time(),
            }
            header_bytes = json.dumps(header).encode("utf-8")
            header_len = len(header_bytes).to_bytes(4, "big")
            msg = header_len + header_bytes + combined.tobytes()
            self._pub.send_multipart([b"et.iq", msg])

            frame_idx += 1
            if frame_idx % 100 == 0:
                logger.info(
                    "GNSS aldatma aktif — %d frame gönderildi, hedef: (%.5f, %.5f)",
                    frame_idx,
                    target_lat,
                    target_lon,
                )

    # ------------------------------------------------------------------
    # Yardımcı metodlar
    # ------------------------------------------------------------------

    def _generate_prn(self, prn_id: int) -> np.ndarray:
        """
        GPS C/A Gold kodu üret.

        G1 ve G2 kaydedicilerinin XOR'u ile 1023-chip PRN kodu üretilir.
        Çip değerleri: 0 → +1, 1 → -1 (BPSK eşlemesi)
        """
        if prn_id not in _GPS_PRN_G2_TAPS:
            # Desteklenmeyen PRN için rastgele Gold kodu benzeri dizi
            logger.warning("PRN %d için standart tap yok, yaklaşık kod üretiliyor.", prn_id)
            rng = np.random.default_rng(seed=prn_id)
            bits = rng.integers(0, 2, _GPS_PRN_LENGTH)
            return 1 - 2 * bits  # 0→+1, 1→-1

        taps = _GPS_PRN_G2_TAPS[prn_id]

        g1 = [1] * 10
        g2 = [1] * 10
        code = np.zeros(_GPS_PRN_LENGTH, dtype=np.int8)

        for i in range(_GPS_PRN_LENGTH):
            # G1 çıkışı: bit 10
            g1_out = g1[9]
            # G2 çıkışı: seçilen tap'lerin XOR'u
            g2_out = g2[taps[0] - 1] ^ g2[taps[1] - 1]
            # C/A çipi
            chip = g1_out ^ g2_out
            code[i] = chip

            # G1 geri besleme: bit 3 XOR bit 10
            g1_fb = g1[2] ^ g1[9]
            g1 = [g1_fb] + g1[:-1]

            # G2 geri besleme: bit 2,3,6,8,9,10 XOR
            g2_fb = g2[1] ^ g2[2] ^ g2[5] ^ g2[7] ^ g2[8] ^ g2[9]
            g2 = [g2_fb] + g2[:-1]

        # 0 → +1, 1 → -1
        return 1 - 2 * code.astype(np.float32)

    def _build_zmq_message(
        self,
        mode: str,
        frequency_hz: float,
        iq: np.ndarray,
    ) -> bytes:
        header = {
            "mode": mode,
            "frequency_hz": frequency_hz,
            "timestamp": time.time(),
        }
        header_bytes = json.dumps(header).encode("utf-8")
        header_len = len(header_bytes).to_bytes(4, "big")
        return header_len + header_bytes + iq.tobytes()

    def _ensure_stopped(self) -> None:
        if self._active:
            self.stop()
            if self._thread:
                self._thread.join(timeout=2)