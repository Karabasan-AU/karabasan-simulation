"""
et_system/main.py — ET Sistem HTTP Sunucusu

UI'dan gelen REST komutlarını karşılar, ilgili modüle yönlendirir.
ZMQ üzerinden sim_engine'e karıştırma sinyali gönderir.

Kullanım:
    uvicorn et_system.main:app --host 0.0.0.0 --port 8000
"""

import json
from pathlib import Path

import zmq
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.logger import get_logger
from et_system.jammer import Jammer
from et_system.spoofer import Spoofer
from et_system.duty_cycle import DutyCycleGuard

logger = get_logger("et_system.main")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).parent.parent / "shared" / "config.json"


def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


cfg = _load_config()

# ---------------------------------------------------------------------------
# ZMQ — et_to_sim soketi
# ---------------------------------------------------------------------------

_zmq_context = zmq.Context()
_et_pub = _zmq_context.socket(zmq.PUB)
_et_pub.bind(
    cfg["sockets"]["et_to_sim"]["address"].replace("zmq://", "tcp://")
)
logger.info(
    "ET ZMQ soketi bağlandı: %s",
    cfg["sockets"]["et_to_sim"]["address"],
)

# ---------------------------------------------------------------------------
# Modüller
# ---------------------------------------------------------------------------

_duty_guard = DutyCycleGuard(
    max_tx_seconds=cfg.get("et", {}).get("max_tx_seconds", 30),
    cooldown_seconds=cfg.get("et", {}).get("cooldown_seconds", 10),
)
_jammer = Jammer(zmq_pub=_et_pub, duty_guard=_duty_guard)
_spoofer = Spoofer(zmq_pub=_et_pub, duty_guard=_duty_guard)

# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(title="ET System", version="1.0.0")


# ── Request body şemaları ──────────────────────────────────────────────────

class JamContinuousRequest(BaseModel):
    frequency_hz: float = 433_000_000.0
    power_w: float = 20.0
    duration_s: float | None = None  # None → süreli değil, manuel durdur


class JamSweepRequest(BaseModel):
    frequency_hz: float = 433_000_000.0
    bandwidth_hz: float = 10_000_000.0
    power_w: float = 20.0
    duration_s: float | None = None


class SpoofVoiceRequest(BaseModel):
    frequency_hz: float = 145_000_000.0
    ctcss_hz: float = 88.5
    audio_file: str = "inject.wav"


class SpoofGnssRequest(BaseModel):
    target_lat: float = 39.925
    target_lon: float = 32.837
    target_alt_m: float = 100.0


# ── Endpointler ───────────────────────────────────────────────────────────

@app.post("/jam/continuous/start")
def jam_continuous_start(req: JamContinuousRequest):
    logger.info(
        "Sürekli karıştırma komutu alındı — frekans: %.3f MHz, güç: %.1f W",
        req.frequency_hz / 1e6,
        req.power_w,
    )
    try:
        _jammer.start_continuous(
            frequency_hz=req.frequency_hz,
            power_w=req.power_w,
            duration_s=req.duration_s,
        )
        return {"status": "ok", "mode": "CONTINUOUS", "frequency_hz": req.frequency_hz}
    except RuntimeError as exc:
        logger.warning("Karıştırma reddedildi: %s", exc)
        raise HTTPException(status_code=429, detail=str(exc))


@app.post("/jam/sweep/start")
def jam_sweep_start(req: JamSweepRequest):
    logger.info(
        "Baraj karıştırma komutu alındı — merkez: %.3f MHz, bant: %.1f MHz",
        req.frequency_hz / 1e6,
        req.bandwidth_hz / 1e6,
    )
    try:
        _jammer.start_barrage(
            frequency_hz=req.frequency_hz,
            bandwidth_hz=req.bandwidth_hz,
            power_w=req.power_w,
            duration_s=req.duration_s,
        )
        return {"status": "ok", "mode": "BARRAGE", "frequency_hz": req.frequency_hz}
    except RuntimeError as exc:
        logger.warning("Baraj karıştırma reddedildi: %s", exc)
        raise HTTPException(status_code=429, detail=str(exc))


@app.post("/jam/stop")
def jam_stop():
    _jammer.stop()
    logger.info("Karıştırma durduruldu.")
    return {"status": "ok", "mode": "STOPPED"}


@app.post("/spoof/voice/start")
def spoof_voice_start(req: SpoofVoiceRequest):
    logger.info(
        "Ses aldatma komutu alındı — frekans: %.3f MHz, CTCSS: %.1f Hz",
        req.frequency_hz / 1e6,
        req.ctcss_hz,
    )
    try:
        _spoofer.start_voice(
            frequency_hz=req.frequency_hz,
            ctcss_hz=req.ctcss_hz,
            audio_file=req.audio_file,
        )
        return {"status": "ok", "mode": "VOICE_SPOOF", "frequency_hz": req.frequency_hz}
    except RuntimeError as exc:
        logger.warning("Ses aldatma reddedildi: %s", exc)
        raise HTTPException(status_code=429, detail=str(exc))


@app.post("/spoof/gnss/start")
def spoof_gnss_start(req: SpoofGnssRequest):
    logger.info(
        "GNSS aldatma komutu alındı — konum: (%.5f, %.5f, %.1f m)",
        req.target_lat,
        req.target_lon,
        req.target_alt_m,
    )
    try:
        _spoofer.start_gnss(
            target_lat=req.target_lat,
            target_lon=req.target_lon,
            target_alt_m=req.target_alt_m,
        )
        return {"status": "ok", "mode": "GNSS_SPOOF"}
    except RuntimeError as exc:
        logger.warning("GNSS aldatma reddedildi: %s", exc)
        raise HTTPException(status_code=429, detail=str(exc))


@app.post("/spoof/stop")
def spoof_stop():
    _spoofer.stop()
    logger.info("Aldatma durduruldu.")
    return {"status": "ok", "mode": "STOPPED"}


@app.get("/status")
def status():
    return {
        "jammer": _jammer.status(),
        "spoofer": _spoofer.status(),
        "duty_guard": _duty_guard.status(),
    }