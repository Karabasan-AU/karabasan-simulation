import zmq
import numpy as np
import json
import os
import uuid
from datetime import datetime, timezone

def run_detector():
    context = zmq.Context()
    
    # 1. shared/config.json Dosyasını Oku
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../shared/config.json'))
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 2. Parametreleri ve Soket Adreslerini Config'den Çek
    sample_rate = config['simulation']['sample_rate']
    
    # Simülasyon motorundan gelen veriyi dinleme adresi (sim_engine -> ed_system)
    # SADECE TEST İÇİN: sim_to_ed yerine generators_to_sim yapıyoruz
    raw_sub_address = config['sockets']['sim_to_ed']['address']
    connect_sub_address = raw_sub_address.replace("zmq://localhost", "tcp://localhost")
    
    pub_address = "tcp://*:5558" 

    # 3. Soketleri Kur
    sub_socket = context.socket(zmq.SUB)
    sub_socket.connect(connect_sub_address)
    sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    pub_socket = context.socket(zmq.PUB)
    pub_socket.bind(pub_address)

    print("ED DSP Modülü: Sinyal Tespiti başlatıldı...")
    print(f"Dinlenen Kanal (SUB): {connect_sub_address} | Yayınlanan Port (PUB): {pub_address}")

    while True:
        message = sub_socket.recv()
        iq_data = np.frombuffer(message, dtype=np.complex64)

        if len(iq_data) == 0:
            continue

        # --- FFT Tabanlı PSD Hesabı ---
        nfft = 4096 
        if len(iq_data) < nfft:
            continue
            
        window = np.hanning(nfft)
        fft_result = np.fft.fftshift(np.fft.fft(iq_data[:nfft] * window, n=nfft))
        psd = (1.0 / (sample_rate * nfft)) * np.abs(fft_result)**2
        psd_db = 10 * np.log10(psd + 1e-12)

        # --- Dinamik Gürültü Tabanı ve Eşik Tespiti ---
        noise_floor_db = np.median(psd_db)
        threshold_db = noise_floor_db + 10.0 # Gürültü tabanının 10 dB üstü eşik

        peaks = np.where(psd_db > threshold_db)[0]

        if len(peaks) > 0:
            peak_idx = peaks[np.argmax(psd_db[peaks])]
            peak_power = psd_db[peak_idx]

            freqs = np.fft.fftshift(np.fft.fftfreq(nfft, d=1/sample_rate))
            center_freq_hz = freqs[peak_idx]

            # --- DİNAMİK BANT GENİŞLİĞİ (BANDWIDTH) HESABI ---
            # Zirveden sola doğru yürü (Sinyalin sol sınırı)
            left_idx = peak_idx
            while left_idx > 0 and psd_db[left_idx] > threshold_db:
                left_idx -= 1
                
            # Zirveden sağa doğru yürü (Sinyalin sağ sınırı)
            right_idx = peak_idx
            while right_idx < nfft - 1 and psd_db[right_idx] > threshold_db:
                right_idx += 1
                
            # Bin sayısını Hz cinsinden frekansa çevir
            freq_resolution = sample_rate / nfft
            calculated_bandwidth_hz = float((right_idx - left_idx) * freq_resolution)

            # Çok küçük veya sıfır çıkma ihtimaline karşı bir alt limit (örn: minimum 1 FFT bin)
            if calculated_bandwidth_hz <= 0:
                calculated_bandwidth_hz = float(freq_resolution)

            # --- PR #13 Uyumlu JSON Şeması ---
            current_time = datetime.now(timezone.utc)
            timestamp_ms = int(current_time.timestamp() * 1000)

            detection_event = {
                "event": "detection",
                "timestamp_ms": timestamp_ms,
                "signal_id": str(uuid.uuid4()), 
                "center_freq_hz": float(center_freq_hz),
                "bandwidth_hz": calculated_bandwidth_hz, # Artık tamamen dinamik!
                "power_dbm": float(peak_power),
                "modulation": "FM", 
                "has_fhss": False,  
                "has_dsss": False
            }
            
            # Veriyi yayınla
            pub_socket.send_string(f"ed.params {json.dumps(detection_event)}")
            print(f"Hedef Tespit! Frekans: {center_freq_hz/1e3:.2f} kHz | Güç: {peak_power:.2f} dBm | Genişlik: {calculated_bandwidth_hz/1e3:.2f} kHz")

if __name__ == "__main__":
    run_detector()