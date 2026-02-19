#!/usr/bin/env python3
"""
Zoum AI Firmware v2 — Pi Zero 2 W

Boucle principale :
  1. Init drivers (GPS, DHT22, MQ-9, NFC, buzzer, LED, OLED, caméra)
  2. Machine d'état (BOOT → READY → AUTH → ALCOHOL → TRIP)
  3. Collecte télémétrie + enqueue SQLite
  4. Sync thread → API FastAPI → Supabase
  5. Affichage OLED + alertes buzzer/LED

Usage :
  python3 main.py
  python3 main.py --no-vision    # sans caméra fatigue
  python3 main.py --no-display   # sans OLED
"""
from __future__ import annotations
import os
import sys
import time
import uuid
import threading
import argparse
from datetime import datetime, timezone

# ── Charger .env ─────────────────────────────────────────────────────
_base = os.path.dirname(os.path.abspath(__file__))
_env_file = os.path.join(_base, ".env")
if os.path.isfile(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

import config
from core.database import (init_db, enqueue, dequeue_batch, mark_sent,
                           mark_failed, queue_size, purge_old, lookup_badge)
from core.sync import ApiClient
from core import state_machine as sm

# ─── Version ─────────────────────────────────────────────────────────
FW_VERSION = "2.0.0"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Init drivers ────────────────────────────────────────────────────

def init_all(args) -> dict:
    """Initialise tous les drivers, retourne le statut de chacun."""
    status = {}

    # GPS
    try:
        from drivers import gps
        status["GPS"] = gps.init(config.GPS_NMEA_PORT, config.GPS_AT_PORT, config.GPS_BAUD)
    except Exception as e:
        print(f"[INIT] GPS: {e}")
        status["GPS"] = False

    # Température
    try:
        from drivers import temperature
        status["TEMP"] = temperature.init(config.DHT_GPIO)
    except Exception as e:
        print(f"[INIT] TEMP: {e}")
        status["TEMP"] = False

    # Gaz
    try:
        from drivers import gas
        status["GAS"] = gas.init(config.GAS_GPIO)
    except Exception as e:
        print(f"[INIT] GAS: {e}")
        status["GAS"] = False

    # NFC
    try:
        from drivers import nfc
        status["NFC"] = nfc.init()
    except Exception as e:
        print(f"[INIT] NFC: {e}")
        status["NFC"] = False

    # Buzzer
    try:
        from drivers import buzzer
        status["BUZZER"] = buzzer.init(config.BUZZER_GPIO, config.BUZZER_FREQ)
    except Exception as e:
        print(f"[INIT] BUZZER: {e}")
        status["BUZZER"] = False

    # LED RGB
    try:
        from drivers import led
        status["LED"] = led.init(config.LED_R_GPIO, config.LED_G_GPIO, config.LED_B_GPIO)
    except Exception as e:
        print(f"[INIT] LED: {e}")
        status["LED"] = False

    # Boutons
    try:
        from drivers import buttons
        status["BTN"] = buttons.init(config.BTN_START_GPIO, config.BTN_STOP_GPIO,
                                     config.BTN_MENU_GPIO, config.BTN_BACK_GPIO)
    except Exception as e:
        print(f"[INIT] BTN: {e}")
        status["BTN"] = False

    # OLED
    if not args.no_display:
        try:
            from drivers import display
            status["OLED"] = display.init()
        except Exception as e:
            print(f"[INIT] OLED: {e}")
            status["OLED"] = False
    else:
        status["OLED"] = False

    # Fatigue (Vision)
    if not args.no_vision:
        try:
            from core import vision
            status["CAM"] = vision.init()
        except Exception as e:
            print(f"[INIT] VISION: {e}")
            status["CAM"] = False
    else:
        status["CAM"] = False

    return status


# ─── Collecte télémétrie ─────────────────────────────────────────────

def build_telemetry_point(state: sm.State) -> dict:
    """Construit un point avec TOUTES les données capteurs."""
    from drivers import gps, temperature, gas

    gps_data = gps.read()
    temp_data = temperature.read()
    gas_data = gas.read()

    fatigue_data = {}
    try:
        from core import vision
        fatigue_data = vision.read()
    except Exception:
        pass

    return {
        "time": utc_iso(),
        "org_id": config.ORG_ID,
        "vehicle_id": config.VEHICLE_ID,
        "kit_id": config.KIT_ID,
        "trip_id": state.trip_id,

        # GPS
        "lat": gps_data.get("lat", 0.0),
        "lon": gps_data.get("lon", 0.0),
        "speed_gps_kmh": gps_data.get("speed_gps_kmh", 0.0),
        "heading_deg": gps_data.get("heading_deg", 0.0),
        "altitude_m": gps_data.get("altitude_m", 0.0),
        "gps_fix_quality": gps_data.get("fix_quality", 0),
        "gps_satellites": gps_data.get("satellites", 0),
        "gps_hdop": gps_data.get("hdop", 99.9),

        # Environnement
        "cabin_temp_c": temp_data.get("temperature_c") or 0.0,
        "cabin_humidity_pct": temp_data.get("humidity_pct") or 0.0,

        # Gaz
        "gas_detected": gas_data.get("gas_detected", False),

        # Réseau
        "signal_strength_rssi": gps_data.get("signal_strength_rssi", -1),
        "network_type": gps_data.get("network_type", "UNKNOWN"),

        # Fatigue
        "fatigue_level": fatigue_data.get("fatigue_level", 0),
        "fatigue_nod_count": fatigue_data.get("fatigue_nod_count", 0),
        "fatigue_yawn_count": fatigue_data.get("fatigue_yawn_count", 0),
        "fatigue_is_microsleep": fatigue_data.get("fatigue_is_microsleep", False),
        "fatigue_head_down_sec": fatigue_data.get("fatigue_head_down_sec", 0.0),
        "fatigue_face_detected": fatigue_data.get("fatigue_face_detected", False),

        # OBD placeholders
        "engine_rpm": 0,
        "vehicle_speed_obd_kmh": 0.0,
        "engine_load_pct": 0.0,
        "fuel_level_pct": 0.0,
        "battery_voltage": 0.0,

        # IMU placeholders
        "accel_x": 0.0, "accel_y": 0.0, "accel_z": 0.0,
        "gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0,
    }


# ─── Sync thread ─────────────────────────────────────────────────────

def sync_loop(api: ApiClient, stop_event: threading.Event):
    """Thread : flush la queue vers l'API périodiquement."""
    while not stop_event.is_set():
        try:
            purge_old(config.DB_PATH)
            batch = dequeue_batch(config.DB_PATH, limit=config.BATCH_SIZE)
            if batch:
                for rid, endpoint, payload in batch:
                    ok, msg = api.post(endpoint, payload)
                    if ok:
                        mark_sent(config.DB_PATH, [rid])
                    else:
                        mark_failed(config.DB_PATH, rid)
                        break  # stop sur erreur
        except Exception as e:
            print(f"[SYNC] Erreur: {e}")

        stop_event.wait(config.SYNC_INTERVAL_S)


# ─── Gestion d'état ──────────────────────────────────────────────────

def handle_state(state: sm.State, btn: str | None,
                 driver_status: dict, api: ApiClient):
    """Gère les transitions d'état selon boutons + événements capteurs."""
    from drivers import gps, gas, buzzer, led, nfc

    has_display = False
    try:
        from drivers import display
        has_display = True
    except Exception:
        pass

    # ── BOOT ─────────────────────────────────────────────────────────
    if state.current == sm.BOOT:
        if has_display:
            display.screen_boot(config.KIT_SERIAL, FW_VERSION, driver_status)
        led.set_named("info")
        buzzer.play("info")
        time.sleep(2)

        # Event boot
        enqueue(config.DB_PATH, "health", {
            "time": utc_iso(),
            "org_id": config.ORG_ID,
            "kit_id": config.KIT_ID,
            "event_type": "boot",
            "firmware_version": FW_VERSION,
            "drivers": {k: v for k, v in driver_status.items()},
        })

        state.transition(sm.READY)
        led.set_named("ok")
        return

    # ── READY ────────────────────────────────────────────────────────
    if state.current == sm.READY:
        gps_data = gps.read()

        if has_display:
            from drivers import temperature
            temp_data = temperature.read()
            display.screen_ready(
                driver=state.driver_name,
                gps_fix=gps_data.get("gps_ok", False),
                gps_sats=gps_data.get("satellites", 0),
                network=gps_data.get("network_type", "—"),
                rssi=gps_data.get("signal_strength_rssi", 0),
                temp_c=temp_data.get("temperature_c"),
                queue_size=queue_size(config.DB_PATH),
            )

        if btn == "start":
            state.transition(sm.AUTH_NFC)
            buzzer.play("info")
        elif btn == "menu":
            state.transition(sm.MENU)
        return

    # ── AUTH_NFC ─────────────────────────────────────────────────────
    if state.current == sm.AUTH_NFC:
        blink = int(state.time_in_state * 2) % 2 == 0
        if has_display:
            display.screen_auth_nfc(blink=blink)

        if btn == "back":
            state.reset_auth()
            state.transition(sm.READY)
            return

        # Scanner badge
        badge = nfc.scan(timeout=0.3)
        if badge:
            uid_hash = badge["uid_hash"]
            uid_hex = badge["uid"]

            # Lookup cache local
            cached = lookup_badge(config.DB_PATH, uid_hash)

            if cached:
                state.driver_id = cached["driver_id"]
                state.driver_name = cached["driver_name"]
                state.badge_uid = uid_hex
                auth_result = "success"
            else:
                # Badge inconnu → accepté offline, validé côté API
                state.driver_id = uid_hash[:8]
                state.driver_name = f"Badge {uid_hex[-8:]}"
                state.badge_uid = uid_hex
                auth_result = "offline_allowed"

            # Event NFC
            gps_data = gps.read()
            enqueue(config.DB_PATH, "nfc_auth", {
                "ts": utc_iso(),
                "org_id": config.ORG_ID,
                "kit_id": config.KIT_ID,
                "vehicle_id": config.VEHICLE_ID,
                "badge_uid_hash": uid_hash,
                "driver_id": state.driver_id,
                "auth_result": auth_result,
                "lat": gps_data.get("lat", 0),
                "lon": gps_data.get("lon", 0),
            })

            if has_display:
                display.screen_auth_result(True, state.driver_name)
            buzzer.play("success")
            led.set_named("ok")
            time.sleep(1.5)

            state.transition(sm.ALCOHOL_CHECK)
            state.reset_alcohol()
            state.alcohol_start = time.time()

        # Timeout 60s → retour
        if state.time_in_state > 60:
            state.transition(sm.READY)
        return

    # ── ALCOHOL_CHECK ────────────────────────────────────────────────
    if state.current == sm.ALCOHOL_CHECK:
        elapsed = time.time() - state.alcohol_start

        if state.alcohol_phase == sm.ALC_WARMUP:
            if has_display:
                display.screen_alcohol_warmup(elapsed, config.ALCOHOL_WARMUP_S)
            if elapsed >= config.ALCOHOL_WARMUP_S:
                state.alcohol_phase = sm.ALC_BLOW
                state.alcohol_start = time.time()
                buzzer.play("info")

        elif state.alcohol_phase == sm.ALC_BLOW:
            countdown = max(0, config.ALCOHOL_BLOW_S - elapsed)
            if has_display:
                display.screen_alcohol_blow(countdown)

            if elapsed >= config.ALCOHOL_BLOW_S:
                # Lire le capteur
                gas_data = gas.read()
                alc_fail = gas_data.get("gas_detected", False)
                ts_end = utc_iso()

                # Event alcool
                enqueue(config.DB_PATH, "alcohol", {
                    "ts_start": utc_iso(),
                    "ts_end": ts_end,
                    "org_id": config.ORG_ID,
                    "kit_id": config.KIT_ID,
                    "vehicle_id": config.VEHICLE_ID,
                    "driver_id": state.driver_id,
                    "sensor_warmup_time_s": config.ALCOHOL_WARMUP_S,
                    "ttl_state": not alc_fail,
                    "result": "fail" if alc_fail else "pass",
                })

                if alc_fail:
                    state.alcohol_result = "fail"
                    state.alcohol_phase = sm.ALC_FAIL
                    buzzer.play("critical")
                    led.blink("red", 0.3, 0.3)

                    # Alerte cloud
                    enqueue(config.DB_PATH, "alert", {
                        "ts": ts_end,
                        "org_id": config.ORG_ID,
                        "kit_id": config.KIT_ID,
                        "vehicle_id": config.VEHICLE_ID,
                        "alert_type": "alcohol_fail",
                        "severity": "critical",
                        "message": "Alcooltest échoué — trajet bloqué",
                        "meta": {"driver_id": state.driver_id},
                    })
                else:
                    state.alcohol_result = "pass"
                    state.alcohol_phase = sm.ALC_PASS
                    buzzer.play("success")
                    led.set_named("ok")

        elif state.alcohol_phase == sm.ALC_PASS:
            if has_display:
                display.screen_alcohol_pass()
            if btn == "start":
                # ── Démarrer le trajet ───────────────────────────────
                state.trip_id = str(uuid.uuid4())
                state.trip_start_time = time.time()

                gps_data = gps.read()
                enqueue(config.DB_PATH, "trip_open", {
                    "trip_id": state.trip_id,
                    "org_id": config.ORG_ID,
                    "vehicle_id": config.VEHICLE_ID,
                    "kit_id": config.KIT_ID,
                    "driver_id": state.driver_id,
                    "start_time": utc_iso(),
                    "start_lat": gps_data.get("lat", 0),
                    "start_lon": gps_data.get("lon", 0),
                    "status": "active",
                })

                # Lancer la vision / fatigue
                try:
                    from core import vision
                    if not vision._data.get("fatigue_ok"):
                        vision.start()
                except Exception:
                    pass

                state.transition(sm.TRIP_ACTIVE)
                buzzer.play("success")

        elif state.alcohol_phase == sm.ALC_FAIL:
            if has_display:
                display.screen_alcohol_fail()
            if btn == "start":
                # Refaire le test
                state.reset_alcohol()
                state.alcohol_start = time.time()
            elif btn == "back":
                state.reset_auth()
                state.reset_alcohol()
                led.stop_blink()
                led.set_named("ok")
                state.transition(sm.READY)

        # Bouton back global (sauf en FAIL déjà géré)
        if btn == "back" and state.alcohol_phase not in (sm.ALC_FAIL,):
            state.reset_auth()
            state.reset_alcohol()
            state.transition(sm.READY)
        return

    # ── TRIP_ACTIVE ──────────────────────────────────────────────────
    if state.current == sm.TRIP_ACTIVE:
        gps_data = gps.read()
        fatigue_data = {}
        try:
            from core import vision
            fatigue_data = vision.read()
        except Exception:
            pass

        elapsed_min = (time.time() - (state.trip_start_time or time.time())) / 60

        if has_display:
            display.screen_trip(
                speed_kmh=gps_data.get("speed_gps_kmh", 0),
                gps_fix=gps_data.get("gps_ok", False),
                network=gps_data.get("network_type", "—"),
                queue_size=queue_size(config.DB_PATH),
                fatigue_level=fatigue_data.get("fatigue_level", 0),
                elapsed_min=elapsed_min,
            )

        # Alertes fatigue
        fat_level = fatigue_data.get("fatigue_level", 0)
        if fat_level >= 2:
            led.blink("red", 0.2, 0.2)
            buzzer.play("critical")
            enqueue(config.DB_PATH, "alert", {
                "ts": utc_iso(),
                "org_id": config.ORG_ID,
                "kit_id": config.KIT_ID,
                "vehicle_id": config.VEHICLE_ID,
                "trip_id": state.trip_id,
                "alert_type": "fatigue_alert",
                "severity": "critical",
                "message": f"Alerte fatigue niveau {fat_level}",
                "meta": fatigue_data,
            })
        elif fat_level == 1:
            led.set_named("warning")
        else:
            led.stop_blink()
            led.set_named("ok")

        # Alerte gaz
        gas_data = gas.read()
        if gas_data.get("gas_detected", False):
            buzzer.play("critical")
            enqueue(config.DB_PATH, "alert", {
                "ts": utc_iso(),
                "org_id": config.ORG_ID,
                "kit_id": config.KIT_ID,
                "vehicle_id": config.VEHICLE_ID,
                "trip_id": state.trip_id,
                "alert_type": "gas_detected",
                "severity": "critical",
                "message": "Gaz détecté dans l'habitacle",
            })

        # Alerte température
        from drivers import temperature
        temp_data = temperature.read()
        temp_c = temp_data.get("temperature_c") or 0
        if temp_c >= config.TEMP_CRITICAL_C:
            buzzer.play("critical")
            enqueue(config.DB_PATH, "alert", {
                "ts": utc_iso(), "org_id": config.ORG_ID,
                "kit_id": config.KIT_ID, "vehicle_id": config.VEHICLE_ID,
                "trip_id": state.trip_id,
                "alert_type": "temp_critical",
                "severity": "critical",
                "message": f"Température cabine critique : {temp_c:.1f}°C",
            })
        elif temp_c >= config.TEMP_WARN_C:
            buzzer.play("warning")

        if btn == "stop":
            state.transition(sm.TRIP_STOP_CONFIRM)
            buzzer.play("info")
        elif btn == "menu":
            state.transition(sm.MENU)
        return

    # ── TRIP_STOP_CONFIRM ────────────────────────────────────────────
    if state.current == sm.TRIP_STOP_CONFIRM:
        if has_display:
            display.screen_stop_confirm()

        if btn == "start":
            # Confirmer arrêt
            gps_data = gps.read()
            enqueue(config.DB_PATH, "trip_close", {
                "trip_id": state.trip_id,
                "org_id": config.ORG_ID,
                "vehicle_id": config.VEHICLE_ID,
                "kit_id": config.KIT_ID,
                "end_time": utc_iso(),
                "end_lat": gps_data.get("lat", 0),
                "end_lon": gps_data.get("lon", 0),
                "status": "stopped_by_button",
            })

            # Arrêter la vision
            try:
                from core import vision
                vision.stop()
            except Exception:
                pass

            state.reset_trip()
            state.reset_auth()
            led.stop_blink()
            led.set_named("ok")
            buzzer.play("success")
            state.transition(sm.READY)

        elif btn == "back":
            state.transition(sm.TRIP_ACTIVE)
        return

    # ── MENU ─────────────────────────────────────────────────────────
    if state.current == sm.MENU:
        gps_data = gps.read()
        menu_data = {
            "sensors": driver_status,
            "queue_size": queue_size(config.DB_PATH),
            "last_sync": (time.strftime("%H:%M:%S", time.localtime(api.last_ok_time))
                          if api.last_ok_time else "—"),
            "sync_fails": api.consecutive_fails,
            "gps_fix": gps_data.get("gps_ok", False),
            "gps_sats": gps_data.get("satellites", 0),
            "lat": gps_data.get("lat", 0),
            "serial": config.KIT_SERIAL,
            "version": FW_VERSION,
            "uptime": f"{time.monotonic() / 60:.0f}min",
        }

        if has_display:
            display.screen_menu(state.menu_page, menu_data)

        if btn == "menu":
            state.menu_page = (state.menu_page + 1) % 4
        elif btn == "back":
            state.menu_page = 0
            state.transition(state.previous)
        return


# ─── Boucle principale ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Zoum AI Firmware")
    parser.add_argument("--no-vision", action="store_true",
                        help="Désactiver la caméra fatigue")
    parser.add_argument("--no-display", action="store_true",
                        help="Désactiver l'OLED")
    args = parser.parse_args()

    print("=" * 60)
    print(f"  Zoum AI Firmware v{FW_VERSION}")
    print(f"  Kit: {config.KIT_SERIAL}")
    print(f"  API: {config.API_BASE_URL}")
    print("=" * 60)

    # Init DB
    init_db(config.DB_PATH)

    # Init drivers
    driver_status = init_all(args)
    for name, ok in driver_status.items():
        tag = "✔" if ok else "✘"
        print(f"  {tag} {name}")

    # Init API client
    api = ApiClient(config.API_BASE_URL, config.KIT_SERIAL, config.KIT_KEY)

    # State machine
    state = sm.State()

    # Sync thread
    sync_stop = threading.Event()
    sync_thread = threading.Thread(
        target=sync_loop, args=(api, sync_stop),
        daemon=True, name="sync",
    )
    sync_thread.start()

    # Timers
    last_telemetry = 0.0
    last_network_refresh = 0.0

    print("[MAIN] Boucle principale démarrée")

    try:
        while True:
            now = time.time()

            # Lire les boutons

            btn = None
            try:
                from drivers import buttons
                btn = buttons.poll()
                if btn:
                    print(f"[DEBUG] Bouton détecté : {btn}")
            except Exception:
                pass

            # Gérer l'état
            handle_state(state, btn, driver_status, api)

            # Collecte télémétrie périodique
            if now - last_telemetry >= config.TELEMETRY_INTERVAL_S:
                if state.current in (sm.TRIP_ACTIVE, sm.READY):
                    point = build_telemetry_point(state)
                    enqueue(config.DB_PATH, "telemetry", {"points": [point]})
                    last_telemetry = now

            # Refresh réseau toutes les 30s
            if now - last_network_refresh >= 30:
                try:
                    from drivers import gps
                    gps.refresh_network()
                except Exception:
                    pass
                last_network_refresh = now

            # Ne pas saturer le CPU
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n[MAIN] Arrêt demandé")
    finally:
        sync_stop.set()

        # Cleanup drivers
        for mod_name in ["drivers.gps", "drivers.temperature", "drivers.gas",
                         "drivers.nfc", "drivers.buzzer", "drivers.led",
                         "drivers.buttons", "drivers.display", "core.vision"]:
            try:
                mod = sys.modules.get(mod_name)
                if mod and hasattr(mod, "cleanup"):
                    mod.cleanup()
            except Exception:
                pass

        print("[MAIN] Firmware arrêté proprement")


if __name__ == "__main__":
    main()
