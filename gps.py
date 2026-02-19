#!/usr/bin/env python3
import time
import serial
import pynmea2

AT_PORT = "/dev/ttyUSB2"
NMEA_PORT = "/dev/ttyUSB1"
BAUD = 115200

def at_send(cmd, timeout=1.0, wait=0.25):
    with serial.Serial(AT_PORT, BAUD, timeout=timeout) as s:
        s.reset_input_buffer()
        s.write((cmd + "\r").encode())
        time.sleep(wait)
        return s.read(2048).decode(errors="ignore").strip()

def try_gnss_init():
    print("AT init...")
    for cmd in [
        "AT",
        "AT+CGNSSMODE=1",     # ok chez toi
        "AT+CGPS?",           # juste pour info
        "AT+CGPS=0",          # reset soft (optionnel)
        "AT+CGPS=1",          # peut faire ERROR selon firmware
        "AT+CGPS?",           # re-check
    ]:
        resp = at_send(cmd)
        print(f"{cmd} => {resp or '(no reply)'}")

def ddmm_to_deg(v, hemi):
    if not v:
        return None
    # lat: ddmm.mmmm / lon: dddmm.mmmm
    if hemi in ("N", "S"):
        d = int(v[:2]); m = float(v[2:])
    else:
        d = int(v[:3]); m = float(v[3:])
    deg = d + m / 60.0
    return -deg if hemi in ("S", "W") else deg

def main():
    try_gnss_init()

    print(f"\nListening NMEA on {NMEA_PORT} @ {BAUD} (Ctrl+C pour quitter)")
    with serial.Serial(NMEA_PORT, BAUD, timeout=1) as ser:
        while True:
            line = ser.readline().decode(errors="ignore").strip()
            if not line.startswith("$"):
                continue

            # parse NMEA
            try:
                msg = pynmea2.parse(line)
            except pynmea2.ParseError:
                continue

            # GGA = fix + sats + altitude
            if isinstance(msg, pynmea2.types.talker.GGA):
                q = int(msg.gps_qual or 0)
                sats = int(msg.num_sats or 0) if msg.num_sats else 0
                lat = ddmm_to_deg(msg.lat, msg.lat_dir)
                lon = ddmm_to_deg(msg.lon, msg.lon_dir)
                alt = float(msg.altitude) if msg.altitude else None

                if q > 0:
                    print(f"GGA: FIX q={q} sats={sats:02d} lat={lat} lon={lon} alt={alt}")
                else:
                    print(f"GGA: NOFIX sats={sats:02d}")

            # RMC = date/heure + validité + vitesse
            elif isinstance(msg, pynmea2.types.talker.RMC):
                status = msg.status  # 'A' valid, 'V' void
                lat = ddmm_to_deg(msg.lat, msg.lat_dir)
                lon = ddmm_to_deg(msg.lon, msg.lon_dir)
                spd_kn = float(msg.spd_over_grnd) if msg.spd_over_grnd else 0.0
                if status == "A":
                    print(f"RMC: FIX lat={lat} lon={lon} speed={spd_kn}kn")
                else:
                    print("RMC: NOFIX")

if __name__ == "__main__":
    main()
