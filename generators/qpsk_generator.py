import zmq
import numpy as np
import time
import json
import os

# 1. Config Dosyasını Oku
config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../shared/config.json'))
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

# Parametreleri Çek
sample_rate = config['simulation']['sample_rate']
raw_address = config['sockets']['generators_to_sim']['address']
bind_address = raw_address.replace("zmq://localhost", "tcp://*").replace("zmq://127.0.0.1", "tcp://*")

# 2. ZMQ PUB Soketi
context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind(bind_address)

print(f"[DİJİTAL JENERATÖR] QPSK Test yayını aktif. Adres: {bind_address}")

# ZMQ bağlantısının oturması için 1 saniye bekle
time.sleep(1)

chunk_size = 10000

# Beyin'i "Sayisal" moda geçirecek o sihirli modülasyon paketi
mod_trigger_data = {
    "status": "active",
    "class": "QPSK",  # main.py bu string'i bekliyor
    "confidence": 0.99
}
# 1. BEYİN'İ UYANDIR: Modülasyon etiketini fırlat (Sayısal hattı tetikler)
socket.send_multipart([b"ed.modulation", json.dumps(mod_trigger_data).encode('utf-8')])
while True:
    
    
    # 2. QPSK I/Q VERİSİ ÜRETİMİ (Sanal Dijital Sinyal)
    # QPSK'nın 4 temel sembolü: (1+1j), (1-1j), (-1+1j), (-1-1j)
    symbols = np.random.choice([1+1j, 1-1j, -1+1j, -1-1j], size=chunk_size)
    
    # Sinyali gerçeğe benzetmek için biraz Termal Gürültü (AWGN) ekliyoruz
    noise = (np.random.randn(chunk_size) + 1j * np.random.randn(chunk_size)) * 0.1
    signal = (symbols + noise).astype(np.complex64)
    
    # 3. VERİYİ FIRLAT
    socket.send_multipart([b"ed.iq", signal.tobytes()])
    
    # Döngü hızı (saniyede ~100 paket atar)
    time.sleep(0.01)