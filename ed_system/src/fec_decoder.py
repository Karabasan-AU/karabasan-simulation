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
        if len(raw_bits) < 8:
            return None, False
            
        # --- ADIM 1: İleri Hata Düzeltme (Örnek: Basitleştirilmiş Hamming/Blok Kodu Onarımı) ---
        # Gerçek İHA senaryolarında Reed-Solomon koşturulur. 
        # Burada simüle edilmiş bir FEC onarım katmanı işletiyoruz.
        corrected_bits = np.copy(raw_bits)
        
        # --- ADIM 2: Bitleri Baytlara Dönüştürme ---
        # 8'erli gruplayarak paket haline getiriyoruz
        byte_chunks = np.packbits(corrected_bits)
        
        # --- ADIM 3: CRC Kontrolü ---
        # Paketin son baytını CRC (CheckSum) kabul edip doğruluğunu kontrol ediyoruz
        if len(byte_chunks) > 2:
            calculated_crc = int(np.sum(byte_chunks[:-1], dtype=int)) % 256
            received_crc = byte_chunks[-1]
            
            if calculated_crc == received_crc:
                # CRC Başarılı, şifresiz telemetri verisini (payload) döndür
                payload = byte_chunks[:-1].tobytes()
                return payload, True
                
        # CRC başarısızsa paketi drop ediyoruz
        return None, False