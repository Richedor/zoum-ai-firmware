"""
Zoum AI Firmware — Configuration complète.

Variables d'environnement (.env) surchargent les valeurs par défaut.
"""
from __future__ import annotations
import os

# ─────────────────────────────────────────────
# API
# ─────────────────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "http://192.168.137.1:8000")

# ─────────────────────────────────────────────
# Provisioning (identité du kit)
# ─────────────────────────────────────────────
ORG_ID     = os.getenv("ORG_ID",     "00000000-0000-4000-a000-000000000001")
VEHICLE_ID = os.getenv("VEHICLE_ID", "00000000-0000-4000-a000-000000000003")
KIT_ID     = os.getenv("KIT_ID",     "00000000-0000-4000-a000-000000000004")
KIT_SERIAL = os.getenv("KIT_SERIAL", "ZOUM-DEMO-001")
KIT_KEY    = os.getenv("KIT_KEY",    "de6332ae7d19673163871f2004b6add079521bef71191b7a5fa95e8892fc6271")

# ─────────────────────────────────────────────
# Buffer local (SQLite)
# ─────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "zoum_buffer.sqlite3")

# ─────────────────────────────────────────────
# Timing
# ─────────────────────────────────────────────
TELEMETRY_INTERVAL_S = int(os.getenv("TELEMETRY_INTERVAL_S", "2"))
SYNC_INTERVAL_S      = int(os.getenv("SYNC_INTERVAL_S", "5"))
BATCH_SIZE           = int(os.getenv("BATCH_SIZE", "50"))

# ─────────────────────────────────────────────
# GPIO — Capteurs
# ─────────────────────────────────────────────
DHT_GPIO    = int(os.getenv("DHT_GPIO",    "4"))    # DHT22 data
GAS_GPIO    = int(os.getenv("GAS_GPIO",    "17"))   # MQ-9/MQ-3 digital out
BUZZER_GPIO = int(os.getenv("BUZZER_GPIO", "27"))   # Buzzer passif
BUZZER_FREQ = int(os.getenv("BUZZER_FREQ", "2000"))

# ─────────────────────────────────────────────
# GPIO — LED RGB (cathode commune)
# ─────────────────────────────────────────────
LED_R_GPIO = int(os.getenv("LED_R_GPIO", "22"))
LED_G_GPIO = int(os.getenv("LED_G_GPIO", "23"))
LED_B_GPIO = int(os.getenv("LED_B_GPIO", "24"))

# ─────────────────────────────────────────────
# GPIO — Boutons (pull-up interne, press = GND)
# ─────────────────────────────────────────────
BTN_START_GPIO = int(os.getenv("BTN_START_GPIO", "5"))
BTN_STOP_GPIO  = int(os.getenv("BTN_STOP_GPIO",  "6"))
BTN_MENU_GPIO  = int(os.getenv("BTN_MENU_GPIO",  "13"))
BTN_BACK_GPIO  = int(os.getenv("BTN_BACK_GPIO",  "19"))

# ─────────────────────────────────────────────
# GPS (SIM7600)
# ─────────────────────────────────────────────
GPS_NMEA_PORT = os.getenv("GPS_NMEA_PORT", "/dev/ttyUSB1")
GPS_AT_PORT   = os.getenv("GPS_AT_PORT",   "/dev/ttyUSB2")
GPS_BAUD      = int(os.getenv("GPS_BAUD",  "115200"))

# ─────────────────────────────────────────────
# Alcooltest
# ─────────────────────────────────────────────
ALCOHOL_WARMUP_S = int(os.getenv("ALCOHOL_WARMUP_S", "20"))
ALCOHOL_BLOW_S   = int(os.getenv("ALCOHOL_BLOW_S",   "7"))

# ─────────────────────────────────────────────
# Seuils alertes
# ─────────────────────────────────────────────
TEMP_WARN_C     = float(os.getenv("TEMP_WARN_C",     "40"))
TEMP_CRITICAL_C = float(os.getenv("TEMP_CRITICAL_C", "50"))
