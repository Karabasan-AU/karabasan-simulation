import zmq
import numpy as np
import time

context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind("tcp://*:5555")

sample_rate = 2.4e6  # 2.4 MSps
print("FM Generator aktif. ZMQ (5555) üzerinden HAREKETLİ I/Q akışı başladı...")

t_total = 0
while True:
    t = np.arange(10000) / sample_rate
    t_global = t + t_total
    t_total += 10000 / sample_rate
    
    # 1. GERÇEKÇİ FREKANS: Merkez frekanstan -400 kHz ile +400 kHz arasında sürekli hareket eden hedef
    f_offset = 400e3 * np.sin(2 * np.pi * 0.5 * t_global) 
    
    # Kompleks sinyal üretimi
    signal = np.exp(2j * np.pi * f_offset * t).astype(np.complex64)
    
    # 2. GERÇEKÇİ SİNYAL GÜCÜ (Fading): Hedef uzaklaşıp yakınlaşıyor gibi sinyal gücü dalgalanır
    signal_power = 0.5 + 0.4 * np.cos(2 * np.pi * 0.2 * t_global)
    
    # 3. GERÇEKÇİ GÜRÜLTÜ: Çevresel etkilere göre taban gürültüsü sürekli değişir
    noise_variance = 0.1 + 0.05 * np.sin(2 * np.pi * 0.1 * t_global)
    noise = (np.random.randn(len(t)) + 1j * np.random.randn(len(t))) * noise_variance
    
    # Hedef sinyal ile çevresel gürültüyü birleştir
    iq_data = (signal * signal_power + noise).astype(np.complex64)

    socket.send(iq_data.tobytes())
    time.sleep(0.001)