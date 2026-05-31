import unittest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from fec_decoder import FECDecoder

class TestFECDecoder(unittest.TestCase):
    def setUp(self):
        #Test ortamını ve bağımlılıkları hazırlar.
        self.decoder = FECDecoder()

    def test_bit_slicing_all_modes(self):
        #QPSK ve BPSK modülasyonları için bit dilimleme doğruluğunu tek bir yapıda test eder.
        test_cases = [
            ("QPSK", np.array([1+1j, -1+1j, -1-1j, 1-1j], dtype=np.complex64), np.array([1, 1, 0, 1, 0, 0, 1, 0], dtype=np.uint8)),
            ("BPSK", np.array([1+0j, -1+0j], dtype=np.complex64), np.array([1, 0], dtype=np.uint8))
        ]

        # subTest kullanımı: Hata çıkarsa hangi modülasyonda çıktığını nokta atışı gösterir
        for mod_type, symbols, expected_bits in test_cases:
            with self.subTest(mod_type=mod_type):
                sliced_bits = self.decoder.bit_slicing(symbols, mod_type)
                np.testing.assert_array_equal(sliced_bits, expected_bits, f"{mod_type} dilimleme hatası!")

    def test_crc_validation_flows(self):
        #Geçerli ve geçersiz CRC paketlerinin sistemdeki yönlendirmelerini doğrular.
        # Senaryo 1: Geçerli CRC (Drop edilmemeli)
        valid_bytes = np.array([10, 20, 30], dtype=np.uint8)
        payload_valid, is_valid = self.decoder.apply_fec_and_crc(np.unpackbits(valid_bytes))
        
        with self.subTest(condition="Valid CRC Packet"):
            self.assertTrue(is_valid, "Geçerli paket reddedildi!")
            self.assertEqual(payload_valid, b'\x0a\x14')

        # Senaryo 2: Geçersiz CRC (Kesinlikle drop edilmeli)
        invalid_bytes = np.array([10, 20, 99], dtype=np.uint8)
        payload_invalid, is_invalid = self.decoder.apply_fec_and_crc(np.unpackbits(invalid_bytes))
        
        with self.subTest(condition="Invalid CRC Packet"):
            self.assertFalse(is_invalid, "Hatalı CRC sistemi geçti!")
            self.assertIsNone(payload_invalid)

    def test_edge_case_short_packet(self):
        #8 bitten (1 bayt) daha kısa olan eksik/kopuk paketlerin çökme yapmadan drop edilmesini test eder.
        short_bits = np.array([1, 0, 1, 1], dtype=np.uint8)
        payload, is_valid = self.decoder.apply_fec_and_crc(short_bits)
        
        self.assertFalse(is_valid, "Eksik paketler anında reddedilmeli!")
        self.assertIsNone(payload)

if __name__ == '__main__':
    unittest.main()