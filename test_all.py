#!/usr/bin/env python3
"""
test_all.py — Test unifié de tous les périphériques IoT (Pi Zero)
  - IMX219 (caméra)
  - DHT22  (température / humidité)
  - MQ-9   (capteur de gaz)
  - GPS    (SIM7600 via AT + NMEA)
  - RFID   (PN532 I2C)
  - OLED   (SSD1306 I2C)
  - Buzzer (GPIO PWM)
"""

import os
import time
import sys
from datetime import datetime

# ──────────────────────────── CONFIG ────────────────────────────
DHT_GPIO      = 4          # board.D4
GAS_PIN       = 17         # GPIO 17 (DO du MQ-9)
BUZZER_PIN    = 27         # GPIO 27 (buzzer passif)
BUZZER_FREQ   = 2000       # Hz
GPS_AT_PORT   = "/dev/ttyUSB2"
GPS_NMEA_PORT = "/dev/ttyUSB1"
GPS_BAUD      = 115200
_BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
# fatigue-lite : dossier autonome avec tous les modules
FATIGUE_LITE_DIR = os.path.join(_BASE_DIR, "fatigue-lite")

# ──────────────────────────── HELPERS ───────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

results = {}   # nom -> (ok: bool, detail: str)

def header(txt):
    print(f"\n{CYAN}{BOLD}{'─'*50}")
    print(f"  {txt}")
    print(f"{'─'*50}{RESET}")

def ok(name, detail=""):
    results[name] = (True, detail)
    print(f"  {GREEN}✔ {name}: {detail}{RESET}")

def fail(name, detail=""):
    results[name] = (False, detail)
    print(f"  {RED}✘ {name}: {detail}{RESET}")

# ──────────────────────────── TESTS ─────────────────────────────

# 1) OLED SSD1306
def test_oled():
    header("1/7 — OLED SSD1306 (I2C)")
    try:
        import board
        import adafruit_ssd1306
        from PIL import Image, ImageDraw, ImageFont

        i2c = board.I2C()
        oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)
        oled.fill(0)
        oled.show()

        img = Image.new("1", (128, 64))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        draw.text((10, 5),  "TEST IoT", font=font, fill=255)
        draw.text((10, 25), "En cours...", font=font, fill=255)
        oled.image(img)
        oled.show()

        ok("OLED", "Affichage OK (128x64)")
        return oled
    except Exception as e:
        fail("OLED", str(e))
        return None


# 2) DHT22
def test_dht22():
    header("2/7 — DHT22 (Température / Humidité)")
    try:
        import board
        import adafruit_dht

        pin_map = {4: board.D4, 17: board.D17, 27: board.D27}
        dht = adafruit_dht.DHT22(pin_map.get(DHT_GPIO, board.D4))

        temp, hum = None, None
        for attempt in range(5):
            try:
                temp = dht.temperature
                hum  = dht.humidity
                if temp is not None and hum is not None:
                    break
            except RuntimeError:
                time.sleep(2)

        dht.exit()

        if temp is not None:
            ok("DHT22", f"Temp={temp:.1f}°C  Humidité={hum}%")
            return temp, hum
        else:
            fail("DHT22", "Pas de lecture après 5 tentatives")
            return None, None
    except Exception as e:
        fail("DHT22", str(e))
        return None, None


# 3) MQ-9 (gaz)
def test_mq9():
    header("3/7 — MQ-9 (Capteur de gaz)")
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(GAS_PIN, GPIO.IN)

        val = GPIO.input(GAS_PIN)
        gas = (val == GPIO.LOW)

        if gas:
            ok("MQ-9", "Gaz détecté ! (vérifiez l'environnement)")
        else:
            ok("MQ-9", "Air normal — capteur actif")
        return gas
    except Exception as e:
        fail("MQ-9", str(e))
        return None


# 4) Détection de fatigue (Caméra + UltraFace + Head Nod + Bâillements)
def test_fatigue():
    header("4/7 — Détection de fatigue (Head Nod + Bâillements)")
    cam = None
    try:
        # Ajouter fatigue-lite/ au path (dossier autonome)
        if FATIGUE_LITE_DIR not in sys.path:
            sys.path.insert(0, FATIGUE_LITE_DIR)

        from camera import Camera
        from face_detector import UltraFaceDetector
        from head_nod import HeadNodDetector
        from fatigue_fusion import FatigueFusion
        from yawn_detector import YawnDetector

        details = []

        # 4a) Caméra
        print(f"  {YELLOW}Démarrage caméra...{RESET}")
        cam = Camera(source=0)
        time.sleep(1)
        ret, frame = cam.read()
        if not ret or frame is None:
            fail("FATIGUE", "Caméra : pas de frame")
            cam.release()
            return False
        h, w = frame.shape[:2]
        details.append(f"Cam {w}x{h}")

        # 4b) Détection de visage (UltraFace)
        print(f"  {YELLOW}Chargement modèle UltraFace...{RESET}")
        detector = UltraFaceDetector()
        faces = detector.detect(frame)
        face = UltraFaceDetector.largest_face(faces) if len(faces) > 0 else None
        if face is not None:
            details.append(f"{len(faces)} visage(s)")
        else:
            details.append("0 visage (normal si personne devant)")

        # 4c) Head Nod Detector
        print(f"  {YELLOW}Test Head Nod Detector...{RESET}")
        nod_det = HeadNodDetector()
        if face is not None:
            nod_det.add_calibration_sample(face, h)
            nod_det.update(face, h)
            details.append(f"HeadNod OK (dev={nod_det.deviation:+.2f})")
        else:
            details.append("HeadNod chargé (pas de visage)")

        # 4d) Yawn Detector
        print(f"  {YELLOW}Test Yawn Detector...{RESET}")
        yawn_det = YawnDetector()
        if face is not None:
            mouth = yawn_det.extract_mouth_roi(frame, face)
            if mouth is not None:
                details.append(f"Bouche ROI {mouth.shape[1]}x{mouth.shape[0]}")
            else:
                details.append("ROI bouche non extrait")
        else:
            details.append("Yawn chargé (pas de visage)")

        # 4e) Fatigue Fusion
        fusion = FatigueFusion()
        lvl, _, _ = fusion.update(nod_det.nod_count, nod_det.is_microsleep,
                                  nod_det.head_down_duration, yawn_det.yawn_count)
        details.append(f"Fusion → {fusion.level_name}")

        cam.release()
        ok("FATIGUE", " | ".join(details))
        return True

    except Exception as e:
        fail("FATIGUE", str(e))
        try:
            if cam is not None:
                cam.release()
        except Exception:
            pass
        return False


# 5) GPS (SIM7600)
def test_gps():
    header("5/7 — GPS (SIM7600 AT + NMEA)")
    try:
        import serial
        import pynmea2

        # Envoi des commandes AT d'initialisation
        def at_send(cmd, timeout=1.0, wait=0.3):
            with serial.Serial(GPS_AT_PORT, GPS_BAUD, timeout=timeout) as s:
                s.reset_input_buffer()
                s.write((cmd + "\r").encode())
                time.sleep(wait)
                return s.read(2048).decode(errors="ignore").strip()

        resp_at = at_send("AT")
        if "OK" not in resp_at and "AT" not in resp_at:
            fail("GPS", f"Module SIM non détecté (AT → {resp_at!r})")
            return None

        # Tenter d'activer le GNSS
        for cmd in ["AT+CGNSSMODE=1", "AT+CGPS=0", "AT+CGPS=1"]:
            at_send(cmd)

        time.sleep(1)

        # Lire quelques trames NMEA (timeout 10 s)
        fix_info = None
        deadline = time.time() + 10
        with serial.Serial(GPS_NMEA_PORT, GPS_BAUD, timeout=1) as ser:
            while time.time() < deadline:
                line = ser.readline().decode(errors="ignore").strip()
                if not line.startswith("$"):
                    continue
                try:
                    msg = pynmea2.parse(line)
                except pynmea2.ParseError:
                    continue

                if isinstance(msg, pynmea2.types.talker.GGA):
                    q    = int(msg.gps_qual or 0)
                    sats = int(msg.num_sats or 0) if msg.num_sats else 0
                    if q > 0 and msg.lat:
                        fix_info = f"FIX sats={sats} lat={msg.lat} lon={msg.lon}"
                        break
                    elif sats > 0:
                        fix_info = f"NOFIX (sats={sats} visibles)"

                # On accepte aussi un RMC valide
                elif isinstance(msg, pynmea2.types.talker.RMC):
                    if msg.status == "A" and msg.lat:
                        fix_info = f"FIX lat={msg.lat} lon={msg.lon}"
                        break

        if fix_info and "FIX" in fix_info and "NOFIX" not in fix_info:
            ok("GPS", fix_info)
        elif fix_info:
            ok("GPS", f"Module actif — {fix_info} (fix en cours)")
        else:
            ok("GPS", "Module AT OK — pas de trame NMEA avec fix (normal en intérieur)")
        return fix_info

    except Exception as e:
        fail("GPS", str(e))
        return None


# 6) RFID PN532
def test_rfid():
    header("6/7 — RFID PN532 (I2C)")
    try:
        import board
        import busio
        from adafruit_pn532.i2c import PN532_I2C

        i2c = busio.I2C(board.SCL, board.SDA)
        pn532 = PN532_I2C(i2c, debug=False)

        ic, ver, rev, support = pn532.firmware_version
        fw = f"{ic}.{ver}.{rev}"

        pn532.SAM_configuration()

        print(f"  {YELLOW}Approchez une carte NFC (5 sec)...{RESET}")
        uid = None
        deadline = time.time() + 5
        while time.time() < deadline:
            uid = pn532.read_passive_target(timeout=0.3)
            if uid is not None:
                break
            time.sleep(0.05)

        if uid is not None:
            uid_str = ":".join(f"{b:02X}" for b in uid)
            ok("RFID", f"Firmware {fw} — Carte lue UID={uid_str}")
            return uid_str
        else:
            ok("RFID", f"Firmware {fw} — Aucune carte (timeout 5 s)")
            return None
    except Exception as e:
        fail("RFID", str(e))
        return None


# 7) Buzzer (GPIO PWM)
def test_buzzer():
    header("7/7 — Buzzer (GPIO PWM)")
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUZZER_PIN, GPIO.OUT)

        pwm = GPIO.PWM(BUZZER_PIN, BUZZER_FREQ)

        # 3 bips courts pour confirmer que ça marche
        print(f"  {YELLOW}3 bips de test...{RESET}")
        for i in range(3):
            pwm.start(50)     # duty cycle 50%
            time.sleep(0.15)
            pwm.stop()
            time.sleep(0.1)

        ok("BUZZER", f"GPIO {BUZZER_PIN} — 3 bips @ {BUZZER_FREQ} Hz")
        return True
    except Exception as e:
        fail("BUZZER", str(e))
        return False


# ──────────────── AFFICHAGE RÉSUMÉ SUR OLED ─────────────────────

def show_results_oled(oled):
    if oled is None:
        return
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("1", (128, 64))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()

        draw.text((0, 0), "== RESULTATS ==", font=font, fill=255)
        y = 12
        for name, (passed, _) in results.items():
            tag = "OK" if passed else "FAIL"
            draw.text((0, y), f"{name}: {tag}", font=font, fill=255)
            y += 10
            if y > 54:
                break

        oled.image(img)
        oled.show()
    except Exception:
        pass


# ──────────────────────────── MAIN ──────────────────────────────

def main():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{BOLD}{CYAN}")
    print("╔══════════════════════════════════════════════════╗")
    print("║        TEST UNIFIÉ — PÉRIPHÉRIQUES IoT          ║")
    print("║              Raspberry Pi Zero                   ║")
    print(f"║  {ts}                        ║")
    print("╚══════════════════════════════════════════════════╝")
    print(RESET)

    # --- Exécution séquentielle (évite conflits I2C / GPIO) ---
    oled         = test_oled()
    temp, hum    = test_dht22()
    gas          = test_mq9()
    fatigue_ok   = test_fatigue()
    gps_info     = test_gps()
    rfid_uid     = test_rfid()
    buzzer_ok    = test_buzzer()

    # --- Résumé console ---
    header("RÉSUMÉ")
    passed = sum(1 for v in results.values() if v[0])
    total  = len(results)
    for name, (status, detail) in results.items():
        tag = f"{GREEN}OK{RESET}" if status else f"{RED}FAIL{RESET}"
        print(f"  [{tag}] {name}: {detail}")

    print(f"\n  {BOLD}{passed}/{total} périphériques fonctionnels{RESET}\n")

    # --- Résumé sur l'OLED ---
    show_results_oled(oled)

    # --- Nettoyage GPIO ---
    try:
        import RPi.GPIO as GPIO
        GPIO.cleanup()
    except Exception:
        pass

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
