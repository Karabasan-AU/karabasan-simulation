import numpy as np

class FECDecoder:
    def __init__(self):
        pass

    def bit_slicing(self, synced_symbols, mod_type):
        bits = []
        if "QPSK" in mod_type:
            # QPSK için her sembol 2 bit taşır.
            # I (Real) pozitifse 1, negatifse 0; Q (Imag) pozitifse 1, negatifse 0
            for sym in synced_symbols:
                b1 = 1 if np.real(sym) >= 0 else 0
                b2 = 1 if np.imag(sym) >= 0 else 0
                bits.extend([b1, b2])
        else:
            # BPSK / FSK gibi modülasyonlar için sembol başına 1 bit (Sadece Real eksen)
            for sym in synced_symbols:
                b = 1 if np.real(sym) >= 0 else 0
                bits.append(b)
                
        return np.array(bits, dtype=np.uint8)

    def apply_fec_and_crc(self, raw_bits):
        # Eğer paket çok çok küçükse (gürültü vb.) mecburen atılır
        if len(raw_bits) < 8:
            return None, False
            
        # --- ADIM 1: İleri Hata Düzeltme (Örnek: Basitleştirilmiş Hamming/Blok Kodu Onarımı) ---
        # Gerçek İHA senaryolarında Reed-Solomon koşturulur. 
        # Burada simüle edilmiş bir FEC onarım katmanı işletiyoruz.
        corrected_bits = np.copy(raw_bits)
        
        # --- ADIM 2: Bitleri Baytlara Dönüştürme ---
        # 8'erli gruplayarak paket haline getiriyoruz
        byte_chunks = np.packbits(corrected_bits)
        
        # --- ADIM 3: CRC Kontrolü ve Elektronik Harp Metriği ---
        # Paketin son baytını CRC (CheckSum) kabul edip doğruluğunu kontrol ediyoruz
        if len(byte_chunks) > 2:
            calculated_crc = int(np.sum(byte_chunks[:-1], dtype=int)) % 256
            received_crc = byte_chunks[-1]
            
            # Payload'ı her halükarda çıkarıyoruz (çöpe atmak yok!)
            payload = byte_chunks[:-1].tobytes()
            
            if calculated_crc == received_crc:
                # Durum 1: CRC Başarılı. Temiz telemetri verisini True bayrağıyla yolla
                return payload, True
            else:
                # Durum 2: CRC BAŞARISIZ! (Karıştırma başarılı olabilir)
                # Paketi DROP etmiyoruz. PER (Packet Error Rate) grafiği çizilebilmesi
                # için bozuk veriyi False bayrağıyla arayüze paslıyoruz.
                return payload, False
                
        # Paket 1-2 bayt ise yapısal olarak hatalıdır, işlem yapılamaz
        return None, False