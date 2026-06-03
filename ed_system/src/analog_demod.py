import numpy as np
from scipy import signal

class AnalogDemodulator:
    def __init__(self, input_sample_rate=2400000, audio_sample_rate=48000):
        self.fs_in = input_sample_rate
        self.fs_out = audio_sample_rate
        
        # 1. Decimation Oranı Hesaplama 
        # Örn: 2.4 MSps -> 48 kHz için oran 50'dir.
        self.decimation_factor = self.fs_in // self.fs_out
        
        # 2. Low-Pass FIR Filtre Tasarımı
        # Ses bandı genelde 15 kHz ile sınırlıdır. Nyquist frekansına göre normalize ediyoruz.
        cutoff_hz = 15000.0 
        nyq_rate = self.fs_in / 2.0
        
        # Keskin kenarlı bir FIR filtre tasarımı (NumTaps = 65, işlemci dostu)
        self.fir_taps = signal.firwin(65, cutoff_hz / nyq_rate, window='hamming')
        
        # Quadrature Demodulation için geçmiş durum (Sürekli akışta faz atlamasını önlemek için)
        self.last_sample = np.complex64(0)
        
        # AGC (Otomatik Kazanç Kontrolü) için başlangıç durumu
        self.agc_gain = 1.0
        self.agc_target_level = 0.5

    def process_block(self, iq_data):
        # --- ADIM 1: Quadrature Demodulation (FM Demod) ---
        # Matematiksel olarak: ardışık kompleks örneklerin faz farkı anlık frekansı (sesi) verir.
        # Bu yöntem vektörize olduğu için CPU'da çok hızlı çalışır.
        
        # Önceki bloğun son örneğini başa ekleyerek kesintisiz faz farkı alıyoruz
        iq_padded = np.insert(iq_data, 0, self.last_sample)
        self.last_sample = iq_data[-1]
        
        # Faz farkının türevi (Açı: np.angle)
        # x[n] * conj(x[n-1]) işleminin açısı bize frekans sapmasını verir.
        fm_demodulated = np.angle(iq_padded[1:] * np.conj(iq_padded[:-1]))

        # --- ADIM 2: Low-Pass FIR Filtre [cite: 65] ---
        # Demodülasyon sonrası yüksek frekanslı gürültüleri temizle
        filtered_audio = signal.lfilter(self.fir_taps, 1.0, fm_demodulated)

        # --- ADIM 3: Decimation (Seyreltme) ---
        # 10 MSps / 2.4 MSps gibi yüksek hızları ses kartının/arayüzün okuyabileceği 48 kHz'e düşür
        decimated_audio = filtered_audio[::self.decimation_factor]

        # --- ADIM 4: AGC (Otomatik Kazanç Kontrolü)  ---
        # Hedef uzaklaştıkça sesin kısılmasını engellemek için dinamik genlik ayarı
        current_energy = np.mean(np.abs(decimated_audio))
        
        if current_energy > 0:
            # Kazancı yumuşak bir şekilde güncelle (Alpha filtresi)
            error = self.agc_target_level / current_energy
            self.agc_gain = (0.9 * self.agc_gain) + (0.1 * error)
            
            # Aşırı patlamaları önlemek için kazancı sınırla
            self.agc_gain = np.clip(self.agc_gain, 0.1, 10.0)
            
        audio_out = decimated_audio * self.agc_gain
        
        # Çıktı: -1.0 ile 1.0 arasında normalize edilmiş float32 ses verisi
        return np.clip(audio_out, -1.0, 1.0).astype(np.float32)