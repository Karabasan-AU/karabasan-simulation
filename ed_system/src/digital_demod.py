import numpy as np
from scipy import signal
from fec_decoder import FECDecoder
from numba import njit
import numba as nb

@njit(cache=True, fastmath=True)
def _costas_loop_kernel(
    samples_real: nb.float64[:],
    samples_imag: nb.float64[:],
    alpha: float,
    beta: float,
    init_phase: float,
    init_freq: float,
):
    """
    Costas Loop iç döngüsü — Numba njit ile C hızında.
    Karmaşık dizi yerine ayrı real/imag alır: Numba'nın complex64
    vektör desteği platforma göre değişir; bu yaklaşım taşınabilirdir.
    """
    n = len(samples_real)
    out_real = np.empty(n, dtype=np.float64)
    out_imag = np.empty(n, dtype=np.float64)

    phase    = init_phase
    freq_err = init_freq

    for i in range(n):
        # 1. Faz düzeltme: örneği tahmini fazın tersine döndür
        cos_p = np.cos(-phase)
        sin_p = np.sin(-phase)
        r = samples_real[i] * cos_p - samples_imag[i] * sin_p
        q = samples_real[i] * sin_p + samples_imag[i] * cos_p

        # 2. Hata dedektörü (BPSK/QPSK uyumlu Costas sezgisi)
        #    e = sign(I)*Q − sign(Q)*I
        #    → QPSK için 4 bölge; BPSK için Q kanalı sıfır kabul edilir
        sign_r = 1.0 if r >= 0.0 else -1.0
        sign_q = 1.0 if q >= 0.0 else -1.0
        error = sign_r * q - sign_q * r

        # 3. İkinci dereceden döngü filtresi (proportional + integratör)
        freq_err += beta  * error
        phase    += alpha * error + freq_err

        # 4. Faz sarmalama: [0, 2π) aralığında tut
        phase = phase % (2.0 * np.pi)

        out_real[i] = r
        out_imag[i] = q

    return out_real, out_imag, phase, freq_err



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
    def _carrier_phase_sync(self, samples: np.ndarray, mode: str = "costas",snr: float = 15.0) -> np.ndarray:
        """
        İki Aşamalı Hibrit Faz Senkronizasyonu (KTRSinyalİzleme §2):
          Aşama 1 — FFT tabanlı kaba frekans kaydırma (her iki modda ortak)
          Aşama 2 — İnce faz eşitleme:
                     • Yüksek SNR / burst → Viterbi-Viterbi (M-th Power)
                     • Düşük SNR / sürekli → Costas Loop (Numba JIT kernel)
        """
        # ── AŞAMA 1: FFT Tabanlı Kaba Frekans Düzeltme ───────────────────────
        fft_out   = np.fft.fft(samples)
        psd       = np.abs(fft_out) ** 2
        peak_bin  = np.argmax(psd)
        n         = len(samples)
        freq_off  = (peak_bin if peak_bin < n // 2 else peak_bin - n) / n
        t         = np.arange(n, dtype=np.float64)
        samples   = (samples * np.exp(-2j * np.pi * freq_off * t)).astype(np.complex64)

        # ── AŞAMA 2: İnce Faz Eşitleme ───────────────────────────────────────
        if mode == "viterbi":
            # Yüksek SNR / burst iletim → M-th Power (QPSK için 4. kuvvet)
            # Açık döngü; kilitlenme anında, preamble kaybı sıfır.
            m         = 4
            rotated   = samples ** m
            phase_est = np.angle(np.mean(rotated)) / m
            synced    = samples * np.exp(-1j * phase_est)

        else:
            # Düşük SNR / sürekli yayın → Costas Loop (Numba JIT)
            # Durum vektörü (phase, freq_err) bloklar arası korunur:
            # ilk çağrıda attribute yoksa 0.0 ile başlat.
            if not hasattr(self, '_costas_phase'):
                self._costas_phase    = 0.0
                self._costas_freq_err = 0.0

            # Numba kernel gerçek sayı dizisi ister → view ile kopyasız dönüşüm
            samp_f64  = samples.astype(np.complex128)
            r_out, q_out, self._costas_phase, self._costas_freq_err = (
                _costas_loop_kernel(
                    samp_f64.real.copy(),   # .copy(): Numba contiguous array bekler
                    samp_f64.imag.copy(),
                    alpha     = 0.02,        # Uygulamaya göre ayarla
                    beta      = 0.0001,      # alpha² / 4 ≈ iyi başlangıç noktası
                    init_phase = self._costas_phase,
                    init_freq  = self._costas_freq_err,
                )
            )
            synced = (r_out + 1j * q_out).astype(np.complex64)

        return synced