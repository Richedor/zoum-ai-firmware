"""
Driver GPS — SIM7600 via NMEA + AT.

Interfaces :
  /dev/ttyUSB1 : flux NMEA continu (GGA, RMC, VTG, GSA)
  /dev/ttyUSB2 : commandes AT (init GNSS, RSSI, opérateur)

Données remontées :
  lat, lon, altitude_m, speed_gps_kmh, heading_deg,
  fix_quality, satellites, hdop, gps_timestamp,
  signal_strength_rssi, network_type, operator
"""
from __future__ import annotations
import time
import threading
import serial
import pynmea2

_nmea_thread = None
_stop_event = threading.Event()
_lock = threading.Lock()

# Cache GPS (mis à jour en continu par le thread NMEA)
_data = {
    "lat": 0.0,
    "lon": 0.0,
    "altitude_m": 0.0,
    "speed_gps_kmh": 0.0,
    "heading_deg": 0.0,
    "fix_quality": 0,
    "satellites": 0,
    "hdop": 99.9,
    "gps_ok": False,
    "gps_timestamp": "",
    # Réseau (via AT)
    "signal_strength_rssi": -1,
    "network_type": "UNKNOWN",
    "operator": "",
}

# Ports mémorisés pour refresh réseau
_at_port = "/dev/ttyUSB2"
_baud = 115200


def init(nmea_port: str = "/dev/ttyUSB1", at_port: str = "/dev/ttyUSB2",
         baud: int = 115200) -> bool:
    """Initialise le GNSS via AT et lance le thread NMEA."""
    global _nmea_thread, _at_port, _baud
    _at_port = at_port
    _baud = baud

    # Activer GNSS via AT
    try:
        _at_init(at_port, baud)
    except Exception as e:
        print(f"[GPS] AT init warning: {e}")

    # Lire réseau
    try:
        _update_network_info(at_port, baud)
    except Exception as e:
        print(f"[GPS] Network info warning: {e}")

    # Thread NMEA
    _stop_event.clear()
    _nmea_thread = threading.Thread(
        target=_nmea_loop, args=(nmea_port, baud),
        daemon=True, name="gps-nmea",
    )
    _nmea_thread.start()
    print(f"[GPS] Thread NMEA démarré sur {nmea_port}")
    return True


def _at_send(port: str, baud: int, cmd: str, timeout: float = 1.0) -> str:
    """Envoie une commande AT et retourne la réponse."""
    with serial.Serial(port, baud, timeout=timeout) as s:
        s.reset_input_buffer()
        s.write((cmd + "\r").encode())
        time.sleep(0.3)
        return s.read(2048).decode(errors="ignore").strip()


def _at_init(port: str, baud: int):
    """Active le GNSS sur le SIM7600."""
    resp = _at_send(port, baud, "AT")
    if "OK" not in resp and "AT" not in resp:
        print(f"[GPS] SIM7600 non détecté (AT → {resp!r})")
        return
    for cmd in ["AT+CGNSSMODE=1", "AT+CGPS=0", "AT+CGPS=1"]:
        _at_send(port, baud, cmd)
        time.sleep(0.3)
    print("[GPS] GNSS activé via AT")


def _update_network_info(port: str, baud: int):
    """Récupère RSSI + type réseau + opérateur via AT."""
    global _data

    # RSSI : +CSQ: 18,99 → RSSI = -113 + 2*18 = -77 dBm
    resp = _at_send(port, baud, "AT+CSQ")
    for line in resp.split("\n"):
        if "+CSQ:" in line:
            try:
                parts = line.split(":")[1].strip().split(",")
                csq = int(parts[0])
                if 0 < csq < 31:
                    with _lock:
                        _data["signal_strength_rssi"] = -113 + 2 * csq
            except (ValueError, IndexError):
                pass

    # Opérateur : +COPS: 0,0,"Orange F",7
    resp = _at_send(port, baud, "AT+COPS?")
    for line in resp.split("\n"):
        if "+COPS:" in line:
            try:
                parts = line.split(",")
                if len(parts) >= 4:
                    op = parts[2].strip('"')
                    act = int(parts[3].strip())
                    act_map = {0: "2G", 2: "3G", 7: "4G", 11: "5G-NSA", 12: "5G"}
                    with _lock:
                        _data["operator"] = op
                        _data["network_type"] = act_map.get(act, f"ACT{act}")
            except (ValueError, IndexError):
                pass


def _nmea_loop(port: str, baud: int):
    """Thread : lit les trames NMEA en continu."""
    reconnect_delay = 1.0

    while not _stop_event.is_set():
        try:
            with serial.Serial(port, baud, timeout=1) as ser:
                reconnect_delay = 1.0
                while not _stop_event.is_set():
                    line = ser.readline().decode(errors="ignore").strip()
                    if not line.startswith("$"):
                        continue
                    try:
                        msg = pynmea2.parse(line)
                    except pynmea2.ParseError:
                        continue
                    _process_nmea(msg)
        except serial.SerialException as e:
            print(f"[GPS] Port perdu: {e} — reconnexion {reconnect_delay:.0f}s")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)
        except Exception as e:
            print(f"[GPS] Erreur NMEA: {e}")
            time.sleep(1)


def _process_nmea(msg):
    """Parse une trame NMEA et met à jour le cache."""
    global _data

    with _lock:
        # GGA : fix, sats, altitude, hdop
        if isinstance(msg, pynmea2.types.talker.GGA):
            q = int(msg.gps_qual or 0)
            sats = int(msg.num_sats or 0) if msg.num_sats else 0
            _data["fix_quality"] = q
            _data["satellites"] = sats
            _data["gps_ok"] = q > 0
            if q > 0 and msg.latitude:
                _data["lat"] = round(msg.latitude, 6)
                _data["lon"] = round(msg.longitude, 6)
                _data["altitude_m"] = round(float(msg.altitude or 0), 1)
            if msg.horizontal_dil:
                _data["hdop"] = round(float(msg.horizontal_dil), 1)

        # RMC : position, vitesse, cap, timestamp
        elif isinstance(msg, pynmea2.types.talker.RMC):
            if msg.status == "A" and msg.latitude:
                _data["lat"] = round(msg.latitude, 6)
                _data["lon"] = round(msg.longitude, 6)
                _data["gps_ok"] = True
                if msg.spd_over_grnd:
                    _data["speed_gps_kmh"] = round(float(msg.spd_over_grnd) * 1.852, 1)
                if msg.true_course:
                    _data["heading_deg"] = round(float(msg.true_course), 1)
                _data["gps_timestamp"] = str(msg.datetime) if msg.datetime else ""

        # VTG : vitesse + cap (plus précis)
        elif isinstance(msg, pynmea2.types.talker.VTG):
            if hasattr(msg, "spd_over_grnd_kmph") and msg.spd_over_grnd_kmph:
                try:
                    _data["speed_gps_kmh"] = round(float(msg.spd_over_grnd_kmph), 1)
                except (ValueError, TypeError):
                    pass
            if hasattr(msg, "true_track") and msg.true_track:
                try:
                    _data["heading_deg"] = round(float(msg.true_track), 1)
                except (ValueError, TypeError):
                    pass

        # GSA : DOP
        elif isinstance(msg, pynmea2.types.talker.GSA):
            if hasattr(msg, "hdop") and msg.hdop:
                try:
                    _data["hdop"] = round(float(msg.hdop), 1)
                except (ValueError, TypeError):
                    pass


def read() -> dict:
    """Retourne une copie du cache GPS courant."""
    with _lock:
        return dict(_data)


def refresh_network(at_port: str = None, baud: int = None):
    """Met à jour les infos réseau (appeler périodiquement, ex: toutes les 30s)."""
    try:
        _update_network_info(at_port or _at_port, baud or _baud)
    except Exception:
        pass


def cleanup():
    _stop_event.set()
    if _nmea_thread and _nmea_thread.is_alive():
        _nmea_thread.join(timeout=3)
