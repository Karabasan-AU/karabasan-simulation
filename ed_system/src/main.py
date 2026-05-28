import zmq
import json
import numpy as np
# Yeni yazdığımız analog modülünü içeri aktarıyoruz
from analog_demod import AnalogDemodulator
from digital_demod import DigitalDemodulator

class SIGINT_Demodulator:
    def __init__(self, config_file='shared/config.json'):
        # Yapılandırmayı yükle
        with open(config_file, 'r') as f:
            self.config = json.load(f)
            
        self.context = zmq.Context()
        self.poller = zmq.Poller()

        # Sensör Füzyonuna veri yollamak için PUB soketi
        self.fusion_pub = self.context.socket(zmq.PUB)
        self.fusion_pub.connect("tcp://host.docker.internal:5556")
        
        # Sinyal işleme sınıfımızı başlatıyoruz
        # config.json içindeki sample rate değerlerini parametre olarak veriyoruz
        self.analog_dsp = AnalogDemodulator(
            input_sample_rate=self.config.get('input_sample_rate', 2400000),
            audio_sample_rate=self.config.get('audio_sample_rate', 48000)
        )
        self.digital_dsp = DigitalDemodulator(
            sample_rate=self.config.get('input_sample_rate', 2400000)
        )
        # Soketleri başlat
        self._setup_sockets()
        
        # Anlık durum takibi
        self.active_target = False
        self.current_mode = None  
        self.current_modulation = None 

    def _setup_sockets(self):
        # I/Q Veri Akışı 
        self.iq_sub = self.context.socket(zmq.SUB)
        self.iq_sub.connect(self.config['ed_source'])
        self.iq_sub.setsockopt_string(zmq.SUBSCRIBE, "ed.iq")
        
        # Operatör veya ED Parametreleri 
        self.params_sub = self.context.socket(zmq.SUB)
        self.params_sub.connect(self.config['ed_source'])
        self.params_sub.setsockopt_string(zmq.SUBSCRIBE, "ed.params")
        
        # Yapay Zeka (AMC) Çıkarımları [cite: 68, 90]
        self.mod_sub = self.context.socket(zmq.SUB)
        self.mod_sub.connect(self.config['ed_source'])
        self.mod_sub.setsockopt_string(zmq.SUBSCRIBE, "ed.modulation")

        # Kontrol hatlarını poller'a kaydet (İşlemci bütçesini korumak için uyku modu) 
        self.poller.register(self.params_sub, zmq.POLLIN)
        self.poller.register(self.mod_sub, zmq.POLLIN)

    def run(self):
        print("[SIGINT] Olay Güdümlü Dinleme Başladı. Tehdit bekleniyor...")
        
        # I/Q hattını da Poller'a dahil ediyoruz
        self.poller.register(self.iq_sub, zmq.POLLIN)
        
        while True:
            # SİHİRLİ DOKUNUŞ: timeout'u sabit bırakıyoruz. 
            # Veri gelmezse CPU'yu dinlendirir, veri gelirse ANINDA uyanır!
            socks = dict(self.poller.poll(timeout=1000))
            
            # --- 1. KONTROL HATLARI (Öncelikli) ---
            if self.params_sub in socks:
                topic, msg = self.params_sub.recv_multipart()
                self._handle_params(json.loads(msg.decode('utf-8')))
                
            if self.mod_sub in socks:
                topic, msg = self.mod_sub.recv_multipart()
                self._handle_modulation(json.loads(msg.decode('utf-8')))
                
            # --- 2. VERİ HATTI (I/Q Akışı) ---
            if self.iq_sub in socks:
                topic, msg = self.iq_sub.recv_multipart()
                
                # Eğer sistem aktifse veriyi işle
                if self.active_target:
                    iq_data = np.frombuffer(msg, dtype=np.complex64)
                    
                    if self.current_mode == "Analog":
                        self.analog_pipeline(iq_data)
                    elif self.current_mode == "Sayisal":
                        self.digital_pipeline(iq_data, self.current_modulation)

    def _handle_params(self, params):
        if params.get("status") == "active" and params.get("type") == "Analog":
            print("[TETİKLEME] Analog yayın tespit edildi. Analog hat uyandırılıyor.")
            self.active_target = True
            self.current_mode = "Analog"
        elif params.get("status") == "inactive":
            print("[BİLGİ] Hedef yayını kesildi. Uyku moduna geçiliyor.")
            self.active_target = False

    def _handle_modulation(self, mod_data):
        if mod_data.get("status") == "active":
            print(f"[TETİKLEME] Sayısal yayın ({mod_data.get('class')}) tespit edildi.")
            self.active_target = True
            self.current_mode = "Sayisal"
            self.current_modulation = mod_data.get("class")
        elif mod_data.get("status") == "inactive":
            self.active_target = False

    def analog_pipeline(self, iq_data):
        # Yazdığımız analog DSP fonksiyonunu çağırıyoruz
        clean_audio = self.analog_dsp.process_block(iq_data)
        
        # Test amaçlı çıktı logu (Sürekli akışta terminali boğmamak için)
        #if np.random.rand() < 0.01: 
        print(f"[DSP LOG] Analog ses işleniyor. Çıktı veri boyutu: {len(clean_audio)}")

    def digital_pipeline(self, iq_data, mod_type):
        # Dijital demodülatör artık sembolleri, payload'u ve CRC durumunu döndürüyor
        synced_symbols, payload, crc_valid = self.digital_dsp.process_block(iq_data, mod_type)
        
        if crc_valid and payload:
            print(f"[SIGINT TELEMETRİ] Paket Deşifre Edildi! Veri: {payload}")
            # Burada elde edilen veri Sensör Füzyonu'na (Sensör Fusion) gönderilecek
        # --- YENİ EKLENEN KISIM: Veriyi Sensör Füzyonuna Gönder ---
            # Simülasyon gereği, test jeneratöründen gelen rastgele byte'ları string'e çevirip içine "DRONE_ID" ekleyelim ki kural tetiklensin
            simulated_packet_str = f"DRONE_ID: XY-99 | Veri: {payload[:10]}"
            self.fusion_pub.send_multipart([b"fusion.telemetry", simulated_packet_str.encode('utf-8')])
        # DİKKAT: Bu satır fonksiyonun içinde (4 boşluk içeride) olmalı!
        #if np.random.rand() < 0.01:
        print(f"[DSP LOG] Dijital hat devrede ({mod_type}). Senkronize sembol sayısı: {len(synced_symbols)}")

if __name__ == "__main__":
    sigint_module = SIGINT_Demodulator()
    sigint_module.run()