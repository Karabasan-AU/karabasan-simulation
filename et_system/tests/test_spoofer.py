"""
et_system/tests/test_spoofer.py — Spoofer birim testleri

Ağ portu açılmaz — ZMQ tamamen mock'lanır.
"""

import json
import unittest
from unittest.mock import MagicMock
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from et_system.duty_cycle import DutyCycleGuard
from et_system.spoofer import Spoofer, _GPS_PRN_LENGTH


class TestSpoofer(unittest.TestCase):

    def setUp(self):
        self.mock_pub = MagicMock()
        self.duty = DutyCycleGuard(max_tx_seconds=30.0, cooldown_seconds=0.1)
        self.spoofer = Spoofer(zmq_pub=self.mock_pub, duty_guard=self.duty)

    def tearDown(self):
        if self.spoofer._active:
            self.spoofer.stop()

    def test_prn_length(self):
        """C/A PRN kodunun 1023 chip uzunluğunda olduğunu doğrular."""
        for prn_id in range(1, 5):
            code = self.spoofer._generate_prn(prn_id)
            self.assertEqual(len(code), _GPS_PRN_LENGTH)

    def test_prn_values_bpsk(self):
        """C/A kodunun yalnızca +1 ve -1 değerleri içerdiğini doğrular."""
        for prn_id in range(1, 5):
            code = self.spoofer._generate_prn(prn_id)
            unique_vals = set(np.unique(code))
            self.assertEqual(unique_vals, {-1.0, 1.0})

    def test_prn_autocorrelation_peak(self):
        """Otokorelasyon tepe değerinin yan loblardan çok büyük olduğunu doğrular."""
        code = self.spoofer._generate_prn(1)
        autocorr = np.correlate(code, code, mode="full")
        peak = autocorr[len(autocorr) // 2]
        side_max = np.max(np.abs(
            np.concatenate([autocorr[:len(autocorr)//2 - 10],
                            autocorr[len(autocorr)//2 + 10:]])
        ))
        self.assertGreater(peak, side_max * 5)

    def test_prn_codes_different(self):
        """Farklı PRN ID'lerinin farklı kodlar ürettiğini doğrular."""
        code1 = self.spoofer._generate_prn(1)
        code2 = self.spoofer._generate_prn(2)
        self.assertFalse(np.array_equal(code1, code2))

    def test_start_voice_sets_active(self):
        """Ses aldatma başlatıldığında active=True ve mode=VOICE_SPOOF olur."""
        self.spoofer.start_voice(frequency_hz=145e6, ctcss_hz=88.5)
        status = self.spoofer.status()
        self.assertTrue(status["active"])
        self.assertEqual(status["mode"], "VOICE_SPOOF")

    def test_stop_clears_active(self):
        """Durdurma sonrası active=False ve mode=None olur."""
        self.spoofer.start_voice(frequency_hz=145e6)
        self.spoofer.stop()
        status = self.spoofer.status()
        self.assertFalse(status["active"])
        self.assertIsNone(status["mode"])

    def test_start_gnss_sets_active(self):
        """GNSS aldatma başlatıldığında active=True ve mode=GNSS_SPOOF olur."""
        self.spoofer.start_gnss(target_lat=39.925, target_lon=32.837)
        status = self.spoofer.status()
        self.assertTrue(status["active"])
        self.assertEqual(status["mode"], "GNSS_SPOOF")

    def test_initial_status_inactive(self):
        """Başlangıçta spoofer pasif olmalı."""
        status = self.spoofer.status()
        self.assertFalse(status["active"])
        self.assertIsNone(status["mode"])

    def test_duty_guard_blocks_during_cooldown(self):
        """Cooldown sırasında ikinci aldatma isteği RuntimeError fırlatmalı."""
        self.spoofer.start_voice(frequency_hz=145e6)
        self.spoofer.stop()
        with self.assertRaises(RuntimeError):
            self.spoofer.start_gnss(target_lat=39.9, target_lon=32.8)


if __name__ == "__main__":
    unittest.main()