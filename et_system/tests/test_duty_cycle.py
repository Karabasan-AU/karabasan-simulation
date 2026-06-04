"""
et_system/tests/test_duty_cycle.py — DutyCycleGuard birim testleri
"""

import time
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from et_system.duty_cycle import DutyCycleGuard


class TestDutyCycleGuard(unittest.TestCase):

    def test_initial_status(self):
        """Başlangıçta TX pasif, cooldown yok."""
        guard = DutyCycleGuard()
        status = guard.status()
        self.assertFalse(status["tx_active"])
        self.assertEqual(status["cooldown_remaining_s"], 0.0)

    def test_request_tx_sets_active(self):
        """request_tx sonrası tx_active=True olur."""
        guard = DutyCycleGuard()
        guard.request_tx()
        self.assertTrue(guard.status()["tx_active"])
        guard.release_tx()

    def test_release_tx_starts_cooldown(self):
        """release_tx sonrası cooldown başlar."""
        guard = DutyCycleGuard(cooldown_seconds=5.0)
        guard.request_tx()
        guard.release_tx()
        status = guard.status()
        self.assertFalse(status["tx_active"])
        self.assertGreater(status["cooldown_remaining_s"], 0.0)

    def test_request_during_cooldown_raises(self):
        """Cooldown sırasında request_tx RuntimeError fırlatmalı."""
        guard = DutyCycleGuard(cooldown_seconds=5.0)
        guard.request_tx()
        guard.release_tx()
        with self.assertRaises(RuntimeError):
            guard.request_tx()

    def test_tx_allowed_returns_false_when_inactive(self):
        """TX başlatılmadan tx_allowed() False döner."""
        guard = DutyCycleGuard()
        self.assertFalse(guard.tx_allowed())

    def test_tx_allowed_returns_true_when_active(self):
        """TX başlatıldıktan sonra tx_allowed() True döner."""
        guard = DutyCycleGuard(max_tx_seconds=30.0)
        guard.request_tx()
        self.assertTrue(guard.tx_allowed())
        guard.release_tx()

    def test_max_tx_exceeded_stops_tx(self):
        """
        max_tx_seconds aşılınca tx_allowed() False döner
        ve TX zorla durdurulur.
        """
        guard = DutyCycleGuard(max_tx_seconds=0.1, cooldown_seconds=0.1)
        guard.request_tx()
        time.sleep(0.15)  # max_tx_seconds aş
        self.assertFalse(guard.tx_allowed())
        self.assertFalse(guard.status()["tx_active"])

    def test_allowed_after_cooldown(self):
        """Cooldown bittikten sonra request_tx başarılı olmalı."""
        guard = DutyCycleGuard(max_tx_seconds=30.0, cooldown_seconds=0.1)
        guard.request_tx()
        guard.release_tx()
        time.sleep(0.15)
        guard.request_tx()  # RuntimeError fırlatmamalı
        self.assertTrue(guard.status()["tx_active"])
        guard.release_tx()

    def test_release_without_request_safe(self):
        """TX başlatılmadan release_tx çağrılması hata vermemeli."""
        guard = DutyCycleGuard()
        guard.release_tx()  # sessizce geçmeli


if __name__ == "__main__":
    unittest.main()