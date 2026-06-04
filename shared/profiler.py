import time
import functools

# Projenin merkezi loglama sistemini çağırıyoruz
from .logger import get_logger

# Bu dosya çalıştığında logs/shared.profiler.log adında kayıt tutacak
logger = get_logger(__name__)

def measure_latency(func):
    """
    Kullanıldığı fonksiyonun çalışma süresini milisaniye hassasiyetinde ölçer.
    Merkezi logger üzerinden DEBUG seviyesinde sisteme kaydeder.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter() # ⏱️ Kronometre Başla
        
        result = func(*args, **kwargs)   # ⚙️ Asıl fonksiyonu çalıştır
        
        end_time = time.perf_counter()   # ⏱️ Kronometre Durdur
        
        latency_ms = (end_time - start_time) * 1000.0
        
        # Terminale ve log dosyasına yazdırıyoruz
        logger.debug(f"[PERFORMANS] '{func.__name__}' fonksiyonu {latency_ms:.3f} ms sürdü.")
        
        return result
    return wrapper