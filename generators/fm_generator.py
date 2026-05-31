import zmq
import numpy as np
import time
import json

# ZMQ PUB Soketi Kurulumu
context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind("tcp://*:5555") # config.json'dan da çekilebilir

sample_rate = 10e6 # 10 MSps
center_freq = 100e6 # 100 MHz

print("FM Generator aktif. ZMQ (5555) üzerinden I/Q akışı başladı...")

while True:
    # 1 milisaniyelik test bloğu (10.000 örnek)
    t = np.arange(10000) / sample_rate
    
    # Kompleks (I/Q) sinyal üretimi
    signal = np.exp(2j * np.pi * 1e3 * t).astype(np.complex64)
    
    # Sistemin dinamik eşiğini test etmek için yapay gürültü ekleyelim
    noise = (np.random.randn(len(t)) + 1j * np.random.randn(len(t))) * 0.1
    iq_data = (signal + noise).astype(np.complex64)

    # Veriyi byte dizisi olarak ZeroMQ'ya bas 
    socket.send(iq_data.tobytes())
    time.sleep(0.001) # Akış hızını dengele