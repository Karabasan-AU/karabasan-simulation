"""
et_system/tests/test_jammer.py — Jammer birim testleri

Ağ portu açılmaz — ZMQ tamamen mock'lanır.
"""

import json
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from et_system.duty_cycle import DutyCycleGuard
from et_system.jammer import Jammer


class TestJammer(unittest.TestCase):

    def setUp(self):
        """Her test için temiz Jammer ve mock ZMQ soketi."""
        self.mock_pub = MagicMock()
        self.duty = DutyCycleGuard(max_tx_seconds=30.0, cooldown_seconds=0.1)
        self.jammer = Jammer(zmq_pub=self.mock_pub, duty_guard=self.duty)

    def tearDown(self):
        """Test sonrası TX temizle."""
        if self.jammer._active:
            self.jammer.stop()

    # ------------------------------------------------------------------
    # Gürültü üretimi testleri
    # ------------------------------------------------------------------

    def test_generate_noise_dtype(self):
        """Üretilen gürültünün complex64 tipinde olduğunu doğrular."""
        noise = self.jammer._generate_noise(power_w=20.0)
        self.assertEqual(noise.dtype, np.complex64, "Gürültü tipi complex64 olmalı.")

    def test_generate_noise_length(self):
        """Üretilen gürültünün FRAME_SIZE uzunluğunda olduğunu doğrular."""
        noise = self.jammer._generate_noise(power_w=20.0)
        self.assertEqual(len(noise), Jammer.FRAME_SIZE)

    def test_generate_noise_power(self):
        """
        Üretilen gürültü gücünün hedef değere yakın olduğunu doğrular.

        σ² = power_w / 2 (I ve Q bileşeni için eşit dağılım)
        Toplam güç: E[|x|²] = E[I²] + E[Q²] = σ² + σ² = power_w
        """
        power_w = 20.0
        # Büyük N ile istatistiksel kararlılık sağla
        samples = np.concatenate([
            self.jammer._generate_noise(power_w) for _ in range(100)
        ])
        measured_power = np.mean(np.abs(samples) ** 2)
        # %20 tolerans — istatistiksel dağılım nedeniyle
        self.assertAlmostEqual(measured_power, power_w, delta=power_w * 0.2)

    def test_generate_noise_not_zero(self):
        """Trivial pass kontrolü — gürültü tamamen sıfır olmamalı."""
        noise = self.jammer._generate_noise(power_w=20.0)
        self.assertGreater(np.std(np.abs(noise)), 0.0, "Gürültü sıfır dönüyor!")

    # ------------------------------------------------------------------
    # ZMQ mesaj formatı testleri
    # ------------------------------------------------------------------

    def test_build_zmq_message_format(self):
        """ZMQ mesajının header+IQ formatında oluşturulduğunu doğrular."""
        iq = self.jammer._generate_noise(power_w=10.0)
        msg = self.jammer._build_zmq_message("CONTINUOUS", 433e6, iq)

        # İlk 4 byte header uzunluğu
        header_len = int.from_bytes(msg[:4], "big")
        header_bytes = msg[4:4 + header_len]
        iq_bytes = msg[4 + header_len:]

        # Header geçerli JSON mı?
        header = json.loads(header_bytes.decode("utf-8"))
        self.assertEqual(header["mode"], "CONTINUOUS")
        self.assertAlmostEqual(header["frequency_hz"], 433e6)
        self.assertIn("timestamp", header)

        # IQ kısmı doğru boyutta mı?
        iq_recovered = np.frombuffer(iq_bytes, dtype=np.complex64)
        self.assertEqual(len(iq_recovered), Jammer.FRAME_SIZE)

    def test_build_zmq_message_barrage_has_bandwidth(self):
        """Baraj modunda mesajda bandwidth_hz alanı olduğunu doğrular."""
        iq = self.jammer._generate_noise(power_w=10.0)
        msg = self.jammer._build_zmq_message(
            "BARRAGE", 433e6, iq, bandwidth_hz=10e6
        )
        header_len = int.from_bytes(msg[:4], "big")
        header = json.loads(msg[4:4 + header_len].decode("utf-8"))
        self.assertEqual(header["bandwidth_hz"], 10e6)

    # ------------------------------------------------------------------
    # Karıştırma modları — durum testleri
    # ------------------------------------------------------------------

    def test_start_continuous_sets_active(self):
        """Sürekli karıştırma başlatıldığında active=True ve mode=CONTINUOUS olur."""
        self.jammer.start_continuous(frequency_hz=433e6, power_w=20.0)
        status = self.jammer.status()
        self.assertTrue(status["active"])
        self.assertEqual(status["mode"], "CONTINUOUS")

    def test_start_barrage_sets_active(self):
        """Baraj karıştırma başlatıldığında active=True ve mode=BARRAGE olur."""
        self.jammer.start_barrage(frequency_hz=433e6, bandwidth_hz=10e6)
        status = self.jammer.status()
        self.assertTrue(status["active"])
        self.assertEqual(status["mode"], "BARRAGE")

    def test_start_interleaved_sets_active(self):
        """Arabakışlı karıştırma başlatıldığında active=True ve mode=INTERLEAVED olur."""
        self.jammer.start_interleaved(frequency_hz=433e6)
        status = self.jammer.status()
        self.assertTrue(status["active"])
        self.assertEqual(status["mode"], "INTERLEAVED")

    def test_stop_clears_active(self):
        """Durdurma sonrası active=False ve mode=None olur."""
        self.jammer.start_continuous(frequency_hz=433e6)
        self.jammer.stop()
        status = self.jammer.status()
        self.assertFalse(status["active"])
        self.assertIsNone(status["mode"])

    def test_initial_status_inactive(self):
        """Başlangıçta karıştırıcı pasif olmalı."""
        status = self.jammer.status()
        self.assertFalse(status["active"])
        self.assertIsNone(status["mode"])

    # ------------------------------------------------------------------
    # DutyCycleGuard entegrasyonu
    # ------------------------------------------------------------------

    def test_duty_guard_blocks_second_request(self):
        """
        Cooldown sırasında ikinci TX isteği RuntimeError fırlatmalı.
        """
        import time
        self.jammer.start_continuous(frequency_hz=433e6)
        self.jammer.stop()

        # Cooldown süresi 0.1 s — hemen ikinci istek
        with self.assertRaises(RuntimeError):
            self.jammer.start_continuous(frequency_hz=433e6)

    def test_duty_guard_allows_after_cooldown(self):
        """Cooldown sonrası TX tekrar izin verilmeli."""
        import time
        self.jammer.start_continuous(frequency_hz=433e6)
        self.jammer.stop()
        time.sleep(0.15)  # cooldown_seconds=0.1 bekliyoruz
        # RuntimeError fırlatmamalı
        self.jammer.start_continuous(frequency_hz=433e6)
        self.assertTrue(self.jammer.status()["active"])


if __name__ == "__main__":
    unittest.main()