"""
sim_engine/channel.py — RF Kanal Simülasyonu

generators'dan ZMQ üzerinden gelen I/Q akışına FSPL ve AWGN uygular,
sonucu ed_system'in dinlediği ZMQ soketine yayınlar.

Kullanım:
    python -m sim_engine.channel
"""

import json
import numpy as np
import zmq
from pathlib import Path
from shared.logger import get_logger

logger = get_logger("sim_engine.channel")

_CONFIG_PATH = Path(__file__).parent.parent / "shared" / "config.json"


def load_config() -> dict:
    """shared/config.json'u okur."""
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def apply_fspl(iq: np.ndarray, frequency_hz: float, distance_m: float) -> np.ndarray:
    """
    Free Space Path Loss uygular.

    FSPL(dB) = 20·log10(4π·d·f / c)

    Sinyal genliği bu kayba göre ölçeklenir:
        scale = 10^(−FSPL_dB / 20)

    Parametreler
    ----------
    iq : np.ndarray (complex)
        Giriş I/Q dizisi.
    frequency_hz : float
        Taşıyıcı frekans (Hz).
    distance_m : float
        Karıştırıcı-alıcı mesafesi (m).

    Döndürür
    -------
    np.ndarray (complex)
        Ölçeklenmiş I/Q dizisi.
    """
    c = 3e8
    fspl_db = 20 * np.log10((4 * np.pi * distance_m * frequency_hz) / c)
    scale = 10 ** (-fspl_db / 20)

    logger.debug(
        "FSPL uygulandı — frekans: %.3f MHz, mesafe: %.1f m, FSPL: %.2f dB, ölçek: %.6f",
        frequency_hz / 1e6,
        distance_m,
        fspl_db,
        scale,
    )

    return iq * scale


def apply_awgn(iq: np.ndarray, snr_db: float) -> np.ndarray:
    """
    Additive White Gaussian Noise ekler.

    Sinyal gücünden SNR hedefine göre gürültü gücü hesaplanır:
        N_power = S_power / 10^(SNR_dB / 10)

    Karmaşık gürültü: her bileşen N(0, σ²/2), σ² = N_power

    Parametreler
    ----------
    iq : np.ndarray (complex)
        Giriş I/Q dizisi (FSPL uygulanmış).
    snr_db : float
        Hedef SNR değeri (dB).

    Döndürür
    -------
    np.ndarray (complex)
        Gürültü eklenmiş I/Q dizisi.
    """
    signal_power = np.mean(np.abs(iq) ** 2)
    noise_power = signal_power / (10 ** (snr_db / 10))
    sigma = np.sqrt(noise_power / 2)

    noise = sigma * (
        np.random.randn(len(iq)) + 1j * np.random.randn(len(iq))
    )

    logger.debug(
        "AWGN eklendi — hedef SNR: %.1f dB, sinyal gücü: %.6f, gürültü gücü: %.6f",
        snr_db,
        signal_power,
        noise_power,
    )

    return iq + noise


def run():
    """
    Ana döngü.

    generators → [ZMQ SUB] → FSPL + AWGN → [ZMQ PUB] → ed_system
    """
    cfg = load_config()

    sim_cfg = cfg["simulation"]
    snr_db = sim_cfg["awgn_snr_db"]
    frame_size = sim_cfg["signal_length"]
    speed_of_light = sim_cfg["speed_of_light"]
    distance_m = sim_cfg.get("distance_m", 200.0)
    frequency_hz = sim_cfg["center_freq"] if sim_cfg["center_freq"] != 0.0 else 433e6

    zmq_cfg = cfg["sockets"]
    input_addr = zmq_cfg["generators_to_sim"]["address"].replace("zmq://", "tcp://")
    output_addr = zmq_cfg["sim_to_ed"]["address"].replace("zmq://", "tcp://")

    logger.info(
        "Kanal başlatılıyor — frekans: %.3f MHz, mesafe: %.1f m, SNR: %.1f dB",
        frequency_hz / 1e6,
        distance_m,
        snr_db,
    )

    context = zmq.Context()

    sub_socket = context.socket(zmq.SUB)
    sub_socket.connect(input_addr)
    sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

    pub_socket = context.socket(zmq.PUB)
    pub_socket.bind(output_addr)

    logger.info("ZMQ hazır — giriş: %s, çıkış: %s", input_addr, output_addr)

    frames_processed = 0

    try:
        while True:
            raw = sub_socket.recv()
            iq = np.frombuffer(raw, dtype=np.complex64).copy()

            iq = apply_fspl(iq, frequency_hz, distance_m)
            iq = apply_awgn(iq, snr_db)

            pub_socket.send(iq.tobytes())

            frames_processed += 1
            if frames_processed % 100 == 0:
                logger.info("%d frame işlendi.", frames_processed)

    except KeyboardInterrupt:
        logger.info(
            "Kanal durduruldu. Toplam işlenen frame: %d", frames_processed
        )
    finally:
        sub_socket.close()
        pub_socket.close()
        context.term()


if __name__ == "__main__":
    run()