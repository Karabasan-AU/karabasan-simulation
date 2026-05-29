"""
shared/logger.py — Merkezi Loglama Modülü

Kullanım:
    from shared.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Sinyal tespit edildi.")
    logger.debug("FFT boyutu: %d", 1024)
    logger.warning("SNR düşük: %.1f dB", 3.2)
    logger.error("ZMQ bağlantısı kurulamadı.")
"""

import logging
import json
import os
import sys
from datetime import timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
_CONFIG_PATH = Path(__file__).parent / "config.json"
_LOGS_DIR = Path(__file__).parent.parent / "logs"
_DEFAULT_LEVEL = "INFO"
_DEFAULT_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"   # ISO 8601


def _load_log_config() -> dict:
    """config.json'dan logging bloğunu okur. Dosya yoksa ya da hatalıysa varsayılanları döner."""
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("logging", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_logger(module_name: str) -> logging.Logger:
    """
    Modül adına göre yapılandırılmış bir logger döner.

    Parametreler
    ----------
    module_name : str
        Genellikle __name__ geçirilir.
        Örnek: get_logger(__name__)  →  logger adı "ed_system.detector" olur.

    Döndürür
    -------
    logging.Logger
        Hem terminale (stdout) hem logs/<module_name>.log dosyasına yazan logger.

    Notlar
    ------
    - Log seviyesi shared/config.json → logging.level alanından okunur.
    - Aynı modül adıyla ikinci kez çağrılırsa mevcut logger döner (handler çoğalmaz).
    """
    log_cfg = _load_log_config()
    level_str = log_cfg.get("level", _DEFAULT_LEVEL).upper()
    level = getattr(logging, level_str, logging.INFO)
    fmt = log_cfg.get("format", _DEFAULT_FORMAT)

    logger = logging.getLogger(module_name)

    # Aynı logger ikinci kez yapılandırılmasın
    if logger.handlers:
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(fmt=fmt, datefmt=_DATE_FORMAT)
    # ISO 8601 zaman damgası için UTC offset ekle
    formatter.converter = lambda *args: __import__("datetime").datetime.now(timezone.utc).timetuple()

    # --- Terminal handler (stdout) ---
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # --- Dosya handler: logs/<module_name>.log ---
    # module_name "ed_system.detector" gibi noktalı gelebilir → "ed_system.detector.log"
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = _LOGS_DIR / f"{module_name}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Üst logger'a mesaj iletimini kapat (çift yazdırmayı önler)
    logger.propagate = False

    return logger


def set_level(module_name: str, level: str) -> None:
    """
    Çalışma zamanında bir modülün log seviyesini değiştir.

    Parametreler
    ----------
    module_name : str
        Logger adı (get_logger'a geçirilen değerle aynı).
    level : str
        "DEBUG" | "INFO" | "WARNING" | "ERROR"

    Örnek
    -----
        from shared.logger import set_level
        set_level("sim_engine", "DEBUG")
    """
    logger = logging.getLogger(module_name)
    numeric = getattr(logging, level.upper(), None)
    if numeric is None:
        raise ValueError(f"Geçersiz log seviyesi: '{level}'. Geçerli değerler: DEBUG, INFO, WARNING, ERROR")
    logger.setLevel(numeric)
    for handler in logger.handlers:
        handler.setLevel(numeric)