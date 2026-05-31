import unittest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from fec_decoder import FECDecoder

class TestFECDecoder(unittest.TestCase):
    def setUp(self):
        self.decoder = FECDecoder()

    def test_bit_slicing_qpsk(self):
        # QPSK için 4 bölgeyi (Quadrant) temsil eden kompleks semboller
        # 1+1j -> 1,1 | -1+1j -> 0,1 | -1-1j -> 0,0 | 1-1j -> 1,0
        qpsk_symbols = np.array([1+1j, -1+1j, -1-1j, 1-1j], dtype=np.complex64)
        expected_bits = np.array([1, 1, 0, 1, 0, 0, 1, 0], dtype=np.uint8)
        
        sliced_bits = self.decoder.bit_slicing(qpsk_symbols, "QPSK")
        np.testing.assert_array_equal(sliced_bits, expected_bits, "QPSK bit dilimleme hatası!")

    def test_bit_slicing_bpsk(self):
        # BPSK için sadece Reel eksen: 1+0j -> 1 | -1+0j -> 0
        bpsk_symbols = np.array([1+0j, -1+0j], dtype=np.complex64)
        expected_bits = np.array([1, 0], dtype=np.uint8)
        
        sliced_bits = self.decoder.bit_slicing(bpsk_symbols, "BPSK")
        np.testing.assert_array_equal(sliced_bits, expected_bits, "BPSK bit dilimleme hatası!")

    def test_valid_crc_parsing(self):
        # 2 Baytlık sahte veri (Payload: 10 ve 20) -> Toplam: 30 (Geçerli CRC: 30)
        valid_bytes = np.array([10, 20, 30], dtype=np.uint8)
        # Baytları bitlere çevirip fonksiyona yollayalım
        valid_bits = np.unpackbits(valid_bytes)
        
        payload, crc_valid = self.decoder.apply_fec_and_crc(valid_bits)
        
        self.assertTrue(crc_valid, "Geçerli CRC paketi yanlışlıkla reddedildi!")
        # Beklenen payload: 10 (0x0A) ve 20 (0x14) baytları
        self.assertEqual(payload, b'\x0a\x14', "Çözülen payload hatalı!")

    def test_invalid_crc_drop(self):
        # 2 Baytlık sahte veri (Payload: 10 ve 20) -> Hatalı CRC: 99
        invalid_bytes = np.array([10, 20, 99], dtype=np.uint8)
        invalid_bits = np.unpackbits(invalid_bytes)
        
        payload, crc_valid = self.decoder.apply_fec_and_crc(invalid_bits)
        
        self.assertFalse(crc_valid, "Hatalı CRC paketi sistemden geçmeyi başardı (Büyük güvenlik açığı)!")
        self.assertIsNone(payload, "Hatalı pakette payload dönmemeli, None olmalı!")

if __name__ == '__main__':
    unittest.main()