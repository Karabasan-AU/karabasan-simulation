import unittest
import numpy as np
import sys
import os

# Test dosyasının bulunduğu yerin bir üst klasöründeki 'src' klasörünü yola ekliyoruz.
# Böylece analog_demod.py dosyasını sorunsuz bulup içe aktarabilir.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from analog_demod import AnalogDemodulator

class TestAnalogDemodulator(unittest.TestCase):
    def setUp(self):
        # 1. Test ortamı hazırlığı: Demodülatörü varsayılan değerlerle (2.4M input, 48k output) başlatıyoruz[cite: 1].
        self.demod = AnalogDemodulator(input_sample_rate=2400000, audio_sample_rate=48000)

    def test_process_block(self):
        # 2. test_generator.py mantığına uygun 24000 örnekli rastgele kompleks I/Q verisi oluşturuyoruz[cite: 6].
        # Bu veri sahte bir FM sinyalini taklit ediyor.
        raw_iq = (np.random.randn(24000) + 1j * np.random.randn(24000)).astype(np.complex64)
        
        # 3. Veriyi yazdığın analog pipeline'a sokuyoruz[cite: 1].
        audio_out = self.demod.process_block(raw_iq)
        
        # --- KABUL KRİTERLERİ (ASSERTIONS) ---
        
        # Çıktı tipinin senin kodunda belirttiğin gibi float32 olup olmadığını kontrol et[cite: 1].
        self.assertEqual(audio_out.dtype, np.float32, "Çıktı tipi float32 olmalı!")
        
        # Decimation (seyreltme) oranına göre veri boyutunun doğruluğunu kontrol et[cite: 1].
        # 2400000 // 48000 = 50 decimation çarpanı var[cite: 1]. 
        # 24000 girdi / 50 = 480 örnek çıkmalı.
        expected_length = len(raw_iq) // self.demod.decimation_factor
        self.assertEqual(len(audio_out), expected_length, "Çıktı veri boyutu seyreltme oranına uymuyor!")
        
        # AGC ve Clip işlemi sayesinde ses çıkışının genlik sınırları içinde olduğunu doğrula[cite: 1].
        self.assertTrue(np.all(audio_out >= -1.0) and np.all(audio_out <= 1.0), "Ses verisi sınırları aştı!")

if __name__ == '__main__':
    unittest.main()