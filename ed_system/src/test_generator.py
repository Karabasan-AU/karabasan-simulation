import zmq
import time
import json
import numpy as np

def run_test():
    context = zmq.Context()
    
    # Bizim config.json'daki adrese (5555 portuna) yayın yapacak PUB soketi kuruyoruz
    # docker-compose yml'de host modu kullandığımız için localhost üzerinden konuşabiliriz
   # test_generator.py içindeki ilgili satır:
    # test_generator.py içindeki soket bağlantı kısmı:
    pub_socket = context.socket(zmq.PUB)
    pub_socket.bind("tcp://127.0.0.1:5555") # Yeniden bind yapıyoruz
    
    print("[TEST] Yapay Sinyal Üreteci Başlatıldı. 3 saniye sonra tetikleme gönderilecek...")
    time.sleep(3)
    
    # --- SENARYO 1: ANALOG SİNYAL TETİKLEMESİ VE VERİSİ ---
    print("[TEST] 1. Senaryo: Analog (FM) yayın tetiklemesi gönderiliyor...")
    # ed.params topic'ine active mesajı basıyoruz
    params_msg = {"type": "Analog", "freq": 433000000, "bw": 25000, "status": "active"}
    pub_socket.send_multipart([b"ed.params", json.dumps(params_msg).encode('utf-8')])
    time.sleep(1)
    
    print("[TEST] Analog I/Q verileri akıtılıyor...")
    for _ in range(5):
        # 2400000 sample rate'e uygun rastgele kompleks I/Q verisi üretiyoruz (Gürültülü FM gibi)
        raw_iq = np.random.randn(24000) + 1j * np.random.randn(24000)
        pub_socket.send_multipart([b"ed.iq", raw_iq.astype(np.complex64).tobytes()])
        time.sleep(0.5)
        
    # Analog yayını bitir
    params_msg["status"] = "inactive"
    pub_socket.send_multipart([b"ed.params", json.dumps(params_msg).encode('utf-8')])
    time.sleep(2)
    
    # --- SENARYO 2: SAYISAL SİNYAL TETİKLEMESİ VEE VERİSİ ---
    print("[TEST] 2. Senaryo: Yapay Zeka (AMC) Sayısal Modülasyon tetiklemesi gönderiliyor...")
    # ed.modulation topic'ine active mesajı basıyoruz
    mod_msg = {"class": "QPSK_FAST_DRONE", "confidence": 0.98, "status": "active"}
    pub_socket.send_multipart([b"ed.modulation", json.dumps(mod_msg).encode('utf-8')])
    time.sleep(1)
    
    print("[TEST] Sayısal I/Q verileri akıtılıyor...")
    for _ in range(5):
        # Sayısal bir sinyal taklidi
        raw_iq = np.random.randn(4800) + 1j * np.random.randn(4800)
        pub_socket.send_multipart([b"ed.iq", raw_iq.astype(np.complex64).tobytes()])
        time.sleep(0.5)
        
    print("[TEST] Test senaryoları bitti.")

if __name__ == "__main__":
    run_test()