import zmq
import numpy as np
import time
import json
import os

# config.json Dosyasını Oku
config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../shared/config.json'))
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

# Parametreleri Çek
sample_rate = config['simulation']['sample_rate']
raw_address = config['sockets']['generators_to_sim']['address']
bind_address = raw_address.replace("zmq://localhost", "tcp://*")

# ZMQ PUB Soketi
context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind(bind_address)

print(f"Drone Generator (Hareketli) aktif. Adres: {bind_address} | Sample Rate: {sample_rate} Hz")

chunk_size = 10000
t_total = 0

while True:
    t = np.arange(chunk_size) / sample_rate
    t_global = t + t_total
    t_total += chunk_size / sample_rate
    
    # Frekansı sürekli değişen drone sinyali (-400 kHz ile +400 kHz arası)
    f_offset = 400e3 * np.sin(2 * np.pi * 0.5 * t_global) 
    
    # Kanal etkileri sim_engine'e bırakıldı, sadece temiz I/Q üretiliyor
    signal = np.exp(2j * np.pi * f_offset * t).astype(np.complex64)
    
    socket.send(signal.tobytes())
    time.sleep(0.001)