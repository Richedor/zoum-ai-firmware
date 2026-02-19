"""
Driver OLED SSD1306 — Affichage 128×64 I2C.

Écrans contextuels selon l'état de la machine :
  BOOT, READY, AUTH_NFC, ALCOHOL, TRIP_ACTIVE, MENU, WARNING
"""
from __future__ import annotations
import threading

_oled = None
_initialized = False
_lock = threading.Lock()

W, H = 128, 64


def init() -> bool:
    global _oled, _initialized
    try:
        import board
        import adafruit_ssd1306
        i2c = board.I2C()
        _oled = adafruit_ssd1306.SSD1306_I2C(W, H, i2c)
        _oled.fill(0)
        _oled.show()
        _initialized = True
        print(f"[OLED] SSD1306 initialisé ({W}x{H})")
        return True
    except Exception as e:
        print(f"[OLED] Init échoué: {e}")
        return False


def _draw():
    """Retourne (image, draw, font)."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("1", (W, H))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    return img, draw, font


def _show(img):
    if _oled is None:
        return
    with _lock:
        try:
            _oled.image(img)
            _oled.show()
        except Exception:
            pass


def clear():
    if _oled:
        with _lock:
            _oled.fill(0)
            _oled.show()


# ── Écrans ───────────────────────────────────────────────────────────

def screen_boot(serial: str, version: str = "1.0.0", progress: dict = None):
    img, draw, font = _draw()
    draw.text((20, 2), "ZOUM AI", font=font, fill=255)
    draw.line([(0, 14), (W, 14)], fill=255)
    draw.text((0, 18), f"Kit: {serial}", font=font, fill=255)
    draw.text((0, 30), f"Firmware v{version}", font=font, fill=255)

    if progress:
        y = 42
        icons = ""
        for name, ok in progress.items():
            tag = "+" if ok else "-"
            icons += f"{name}:{tag} "
        draw.text((0, y), icons[:21], font=font, fill=255)
        if len(icons) > 21:
            draw.text((0, y + 10), icons[21:42], font=font, fill=255)

    _show(img)


def screen_ready(driver: str = "—", gps_fix: bool = False, gps_sats: int = 0,
                 network: str = "OFFLINE", rssi: int = 0,
                 temp_c: float = None, queue_size: int = 0):
    img, draw, font = _draw()

    # Header
    draw.rectangle([(0, 0), (W, 12)], fill=255)
    draw.text((2, 1), "ZOUM AI — PRET", font=font, fill=0)

    # Driver
    draw.text((0, 16), f"Chauffeur: {driver[:14]}", font=font, fill=255)

    # GPS
    gps_txt = f"GPS:{'FIX' if gps_fix else 'NOFIX'} ({gps_sats}sat)"
    draw.text((0, 28), gps_txt, font=font, fill=255)

    # Network
    draw.text((0, 38), f"Net:{network} {rssi}dBm"[:21], font=font, fill=255)

    # Bottom : temp + queue + hint
    bottom = ""
    if temp_c is not None:
        bottom += f"{temp_c:.0f}C "
    if queue_size > 0:
        bottom += f"Q:{queue_size}"
    draw.text((0, 52), bottom, font=font, fill=255)
    draw.text((72, 52), "[>]Start", font=font, fill=255)

    _show(img)


def screen_auth_nfc(blink: bool = False):
    img, draw, font = _draw()
    draw.rectangle([(0, 0), (W, 12)], fill=255)
    draw.text((2, 1), "AUTHENTIFICATION", font=font, fill=0)

    if blink:
        draw.rectangle([(44, 20), (84, 50)], outline=255)
        draw.text((52, 32), "NFC", font=font, fill=255)
    else:
        draw.rectangle([(44, 20), (84, 50)], fill=255)
        draw.text((52, 32), "NFC", font=font, fill=0)

    draw.text((12, 54), "Presentez badge", font=font, fill=255)
    _show(img)


def screen_auth_result(success: bool, name: str = ""):
    img, draw, font = _draw()
    if success:
        draw.text((20, 10), "Badge OK", font=font, fill=255)
        draw.text((10, 30), name[:18], font=font, fill=255)
        draw.text((44, 50), "[OK]", font=font, fill=255)
    else:
        draw.text((10, 10), "Badge inconnu", font=font, fill=255)
        draw.text((30, 30), "REFUSE", font=font, fill=255)
        draw.text((15, 50), "[<] Retour", font=font, fill=255)
    _show(img)


def screen_alcohol_warmup(elapsed_s: float, total_s: float):
    img, draw, font = _draw()
    draw.rectangle([(0, 0), (W, 12)], fill=255)
    draw.text((2, 1), "ALCOOLTEST", font=font, fill=0)

    draw.text((14, 20), "Prechauffage...", font=font, fill=255)

    # Barre de progression
    pct = min(elapsed_s / max(total_s, 0.1), 1.0)
    draw.rectangle([(10, 35), (118, 45)], outline=255)
    draw.rectangle([(10, 35), (int(10 + 108 * pct), 45)], fill=255)

    remain = max(0, total_s - elapsed_s)
    draw.text((48, 50), f"{remain:.0f}s", font=font, fill=255)
    _show(img)


def screen_alcohol_blow(countdown_s: float):
    img, draw, font = _draw()
    draw.rectangle([(0, 0), (W, 12)], fill=255)
    draw.text((2, 1), "ALCOOLTEST", font=font, fill=0)

    draw.text((20, 22), "SOUFFLEZ", font=font, fill=255)
    draw.text((14, 34), "MAINTENANT", font=font, fill=255)
    draw.text((50, 50), f"{countdown_s:.0f}s", font=font, fill=255)
    _show(img)


def screen_alcohol_pass():
    img, draw, font = _draw()
    draw.text((30, 8), "RESULTAT", font=font, fill=255)
    draw.rectangle([(20, 24), (108, 42)], fill=255)
    draw.text((44, 28), "PASS", font=font, fill=0)
    draw.text((16, 50), "[>] Demarrer", font=font, fill=255)
    _show(img)


def screen_alcohol_fail():
    img, draw, font = _draw()
    draw.rectangle([(0, 0), (W, H)], fill=255)
    draw.text((10, 5), "!! ATTENTION !!", font=font, fill=0)
    draw.text((5, 22), "Ne conduisez pas", font=font, fill=0)
    draw.text((15, 38), "Alcool detecte", font=font, fill=0)
    draw.text((2, 52), "[>]Refaire [<]Quit", font=font, fill=0)
    _show(img)


def screen_trip(speed_kmh: float = 0, gps_fix: bool = False,
                network: str = "—", queue_size: int = 0,
                fatigue_level: int = 0, elapsed_min: float = 0):
    img, draw, font = _draw()

    # Header
    draw.rectangle([(0, 0), (W, 12)], fill=255)
    draw.text((2, 1), "TRIP", font=font, fill=0)
    draw.ellipse([(38, 3), (44, 9)], fill=0)
    draw.text((50, 1), f"{elapsed_min:.0f}min", font=font, fill=0)

    # Vitesse
    draw.text((4, 16), f"{speed_kmh:.0f}", font=font, fill=255)
    draw.text((40, 18), "km/h", font=font, fill=255)

    # Fatigue
    fat_labels = {0: "OK", 1: "ATTENTION", 2: "ALERTE!"}
    draw.text((0, 30), f"Fatigue: {fat_labels.get(fatigue_level, '—')}", font=font, fill=255)

    # GPS + Net + Queue
    gps_ico = "FIX" if gps_fix else "---"
    q_txt = f"Q:{queue_size}" if queue_size > 0 else ""
    draw.text((0, 42), f"GPS:{gps_ico} {network} {q_txt}", font=font, fill=255)

    draw.text((72, 52), "[S]Stop", font=font, fill=255)
    _show(img)


def screen_stop_confirm():
    img, draw, font = _draw()
    draw.text((8, 10), "Terminer trajet ?", font=font, fill=255)
    draw.rectangle([(10, 30), (55, 48)], outline=255)
    draw.text((16, 34), "[>]Oui", font=font, fill=255)
    draw.rectangle([(65, 30), (115, 48)], outline=255)
    draw.text((72, 34), "[<]Non", font=font, fill=255)
    _show(img)


def screen_warning_lock(message: str = "Ne conduisez pas"):
    img, draw, font = _draw()
    draw.rectangle([(0, 0), (W, H)], fill=255)
    draw.text((5, 8), "!! ALERTE !!", font=font, fill=0)
    if len(message) > 20:
        draw.text((2, 28), message[:20], font=font, fill=0)
        draw.text((2, 40), message[20:40], font=font, fill=0)
    else:
        draw.text((2, 30), message, font=font, fill=0)
    draw.text((2, 52), "[>]Refaire [<]Quit", font=font, fill=0)
    _show(img)


def screen_menu(page: int = 0, data: dict = None):
    img, draw, font = _draw()
    data = data or {}

    draw.rectangle([(0, 0), (W, 12)], fill=255)
    draw.text((2, 1), f"MENU ({page + 1}/4)", font=font, fill=0)

    if page == 0:  # Capteurs
        draw.text((0, 16), "-- Capteurs --", font=font, fill=255)
        sensors = data.get("sensors", {})
        y = 28
        for name, ok in sensors.items():
            if y > 54:
                break
            draw.text((0, y), f"  {name}: {'OK' if ok else 'KO'}", font=font, fill=255)
            y += 10

    elif page == 1:  # Sync
        draw.text((0, 16), "-- Sync --", font=font, fill=255)
        draw.text((0, 28), f"Queue: {data.get('queue_size', 0)}", font=font, fill=255)
        draw.text((0, 38), f"Last: {data.get('last_sync', '—')}", font=font, fill=255)
        draw.text((0, 48), f"Fails: {data.get('sync_fails', 0)}", font=font, fill=255)

    elif page == 2:  # GPS
        draw.text((0, 16), "-- GPS --", font=font, fill=255)
        draw.text((0, 28), f"Fix: {data.get('gps_fix', False)}", font=font, fill=255)
        draw.text((0, 38), f"Sats: {data.get('gps_sats', 0)}", font=font, fill=255)
        draw.text((0, 48), f"Lat: {data.get('lat', 0):.4f}", font=font, fill=255)

    elif page == 3:  # Info
        draw.text((0, 16), "-- Info --", font=font, fill=255)
        draw.text((0, 28), f"Kit: {data.get('serial', '—')}", font=font, fill=255)
        draw.text((0, 38), f"FW: {data.get('version', '—')}", font=font, fill=255)
        draw.text((0, 48), f"Up: {data.get('uptime', '—')}", font=font, fill=255)

    draw.text((0, 54), "[M]Next [<]Exit", font=font, fill=255)
    _show(img)


def cleanup():
    clear()
