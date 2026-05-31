import zmq
import numpy as np
import json
from datetime import datetime

def run_detector():
    context = zmq.Context()
    
    # 1. Ham I/Q Veri Alımı (SUB)
    sub_socket = context.socket(zmq.SUB)
    sub_socket.connect("tcp://localhost:5555")
    sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    # 2. ed.params Yayını İçin PUB Soketi
    pub_socket = context.socket(zmq.PUB)
    pub_socket.bind("tcp://*:5556")

    print("ED DSP Modülü: Sinyal Tespiti başlatıldı, I/Q verisi bekleniyor...")

    sample_rate = 2.4e6  # config.json'daki güncel değer
    
    while True:
        # ZeroMQ üzerinden veriyi al
        message = sub_socket.recv()
        iq_data = np.frombuffer(message, dtype=np.complex64)

        if len(iq_data) == 0:
            continue

        # --- FFT Tabanlı PSD (Güç Spektral Yoğunluğu) Hesabı ---
        nfft = 1024 # FFT boyutu
        
        # Sızıntıyı (leakage) önlemek için pencereleme (windowing)
        window = np.hanning(len(iq_data[:nfft]))
        
        # Sinyali frekans uzayına çevir (Sıfır frekansı merkeze al)
        fft_result = np.fft.fftshift(np.fft.fft(iq_data[:nfft] * window, n=nfft))
        
        # PSD Hesabı ve dBm formatına dönüşüm
        psd = (1.0 / (sample_rate * nfft)) * np.abs(fft_result)**2
        psd_db = 10 * np.log10(psd + 1e-12) # log(0) hatasını önlemek için küçük bir değer ekliyoruz

        # --- Dinamik Gürültü Tabanı (Noise Floor) Tespiti ---
        # Spektrumdaki sinyallerin medyanı temel ortam gürültüsünü verir
        noise_floor_db = np.median(psd_db)
        
        # SNR (Sinyal Gürültü Oranı) için dinamik tespit eşiği: Gürültü tabanının 10 dB üstü
        threshold_db = noise_floor_db + 10.0

        # Gürültü tabanının üzerindeki tepe noktalarını (sinyalleri) işaretle
        peaks = np.where(psd_db > threshold_db)[0]

        if len(peaks) > 0:
            # En güçlü sinyalin indeksini bul
            peak_idx = peaks[np.argmax(psd_db[peaks])]
            peak_power = psd_db[peak_idx]

            # İndeksi gerçek frekans değerine dönüştür
            freqs = np.fft.fftshift(np.fft.fftfreq(nfft, d=1/sample_rate))
            center_freq = freqs[peak_idx]

            # Parametreleri JSON olarak hazırla
            params = {
                "center_freq": float(center_freq),
                "bandwidth": 25000, # İleride enerji dağılımı ile dinamik hesaplanacak
                "power_db": float(peak_power),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
            # Sonucu ZeroMQ (5556) üzerinden diğer modüllere (Serhat/Meryem) yayınla
            pub_socket.send_string(f"ed.params {json.dumps(params)}")
            
            # Ekrana bas
            print(f"Hedef Tespit Edildi! Frekans: {center_freq/1e3:.2f} kHz | Güç: {peak_power:.2f} dBm | Eşik: {threshold_db:.2f} dBm")

if __name__ == "__main__":
    run_detector()