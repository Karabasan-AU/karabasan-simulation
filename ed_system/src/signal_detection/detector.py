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
    # PR #13 gereği fiziksel modelleme sample_rate'i kullanılıyor (2400000.0 Hz)
    sample_rate = config['simulation']['sample_rate']
    
    # Simülasyon motorundan gelen veriyi dinleme adresi (sim_engine -> ed_system)
    raw_sub_address = config['sockets']['sim_to_ed']['address']
    connect_sub_address = raw_sub_address.replace("zmq://localhost", "tcp://localhost")
    
    # ED Modülünün kendi tespitlerini yayınlayacağı lokal ZMQ PUB soketi
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

            # --- PR #13 Uyumlu websocket_schemas.detection_event JSON Şeması ---
            # Python 3.12+ uyumlu UTC Unix zaman damgası hesabı (utcnow deprecation çözümü)
            current_time = datetime.now(timezone.utc)
            timestamp_ms = int(current_time.timestamp() * 1000)

            detection_event = {
                "event": "detection",
                "timestamp_ms": timestamp_ms,
                "signal_id": str(uuid.uuid4()), 
                "center_freq_hz": float(center_freq_hz),
                "bandwidth_hz": 12500.0, # NBFM varsayılanı (Daha sonra dinamikleştirilecek)
                "power_dbm": float(peak_power),
                "modulation": "FM", 
                "has_fhss": False,  
                "has_dsss": False
            }
            
            # Veriyi yayınla
            pub_socket.send_string(f"ed.params {json.dumps(detection_event)}")
            print(f"Hedef Tespit Edildi! Frekans: {center_freq_hz/1e3:.2f} kHz | Güç: {peak_power:.2f} dBm")

if __name__ == "__main__":
    run_detector()