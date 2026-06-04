import numpy as np                   
import json
from pathlib import Path            
import time
import zmq

C = 299792458
FREQUENCY_HZ = 433e6       # Watson-Watt için
WAVELENGTH   = C / FREQUENCY_HZ  # λ hesabı için
ANTENNA_SPACING_M = 0.05    # d/λ oranı için /// change later, this is random
sigma2 = 1e-15 #look into hackrf noise


base_path = Path("C:/Users/serhat/Desktop/karabasan-simulation")
file_path = base_path / "shared" / "config.json"

_CONFIG_PATH = Path(__file__).parent.parent / "shared" / "config.json"


def readJson():
    try:
        with open(file_path,"r") as file:
            data = json.load(file)
        print("file data: ",data)
    except Exception as err:
        print("Error: ",err)
    return data

def fsplLineer(distanceA): #Free Space Path Loss
    distanceA=max(distanceA,0.01)
    FSPL = np.power((4*(np.pi)*(distanceA)*(433e6) / C),2)
    return FSPL

def receivedPower(FSPL,dbPower): #How much power is left for the antenna
    return dbPower / FSPL #linear, dont forget

def antennaLocation(systemPos, d): #d is antenna spacing
    cx, cy = systemPos
    pos = {
        "N":[cx,cy+d],
        "S":[cx,cy-d],
        "E":[cx+d,cy],
        "W":[cx-d,cy]
    }
    return pos

def simulatePower(targetPos, systemPos, d, originalPower):
    originalPowerLin = 10**(originalPower / 10)
    
    # Merkez istasyonun hedefe olan gerçek mesafesi ve FSPL kaybı
    distance = np.linalg.norm(np.array(targetPos) - np.array(systemPos))
    fspl = fsplLineer(distance)
    center_power = receivedPower(fspl, originalPowerLin)
    
    targetY = targetPos[1] - systemPos[1]
    targetX = targetPos[0] - systemPos[0]
    true_angle = np.arctan2(targetY, targetX)
    
    powers = {}
    powers["N"] = center_power * (1 + np.sin(true_angle))
    powers["S"] = center_power * (1 - np.sin(true_angle))
    powers["E"] = center_power * (1 + np.cos(true_angle))
    powers["W"] = center_power * (1 - np.cos(true_angle))
    
    for name in powers:
        noise = np.sqrt(sigma2 / 2) * np.random.randn()
        powers[name] = max(powers[name] + noise, 1e-12)
        
    return powers

def calculateSNR(originalPower, targetPos, systemPos):
    originalPowerLin = 10**(originalPower / 10)

    distance = np.linalg.norm(np.array(targetPos) - np.array(systemPos))
    receivedPowerA = receivedPower(fsplLineer(distance), originalPowerLin)

    snrLin = receivedPowerA / sigma2 
    return snrLin

def watsonWatt(powers):
    total_power = powers["N"] + powers["S"] + powers["E"] + powers["W"]

    y = (powers["N"] - powers["S"]) / total_power
    x = (powers["E"] - powers["W"]) / total_power

    bearing = np.degrees(np.arctan2(y, x)) % 360
    
    return bearing


def crlb(SNR):
    crlb_rad_sq = 1 / ((2**2) * (ANTENNA_SPACING_M / WAVELENGTH) * (SNR**2))
    
    crlb_deg_sq = crlb_rad_sq * (180.0 / np.pi)**2
    return crlb_deg_sq


def weightedLob(variances, bearings, systems):
    systems = np.asarray(systems)
    bearings = np.radians(np.asarray(bearings))
    variances = np.asarray(variances)

    A = np.zeros((2, 2))
    b = np.zeros(2)

    for i in range(2):
        Sx, Sy = systems[i]
        theta = bearings[i]
        sin_t = np.sin(theta)
        cos_t = np.cos(theta)

        A[i, 0] = sin_t
        A[i, 1] = -cos_t
        b[i] = (sin_t * Sx - cos_t * Sy)

    # Ağırlık = 1 / Varyans
    weights = 1.0 / variances

    # Matrisi ağırlıkla çarpıyoruz
    At_W = A.T * weights
    left_side = At_W @ A
    right_side = At_W @ b

    if np.linalg.matrix_rank(left_side) < 2:
        raise ValueError("Doğrular birbirine paralel veya kesişim yok")
    
    target_pos = np.linalg.solve(left_side, right_side)
    return target_pos.tolist()


def monteCarlos(target, system1, system2, n, originalPower=40):
    rmseBearing = 0
    rmseMeters = 0
    count = 0
    json_stream = []
    start_time = time.time()

    system1_pos = [system1["x"], system1["y"]]
    system2_pos = [system2["x"], system2["y"]]

    while count < n:
        current_time = start_time + time.time()
        target_pos_true = trackTarget(target, current_time, start_time)

        p1 = simulatePower(target_pos_true, system1_pos, ANTENNA_SPACING_M, originalPower)
        p2 = simulatePower(target_pos_true, system2_pos, ANTENNA_SPACING_M, originalPower)
        
        b1 = watsonWatt(p1)
        b2 = watsonWatt(p2)
        
        snr1 = calculateSNR(originalPower, target_pos_true, system1_pos)
        snr2 = calculateSNR(originalPower, target_pos_true, system2_pos)
        v1 = crlb(snr1)  
        v2 = crlb(snr2)
        
        targetY = (target_pos_true[1] - system1["y"])
        targetX = (target_pos_true[0] - system1["x"])
        targetBearing_deg = np.degrees(np.arctan2(targetY, targetX)) % 360

        angle_diff = (b1 - targetBearing_deg + 180) % 360 - 180
        rmseBearing += angle_diff**2
        count += 1
        
        try:
            intendedMeters = weightedLob([v1, v2], [b1, b2], [system1_pos, system2_pos])
            rmseMeters += (np.linalg.norm(target_pos_true - np.array(intendedMeters)))**2

            paket = convertToJSON(
                target_id=target.get("id", "TGT-001"),
                b1=b1,
                intendedMeters=intendedMeters,
                SNR=snr1,
                bearingRMSE=np.sqrt(rmseBearing / count)
            )
            json_stream.append(paket)

        except ValueError:
            continue 

    rmseBearing = np.sqrt(rmseBearing / n)
    rmseMeters = np.sqrt(rmseMeters / n)

    t_id = target.get("id", "TGT-001")
    convertToJSON(t_id, b1, intendedMeters, snr1, rmseBearing, output_filename=f"{t_id}_final.json")

    return rmseBearing, rmseMeters, b1, intendedMeters, targetBearing_deg, json.dumps(json_stream, indent=4, ensure_ascii=False)

def convertToJSON(target_id, b1, intendedMeters, SNR, bearingRMSE, output_filename=None):
    confidence = max(0.0, min(1.0, 1.0 - (bearingRMSE / 25.0)))
    snr_db = 10 * np.log10(max(SNR, 1e-15))

    geolocation = {
        "id": target_id,
        "timestamp": float(time.time()),
        "latitude": float(intendedMeters[1]),  
        "longitude": float(intendedMeters[0]), 
        "azimuth_deg": float(b1),
        "method": "amplitude",                     
        "snr_db": snr_db,
        "confidence":confidence
    }

    if output_filename:
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(geolocation, f, indent=4, ensure_ascii=False)

    return geolocation

def trackTarget(target,current_time,start_time):

    if target.get("type")=="moving":
        
        delta_t=current_time-start_time

        raw_x = target["x0"] + target["xV"] * delta_t
        raw_y = target["y0"] + target["yV"] * delta_t

        current_x = raw_x % 2000   #target moves back in the area, like zigzag
        if current_x > 1000:
            current_x = 2000 - current_x
            
        current_y = raw_y % 2000
        if current_y > 1000:
            current_y = 2000 - current_y

        return np.array([current_x, current_y])
    return np.array([target["x"], target["y"]])

def runZmq(System1, System2, config_data):
    address = config_data["sockets"]["generators_to_sim"]["address"].replace("zmq://", "tcp://")
    
    context = zmq.Context()
    sub = context.socket(zmq.SUB)
    
    sub.setsockopt_string(zmq.SUBSCRIBE, "ed.iq") 
    
    sub.connect(address)
    time.sleep(2)
    
    sub.setsockopt(zmq.RCVTIMEO, 5000)

    est_target = [500, 500]
    target_id = "TGT-001"

    print(f"ZMQ dinleniyor: {address}...")

    while True:
        try:
            message = sub.recv_multipart()
            topic, rawIQData = message
            
            rawIQ = np.frombuffer(rawIQData, dtype=np.complex64)
            realSignal = 10 * np.log10(np.mean(np.abs(rawIQ)**2) + 1e-12)

            p1 = simulatePower(est_target, [System1["x"], System1["y"]], ANTENNA_SPACING_M, realSignal)
            p2 = simulatePower(est_target, [System2["x"], System2["y"]], ANTENNA_SPACING_M, realSignal)

            b1, b2 = watsonWatt(p1), watsonWatt(p2)
            pos = weightedLob([1.0, 1.0], [b1, b2], [[System1["x"], System1["y"]], [System2["x"], System2["y"]]])

            est_target = pos

            liveJSON = convertToJSON(
                target_id=target_id,
                b1=b1,
                intendedMeters=pos,
                SNR=realSignal,
                bearingRMSE=0.0
            )
            
            print(json.dumps(liveJSON, indent=4))
            print(f"Öngörülen Konum: {pos} | Açı: {b1}")

        except zmq.Again:
            print("Sinyal gelmiyor, bekleniyor...")
            continue
        except Exception as e:
            print(f"Hata oluştu: {e}")
            break



if __name__ == "__main__":
    data = readJson()
    
    sys1 = data["systems"][0]
    sys2 = data["systems"][1]
    static_target = data["targets"][0]
    moving_target = data["targets"][1]
    
    print("\nSimülasyon Başlatılıyor...")

    
    iterations = 1000
    tx_power = 20

    mode = input("Mod seçin [S]/[C]: ").upper()
    if mode == 'C':
        runZmq(sys1,sys2,data)
    else:
        bearing_rmse, distance_rmse, b1, konum, aci, json_stream_static = monteCarlos(static_target, sys1, sys2, n=iterations, originalPower=tx_power)
        print("\n--- STATIC MONTE CARLO SONUÇLARI ---")
        print(f"Gerçek Konum: [{static_target['x']}, {static_target['y']}] | Ölçülen Konum: [{konum[0]}, {konum[1]}]")
        print(f"Açı RMSE: {bearing_rmse}° | Konum RMSE: {distance_rmse:.2f} metre")

        bearing_rmse, distance_rmse, b1, konum, aci, json_stream_dynamic = monteCarlos(moving_target, sys1, sys2, n=iterations, originalPower=tx_power)
        print("\n--- DYNAMIC MONTE CARLO SONUÇLARI ---")
        print(f"Başlangıç Konumu: [{moving_target['x0']}, {moving_target['y0']}] | Son Ölçülen Konum: [{konum[0]}, {konum[1]}]")
        print(f"Açı RMSE: {bearing_rmse}° | Konum RMSE: {distance_rmse:} metre")
        print()

