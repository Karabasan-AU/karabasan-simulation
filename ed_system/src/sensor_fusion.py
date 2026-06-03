import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import zmq
import json
import time

class SensorFusion:
    # 1. Varsayılan değeri None yapıyoruz
    def __init__(self, config_file=None):
        if config_file is None:
            current_dir = os.path.dirname(__file__)
            config_file = os.path.abspath(os.path.join(current_dir, '../../shared/config.json'))
            
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
            
        self.context = zmq.Context()
        
        # 1. İÇERİDEN VERİ ALMA (Main.py buradan bize bağlanacak) - BIND YAPIYORUZ
        self.fusion_sub = self.context.socket(zmq.SUB)
        self.fusion_sub.bind("tcp://0.0.0.0:5557")  # <-- ARTIK KAPININ SAHİBİ BURASI!
        self.fusion_sub.setsockopt_string(zmq.SUBSCRIBE, "fusion.telemetry")
        self.fusion_sub.setsockopt_string(zmq.SUBSCRIBE, "fusion.audio")
        self.fusion_sub.setsockopt_string(zmq.SUBSCRIBE, "ed.geolocation")
        self.fusion_sub.setsockopt_string(zmq.SUBSCRIBE, "ed.quarantine")
        
        self.poller = zmq.Poller()
        self.poller.register(self.fusion_sub, zmq.POLLIN)
        
        # 2. DIŞARIYA VERİ BASMA (Arayüz/UI Hattı - 5558)
        self.ui_pub = self.context.socket(zmq.PUB)
        self.ui_pub.setsockopt(zmq.LINGER, 0)
        self.ui_pub.bind("tcp://0.0.0.0:5558")
        
        # 3. TAARRUZ TETİKLEME (Kural Motoru - Çakışmasın diye 5559 yapıyoruz)
        self.trigger_pub = self.context.socket(zmq.PUB)
        self.trigger_pub.bind("tcp://0.0.0.0:5559") 
        
        print("[SENSÖR FÜZYONU] Kavşak noktası başlatıldı. Veriler bekleniyor...")

    def run(self):
        print("[SENSÖR FÜZYONU] Dinleme döngüsü aktif. Kapatmak için Ctrl+C yapabilirsiniz.")
        while True:
            try:
                # Maksimum 1 saniye bekler. Veri gelmese de uyanır, 
                # bu sayede Windows Ctrl+C sinyalini anında yakalayabilir!
                socks = dict(self.poller.poll(timeout=1000))
                
                if self.fusion_sub in socks:
                    topic, msg = self.fusion_sub.recv_multipart()
                    topic = topic.decode('utf-8')
                    
                    if topic == "fusion.telemetry":
                        self._handle_telemetry(msg)
                    elif topic == "fusion.audio":
                        self._handle_audio(msg) # Gelen paketi yeni fonksiyona yolla
                    elif topic == "ed.geolocation":
                        pass
                        
            except KeyboardInterrupt:
                # Ctrl+C basıldığında donmak yerine buraya düşecek
                print("\n[BİLGİ] Sensör Füzyonu kullanıcı tarafından kapatılıyor...")
                break
            except Exception as e:
                print(f"Döngü hatası: {e}")
                break

    def _handle_telemetry(self, payload_bytes):
        try:
            packet_data = payload_bytes.decode('utf-8', errors='ignore')
            print(f"[FÜZYON] Telemetri alındı: {packet_data}")
            
            # --- 1. ARAYÜZE (UI) LOGLAMA ---
            ui_msg = json.dumps({"type": "telemetry", "data": packet_data, "timestamp": time.time()})
            self.ui_pub.send_multipart([b"ui.data", ui_msg.encode('utf-8')])
            
            # --- 2. KURAL TABANLI TAARRUZ (ET) TETİKLEME ---
            if "DRONE_ID" in packet_data or "CRITICAL_CMD" in packet_data:
                trigger_cmd = json.dumps({
                    "action": "START_JAMMING",
                    "target_type": "QPSK_FAST_DRONE",
                    "priority": "HIGH"
                })
                print("[FÜZYON] Kural tetiklendi! ET Modülüne Taarruz Emri (et.trigger) gönderiliyor.")
                self.trigger_pub.send_multipart([b"et.trigger", trigger_cmd.encode('utf-8')])
                
        except Exception as e:
            print(f"Telemetri işleme hatası: {e}")

    def _handle_audio(self, payload_bytes):
        try:
            # 1. main.py'den gelen paketi string'e ve ardından JSON'a çeviriyoruz
            packet_str = payload_bytes.decode('utf-8', errors='ignore')
            raw_json = json.loads(packet_str)
            
            # 2. ARAYÜZE (UI) LOGLAMA VE FIRLATMA
            # UI ekibinin sistemiyle uyumlu olması için veriyi "type: audio" kılıfına sokuyoruz
            ui_msg = json.dumps({
                "type": "audio", 
                "data": raw_json, 
                "timestamp": time.time()
            })
            
            # 3. ZMQ ile arayüz soketine fırlat
            self.ui_pub.send_multipart([b"ui.data", ui_msg.encode('utf-8')])
            
            # 4. Terminalden canlı takip edebilmek için gecikmeyi ekrana bas
            latency = raw_json.get("processing_latency_ms", "Bilinmiyor")
            print(f"[FÜZYON] Canlı telsiz sesi arayüze iletildi! İşlem Gecikmesi: {latency} ms")
            
        except Exception as e:
            print(f"Ses paketi işleme hatası: {e}")
if __name__ == "__main__":
    sf = SensorFusion()
    sf.run()