import numpy as np
from scipy import signal
from fec_decoder import FECDecoder

class DigitalDemodulator:
    def __init__(self, sample_rate=2400000):
        self.fs = sample_rate
        
        # Döngü filtre parametreleri (Loop Filter Gains)
        # Kararlılık ve hızlı kilitlenme (settling time) dengesi için optimize edildi
        self.gardner_gain = 0.01
        self.mm_gain = 0.005
        
        # Başlangıç durumları (States)
        self.mu = 0.0  # Kesirli gecikme (fractional interval)
        self.last_sample = np.complex64(0)

        # M&M algoritması için bloklar arası hafıza
        self.mm_last_s = np.complex64(0)
        self.mm_last_a = np.complex64(0)

        self.fec_decoder = FECDecoder()

    def process_block(self, iq_data, mod_type):
        # 1. Saat Geri Kazanımı (Gardner / M&M)
        if "FAST_DRONE" in mod_type or "BURST" in mod_type:
            synced_symbols = self._gardner_clock_recovery(iq_data)
        else:
            synced_symbols = self._mueller_muller_clock_recovery(iq_data)
        
        # --- YENİ EKLENEN KISIM: Dinamik SNR Tahmini ---
        if len(synced_symbols) > 0:
            signal_power = np.mean(np.abs(synced_symbols)**2)
            noise_power = np.var(synced_symbols) + 1e-10 # Sıfıra bölmeyi engelle
            estimated_snr = 10 * np.log10(signal_power / noise_power)
        else:
            estimated_snr = 0.0

       # 2. Taşıyıcı Faz Senkronizasyonu (Dinamik SNR ile)
        final_symbols = self._carrier_phase_sync(synced_symbols, mod_type, snr=estimated_snr)
            
        # 3. Bit Slicing (Sembolden Bite)
        raw_bits = self.fec_decoder.bit_slicing(final_symbols, mod_type)
        
        # 4. FEC & CRC Hata Düzeltme / Paket Çözümleme
        payload, crc_valid = self.fec_decoder.apply_fec_and_crc(raw_bits)
        
        # Eğer paket hatasız çözüldüyse ana hatta bildirmek için tuple döndürüyoruz
        return final_symbols, payload, crc_valid

    def _gardner_clock_recovery(self, iq_data):
        num_samples = len(iq_data)
        output_symbols = []
        
        # Vektörize interpolasyon ve hata takibi için pointer'lar
        idx = 2
        while idx < num_samples - 1:
            
           # Farrow yapısı veya doğrusal interpolasyon ile optimum örnekleri buluyoruz
            # Burada indeksleri sembol aralığına (2 örnek) göre doğru hizalıyoruz:
            s_0 = iq_data[idx - 2]   # Önceki sembol
            s_mid = iq_data[idx - 1] # Sembol ortası (Geçiş örneği)
            s_1 = iq_data[idx]       # Mevcut sembol
            
            # Gardner Hata Fonksiyonu: e = real( (s_1 - s_0) * conj(s_mid) )
            error = np.real((s_1 - s_0) * np.conj(s_mid))
            
            # Kesirli gecikmeyi (mu) güncelle ve döngü filtresinden geçir
            self.mu += self.gardner_gain * error
            
            # Zamanlama kaymasına göre indeks kontrolü
            if self.mu > 1.0:
                idx += 1
                self.mu -= 1.0
            elif self.mu < -1.0:
                idx -= 1
                self.mu += 1.0
                
            output_symbols.append(s_1)
            idx += 2 # Sembol başına 2 örnek ilerleme
            
        return np.array(output_symbols, dtype=np.complex64)

    def _mueller_muller_clock_recovery(self, iq_data):
        num_samples = len(iq_data)
        output_symbols = []
        
        idx = 1
        
        # GÜVENLİK: Eğer __init__ içinde tanımlanmayı unutulmuşsa değişkenleri ilk kez burada yarat
        if not hasattr(self, 'mm_last_s'):
            self.mm_last_s = np.complex64(0)
            self.mm_last_a = np.complex64(0)
        
        while idx < num_samples:
            s_n = iq_data[idx]
            
            # Slicer (Karar verici): En yakın sembol değerine yuvarla (Örn: BPSK/QPSK için işaret alma)
            a_n = np.sign(np.real(s_n)) + 1j * np.sign(np.imag(s_n))
            
            # M&M Hata Fonksiyonu: e = real(a_{n-1} * s_n - a_n * s_{n-1})
            # LOKAL DEĞİŞKEN YERİNE SELF KULLANILDI (Bloklar arası veri kaybını önler)
            error = np.real(self.mm_last_a * s_n - a_n * self.mm_last_s)
            
            # Zamanlama güncelleme
            idx_step = 1 + int(self.mm_gain * error)
            idx += max(1, idx_step) # Negatif veya sıfır adımı engelle
            
            output_symbols.append(s_n)
            
            # Sonraki döngü (veya sonraki process_block veri akışı) için hafızayı güncelle
            self.mm_last_s = s_n
            self.mm_last_a = a_n
            
        return np.array(output_symbols, dtype=np.complex64)
    def _carrier_phase_sync(self, symbols, mod_type, snr=15.0):
        if len(symbols) == 0:
            return symbols

        # --- AŞAMA 1: FFT Tabanlı Kaba Frekans Senkronizasyonu ---
        m = 4 if "QPSK" in mod_type else 2
        fft_res = np.fft.fft(symbols ** m)
        freq_idx = np.argmax(np.abs(fft_res))
        
        # Reviewer'ın uyarısı: Fazı değil, frekans bin'ini kullanarak sapmayı bul
        normalized_freq = freq_idx / len(symbols)
        if normalized_freq > 0.5:
            normalized_freq -= 1.0 # Negatif frekans bölgesi (Nyquist sonrası) için düzeltme
            
        coarse_freq_offset = normalized_freq / m
        
        # Faz düzeltmesini zaman vektörüyle sinyale uygula
        t = np.arange(len(symbols))
        symbols_coarse_corrected = symbols * np.exp(-1j * 2 * np.pi * coarse_freq_offset * t)
        
        # --- AŞAMA 2: Uyarlanabilir İnce Faz Eşitleme ---
        # Paket bazlı (burst) ve yüksek SNR durumlarında Viterbi-Viterbi açık döngüsü devreye girer
        if "BURST" in mod_type or snr > 12.0:
            # Viterbi-Viterbi Açık Döngü Algoritması (Veri kaybını sıfıra indirir)
            phase_error = np.angle(np.mean(symbols_coarse_corrected ** m)) / m
            synced_symbols = symbols_coarse_corrected * np.exp(-1j * phase_error)
            
        else:
            # Düşük SNR ve sürekli yayınlarda Costas Loop kapalı döngüsü (İşlemci bütçesini korur)
            synced_symbols = np.zeros_like(symbols_coarse_corrected)
            phase = 0.0
            freq = 0.0
            alpha = 0.1  # Döngü filtresi kazançları
            beta = 0.01
            
            for i, sym in enumerate(symbols_coarse_corrected):
                # Faz kaydırma uygulamasını yap
                rotated_sym = sym * np.exp(-1j * phase)
                synced_symbols[i] = rotated_sym
                
                # QPSK için Costas Hata Dedektörü: e = real(y)*imag(y) * (real(y)^2 - imag(y)^2)
                error = np.real(rotated_sym) * np.imag(rotated_sym) * \
                        (np.real(rotated_sym)**2 - np.imag(rotated_sym)**2)
                
                # Frekans ve faz güncelleme (Loop Filter)
                freq += beta * error
                phase += freq + alpha * error
                
        return synced_symbols.astype(np.complex64)