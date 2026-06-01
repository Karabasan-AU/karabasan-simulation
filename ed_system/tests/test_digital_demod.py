import unittest
import numpy as np
import sys
import os

# src klasörünü yola ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from digital_demod import DigitalDemodulator

class TestDigitalDemodulator(unittest.TestCase):
    def setUp(self):
        self.demod = DigitalDemodulator(sample_rate=2400000)

    def test_qpsk_demodulation_flow(self):
        # 1. 4800 örnekli rastgele QPSK taklidi I/Q verisi oluştur (Sistemi yormadan test et)
        raw_iq = (np.random.randn(4800) + 1j * np.random.randn(4800)).astype(np.complex64)
        
        # 2. Dijital pipeline'a sok (Gardner Clock Recovery + FFT Phase Sync + FEC)
        symbols, payload, crc_valid = self.demod.process_block(raw_iq, "QPSK_FAST_DRONE")
        
        # --- KABUL KRİTERLERİ ---
        # Saat geri kazanımı (Clock recovery) sonrası sembol dizisinin boş dönmediğini doğrula
        self.assertGreater(len(symbols), 0, "Senkronize semboller üretilemedi!")
        
        # Çıktının kompleks sayı (complex64) formatında olduğunu doğrula
        self.assertEqual(symbols.dtype, np.complex64, "Sembol çıktısı kompleks sayı olmalı!")
        
        # Girdiğimiz veri rastgele gürültü olduğu için FEC/CRC'nin başarısız olmasını bekliyoruz.
        # Bu test, sistemin çökmeden hatalı paketi doğru şekilde drop ettiğini kanıtlar.
        self.assertFalse(crc_valid, "Rastgele gürültüde CRC yanlışlıkla başarılı oldu!")
        self.assertIsNone(payload, "Geçersiz pakette payload None dönmeli!")

if __name__ == '__main__':
    unittest.main()