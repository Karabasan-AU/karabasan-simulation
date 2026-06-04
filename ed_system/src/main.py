import sys
import os

#Python'a "İki kat yukarı çık ve ana proje klasörünü de modül arama yoluna ekle"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import zmq
import json
import base64
import numpy as np
# Yeni yazdığımız analog modülünü içeri aktarıyoruz
from analog_demod import AnalogDemodulator
from digital_demod import DigitalDemodulator
import time
from shared.profiler import measure_latency

class SIGINT_Demodulator:
    def __init__(self, config_file='shared/config.json'):
        # Yapılandırmayı yükle
        with open(config_file, 'r') as f:
            self.config = json.load(f)
            
        self.context = zmq.Context()
        self.poller = zmq.Poller()

        # Sensör Füzyonuna veri yollamak için PUB soketi
        self.fusion_pub = self.context.socket(zmq.PUB)
        #self.fusion_pub.connect("tcp://host.docker.internal:5556")
        #(Lokal test için):
        self.fusion_pub.connect("tcp://127.0.0.1:5557")
        
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
        # --- YENİ: İSTATİSTİK SAYAÇLARI ---
        self.total_digital_blocks = 0
        self.valid_digital_blocks = 0

         # ↓↓↓ BURASI EKLENİYOR ↓↓↓
        self.quarantine_blocks = 0

        # --- YENİ: KARANTİNA PUB SOKETI ---
        # Mevcut fusion_pub (5557) üzerinde yeni bir topic açıyoruz.
        # Ayrı port gerektirmez; sensor_fusion.py sadece subscribe ekler.
        # Ana döngüyü kilitlemez: NOBLOCK bayrağı ile fire-and-forget çalışır.
        self.quarantine_pub = self.context.socket(zmq.PUB)
        self.quarantine_pub.setsockopt(zmq.SNDHWM, 500)   # HWM: kuyruk taşarsa eski paketi at
        self.quarantine_pub.setsockopt(zmq.LINGER, 0)      # Kapatmada beklemez
        self.quarantine_pub.connect("tcp://127.0.0.1:5557")

    def _setup_sockets(self):
        # 1. Jeneratörden (Sinyal Kaynağı) gelen I/Q verisi için adres (5555)
        raw_gen_addr = self.config.get("sockets", {}).get("generators_to_sim", {}).get("address", "tcp://127.0.0.1:5555")
        gen_addr = raw_gen_addr.replace("zmq://", "tcp://")

        # 2. Gözcüden (Detector) gelen uyandırma paketleri için adres (5556)
        detector_addr = "tcp://127.0.0.1:5556"

        # --- I/Q Veri Akışı (Sadece 5555'ten dinliyoruz) ---
        self.iq_sub = self.context.socket(zmq.SUB)
        self.iq_sub.connect(gen_addr)
        self.iq_sub.setsockopt_string(zmq.SUBSCRIBE, "ed.iq")
        
        # --- Uyandırma / Parametre Hattı (Gözcüden 5556'ya bağlandık) ---
        self.params_sub = self.context.socket(zmq.SUB)
        self.params_sub.connect(detector_addr) 
        self.params_sub.setsockopt_string(zmq.SUBSCRIBE, "ed.params")
        # İçi boş string! Önüne gelen her paketi içeri al demek.
        #self.params_sub.setsockopt_string(zmq.SUBSCRIBE, "")
        
        # --- Yapay Zeka (AMC) Çıkarımları (İhtiyaca göre 5555 veya 5556 olabilir) ---
        self.mod_sub = self.context.socket(zmq.SUB)
        self.mod_sub.connect(gen_addr)
        self.mod_sub.setsockopt_string(zmq.SUBSCRIBE, "ed.modulation")

        # Kontrol hatlarını poller'a kaydet (Uyanma ve Modülasyon hatlarını dinliyoruz)
        self.poller.register(self.params_sub, zmq.POLLIN)
        self.poller.register(self.mod_sub, zmq.POLLIN)
        # I/Q hattını da dinlemeye ekliyoruz ki sinyal gelince işlemeye başlasın
        self.poller.register(self.iq_sub, zmq.POLLIN)

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
                # --- AJAN SATIRI EKLİYORUZ ---
                print(f"[AĞ KONTROL] Gözcüden kapıya mesaj geldi: {msg.decode('utf-8')}")
                # -----------------------------
                self._handle_params(json.loads(msg.decode('utf-8')))
                
            if self.mod_sub in socks:
                topic, msg = self.mod_sub.recv_multipart()
                self._handle_modulation(json.loads(msg.decode('utf-8')))
                
            # --- 2. VERİ HATTI (I/Q Akışı) ---
            if self.iq_sub in socks:
                topic, msg = self.iq_sub.recv_multipart()
                
                # Eğer sistem aktifse veriyi işle
                if self.active_target:
                    # KRONOMETREYİ BURADA BAŞLATIYORUZ (Sinyal kapıdan girdi)
                    pipeline_start = time.perf_counter()
                    
                    iq_data = np.frombuffer(msg, dtype=np.complex64)
                    
                    if self.current_mode == "Analog":
                        self.analog_pipeline(iq_data, pipeline_start)
                    elif self.current_mode == "Sayisal":
                        self.digital_pipeline(iq_data, self.current_modulation, pipeline_start)

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

    def analog_pipeline(self, iq_data, pipeline_start):
        # 1. Analog DSP çalışır (Ses deşifre edilir)
        clean_audio = self.analog_dsp.process_block(iq_data)
        
        # ⏱️ 2. KRONOMETREYİ DURDURUYORUZ
        pipeline_end = time.perf_counter()
        total_latency_ms = round((pipeline_end - pipeline_start) * 1000.0, 3)
        
        # 📦 3. SES TAMPON (BUFFER) VE FORMAT OPTİMİZASYONU
        # NumPy dizisindeki sesi UI ekibinin tarayıcıda çalabileceği Base64 metnine çeviriyoruz
        audio_bytes = clean_audio.tobytes()
        audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        
        # 🚀 4. PAKETİ OLUŞTUR VE SENSÖR FÜZYONUNA FIRLAT
        # UI ile anlaştığımız demodulation sözleşmesine göre paketi hazırlıyoruz
        audio_packet = json.dumps({
            "event": "demodulation",
            "audio_chunk_b64": audio_b64,
            "processing_latency_ms": total_latency_ms
        })
        self.fusion_pub.send_multipart([b"fusion.audio", audio_packet.encode('utf-8')])
        
        # Terminali de bilgilendiriyoruz
        print(f"[DSP LOG] Analog ses fırlatıldı! Çıktı veri boyutu: {len(clean_audio)} | İşlem Gecikmesi: {total_latency_ms} ms")

    def digital_pipeline(self, iq_data, mod_type, pipeline_start):
        self.total_digital_blocks += 1
        synced_symbols, payload, crc_valid = self.digital_dsp.process_block(iq_data, mod_type)

        if crc_valid and payload:
            self.valid_digital_blocks += 1

            pipeline_end = time.perf_counter()
            total_latency_ms = round((pipeline_end - pipeline_start) * 1000.0, 3)

            simulated_packet_str = (
                f"DRONE_ID: XY-99 | Veri: {payload[:10]} | "
                f"Gecikme: {total_latency_ms} ms | CRC_Gecerli: {crc_valid}"
            )
            self.fusion_pub.send_multipart(
                [b"fusion.telemetry", simulated_packet_str.encode('utf-8')]
            )

        else:
            # ── KARANTİNA HATTI ──────────────────────────────────────────────
            # KTRSinyalİzleme: "FEC algoritmaları dinamik olarak koşturulur,
            # ardından CRC ile doğrulanır." — CRC'den geçemeyen paket çöpe
            # atılmak yerine ed.quarantine topic'ine iletilir; SIGINT modülü
            # veya ileriki FEC yeniden işleme (reprocessing) katmanı tüketir.
            #
            # TASARIM KARARLARI:
            #   • zmq.NOBLOCK → ana döngü asla bloklanmaz (17.5W CPU bütçesi)
            #   • zmq.Again  → kuyruk doluysa paketi sessizce bırak (log yok)
            #   • synced_symbols varsa Base64 ile taşı; yoksa None geç
            # ─────────────────────────────────────────────────────────────────
            self.quarantine_blocks += 1

            symbols_b64 = None
            if synced_symbols is not None and len(synced_symbols) > 0:
                symbols_b64 = base64.b64encode(
                    synced_symbols.astype(np.complex64).tobytes()
                ).decode('utf-8')

            quarantine_packet = json.dumps({
                "event":          "quarantine",
                "mod_type":       mod_type,
                "block_id":       self.total_digital_blocks,
                "timestamp":      time.time(),
                "symbols_b64":    symbols_b64,   # Ham semboller: FEC katmanı işler
                "payload_raw":    list(payload[:32]) if payload else None,
                "reason":         "CRC_FAIL",
                "pipeline_age_ms": round((time.perf_counter() - pipeline_start) * 1000.0, 3)
            })

            try:
                self.quarantine_pub.send_multipart(
                    [b"ed.quarantine", quarantine_packet.encode('utf-8')],
                    zmq.NOBLOCK   # ← kritik: ana döngüyü yavaşlatmaz
                )
            except zmq.Again:
                pass  # HWM doluysa paketi sessizce bırak

        # --- SPAMSIZ İSTATİSTİK RAPORU ---
        if self.total_digital_blocks > 0 and self.total_digital_blocks % 100 == 0:
            garbage_blocks = self.total_digital_blocks - self.valid_digital_blocks
            drop_rate = (garbage_blocks / self.total_digital_blocks) * 100

            print(
                f"📊 [DSP RAPORU] İşlenen: {self.total_digital_blocks} | "
                f"Başarılı: {self.valid_digital_blocks} | "
                f"Karantina: {self.quarantine_blocks} | "
                f"Çöpe Atılan: {garbage_blocks - self.quarantine_blocks} | "
                f"Filtreleme: %{drop_rate:.1f}"
            )

if __name__ == "__main__":
    sigint_module = SIGINT_Demodulator()
    sigint_module.run()