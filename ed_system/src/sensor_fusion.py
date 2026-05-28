import zmq
import json
import time

class SensorFusion:
    def __init__(self, config_file='../../shared/config.json'):
        with open(config_file, 'r') as f:
            self.config = json.load(f)
            
        self.context = zmq.Context()
        
        # 1. Veri Alma (Subscriber) Soketi
        self.fusion_sub = self.context.socket(zmq.SUB)
        self.fusion_sub.bind("tcp://0.0.0.0:5556")  # Dışarıya açık arayüz
        self.fusion_sub.setsockopt_string(zmq.SUBSCRIBE, "fusion.telemetry")
        self.fusion_sub.setsockopt_string(zmq.SUBSCRIBE, "fusion.audio")
        self.fusion_sub.setsockopt_string(zmq.SUBSCRIBE, "ed.geolocation")
        
        # SİHİRLİ DOKUNUŞ: Ctrl+C'nin donmasını engelleyecek Poller yapısı
        self.poller = zmq.Poller()
        self.poller.register(self.fusion_sub, zmq.POLLIN)
        
        # 2. Taarruz Tetikleme (Publisher) Soketi
        self.trigger_pub = self.context.socket(zmq.PUB)
        self.trigger_pub.bind("tcp://0.0.0.0:5557") 
        
        # 3. Arayüz (UI) Soketi
        self.ui_pub = self.context.socket(zmq.PUB)
        self.ui_pub.bind("tcp://0.0.0.0:5558")
        
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
                        pass
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

if __name__ == "__main__":
    sf = SensorFusion()
    sf.run()