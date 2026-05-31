import unittest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from analog_demod import AnalogDemodulator

class TestAnalogDemodulator(unittest.TestCase):
    def setUp(self):
        # Ortak test kurulumu
        self.demod = AnalogDemodulator(input_sample_rate=2400000, audio_sample_rate=48000)
        # Bütün testlerde kullanılacak ortak sahte I/Q sinyali
        self.raw_iq = (np.random.randn(24000) + 1j * np.random.randn(24000)).astype(np.complex64)

    def test_output_dtype(self):
        audio_out = self.demod.process_block(self.raw_iq)
        self.assertEqual(audio_out.dtype, np.float32, "Çıktı tipi float32 olmalı!")

    def test_output_length(self):
        audio_out = self.demod.process_block(self.raw_iq)
        expected_length = len(self.raw_iq) // self.demod.decimation_factor
        self.assertEqual(len(audio_out), expected_length, "Çıktı veri boyutu seyreltme oranına uymuyor!")

    def test_amplitude_bounds_and_validity(self):
        audio_out = self.demod.process_block(self.raw_iq)
        
        # Sınır kontrolü
        self.assertTrue(np.all(audio_out >= -1.0) and np.all(audio_out <= 1.0), "Ses verisi sınırları aştı!")
        
        # Trivial Pass (Sürekli 0 gelmesi) kontrolü - Sinyalin varyansı sıfırdan büyük olmalı
        self.assertGreater(np.std(audio_out), 0.0, "Çıktı tamamen sıfır dönüyor (Trivial pass yakalandı)!")

    def test_edge_case_sample_rates(self):
        # Kenar durum: Girdi ve ses çıktı frekansı aynıysa (Decimation = 1)
        edge_demod = AnalogDemodulator(input_sample_rate=48000, audio_sample_rate=48000)
        short_iq = (np.random.randn(4800) + 1j * np.random.randn(4800)).astype(np.complex64)
        
        audio_out = edge_demod.process_block(short_iq)
        
        self.assertEqual(len(audio_out), len(short_iq), "Decimation 1 iken uzunluklar aynı olmalı!")
        self.assertEqual(audio_out.dtype, np.float32)

if __name__ == '__main__':
    unittest.main()