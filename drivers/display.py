"""
Driver OLED SSD1306 - Affichage 128x64 I2C.

Écrans contextuels selon l'état de la machine :
  BOOT, READY, AUTH_NFC, ALCOHOL, TRIP_ACTIVE, MENU, WARNING
"""
from __future__ import annotations
import threading

_oled = None
_initialized = False
_lock = threading.Lock()

W, H = 128, 64

def safe_text(txt):
    return str(txt).replace("—", "-").encode("ascii", errors="replace").decode()

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
    draw.text((20, 2), safe_text("ZOUM AI"), font=font, fill=255)
    draw.line([(0, 14), (W, 14)], fill=255)
    draw.text((0, 18), safe_text(f"Kit: {serial}"), font=font, fill=255)
    draw.text((0, 30), safe_text(f"Firmware v{version}"), font=font, fill=255)
    if progress:
        y = 42
        icons = ""
        for name, ok in progress.items():
            tag = "+" if ok else "-"
            icons += f"{name}:{tag} "
        draw.text((0, y), safe_text(icons[:21]), font=font, fill=255)
        if len(icons) > 21:
            draw.text((0, y + 10), safe_text(icons[21:42]), font=font, fill=255)
    _show(img)

def screen_ready(driver: str = "-", gps_fix: bool = False, gps_sats: int = 0,
                 network: str = "OFFLINE", rssi: int = 0,
                 temp_c: float = None, queue_size: int = 0):
    img, draw, font = _draw()
    driver = safe_text(driver)
    draw.rectangle([(0, 0), (W, 12)], fill=255)
    draw.text((2, 1), safe_text("ZOUM AI - PRET"), font=font, fill=0)
    draw.text((0, 16), safe_text(f"Chauffeur: {driver[:14]}"), font=font, fill=255)
    gps_txt = safe_text(f"GPS:{'FIX' if gps_fix else 'NOFIX'} ({gps_sats}sat)")
    draw.text((0, 28), gps_txt, font=font, fill=255)
    draw.text((0, 38), safe_text(f"Net:{network} {rssi}dBm"[:21]), font=font, fill=255)
    bottom = ""
    if temp_c is not None:
        bottom += f"{temp_c:.0f}C "
    if queue_size > 0:
        bottom += f"Q:{queue_size}"
    draw.text((0, 52), safe_text(bottom), font=font, fill=255)
    draw.text((72, 52), safe_text("[>]Start"), font=font, fill=255)
    _show(img)

def screen_auth_nfc(blink: bool = False):
    img, draw, font = _draw()
    draw.rectangle([(0, 0), (W, 12)], fill=255)
    draw.text((2, 1), safe_text("AUTHENTIFICATION"), font=font, fill=0)
    if blink:
        draw.rectangle([(44, 20), (84, 50)], outline=255)
        draw.text((52, 32), safe_text("NFC"), font=font, fill=255)
    else:
        draw.rectangle([(44, 20), (84, 50)], fill=255)
        draw.text((52, 32), safe_text("NFC"), font=font, fill=0)
    draw.text((12, 54), safe_text("Presentez badge"), font=font, fill=255)
    _show(img)

def screen_auth_result(success: bool, name: str = ""):
    img, draw, font = _draw()
    if success:
        draw.text((20, 10), safe_text("Badge OK"), font=font, fill=255)
        draw.text((10, 30), safe_text(name[:18]), font=font, fill=255)
        draw.text((44, 50), safe_text("[OK]"), font=font, fill=255)
    else:
        draw.text((10, 10), safe_text("Badge inconnu"), font=font, fill=255)
        draw.text((30, 30), safe_text("REFUSE"), font=font, fill=255)
        draw.text((15, 50), safe_text("[<] Retour"), font=font, fill=255)
    _show(img)

def screen_alcohol_warmup(elapsed_s: float, total_s: float):
    img, draw, font = _draw()
    draw.rectangle([(0, 0), (W, 12)], fill=255)
    draw.text((2, 1), safe_text("ALCOOLTEST"), font=font, fill=0)
    draw.text((14, 20), safe_text("Prechauffage..."), font=font, fill=255)
    pct = min(elapsed_s / max(total_s, 0.1), 1.0)
    draw.rectangle([(10, 35), (118, 45)], outline=255)
    draw.rectangle([(10, 35), (int(10 + 108 * pct), 45)], fill=255)
    remain = max(0, total_s - elapsed_s)
    draw.text((48, 50), safe_text(f"{remain:.0f}s"), font=font, fill=255)
    _show(img)

def screen_alcohol_blow(countdown_s: float):
    img, draw, font = _draw()
    draw.rectangle([(0, 0), (W, 12)], fill=255)
    draw.text((2, 1), safe_text("ALCOOLTEST"), font=font, fill=0)
    draw.text((20, 22), safe_text("SOUFFLEZ"), font=font, fill=255)
    draw.text((14, 34), safe_text("MAINTENANT"), font=font, fill=255)
    draw.text((50, 50), safe_text(f"{countdown_s:.0f}s"), font=font, fill=255)
    _show(img)

def screen_alcohol_pass():
    img, draw, font = _draw()
    draw.text((30, 8), safe_text("RESULTAT"), font=font, fill=255)
    draw.rectangle([(20, 24), (108, 42)], fill=255)
    draw.text((44, 28), safe_text("PASS"), font=font, fill=0)
    draw.text((16, 50), safe_text("[>] Demarrer"), font=font, fill=255)
    _show(img)

def screen_alcohol_fail():
    img, draw, font = _draw()
    draw.rectangle([(0, 0), (W, H)], fill=255)
    draw.text((10, 5), safe_text("!! ATTENTION !!"), font=font, fill=0)
    draw.text((5, 22), safe_text("Ne conduisez pas"), font=font, fill=0)
    draw.text((15, 38), safe_text("Alcool detecte"), font=font, fill=0)
    draw.text((2, 52), safe_text("[>]Refaire [<]Quit"), font=font, fill=0)
    _show(img)

def screen_trip(speed_kmh: float = 0, gps_fix: bool = False,
                network: str = "-", queue_size: int = 0,
                fatigue_level: int = 0, elapsed_min: float = 0):
    img, draw, font = _draw()
    draw.rectangle([(0, 0), (W, 12)], fill=255)
    draw.text((2, 1), safe_text("TRIP"), font=font, fill=0)
    draw.ellipse([(38, 3), (44, 9)], fill=0)
    draw.text((50, 1), safe_text(f"{elapsed_min:.0f}min"), font=font, fill=0)
    draw.text((4, 16), safe_text(f"{speed_kmh:.0f}"), font=font, fill=255)
    draw.text((40, 18), safe_text("km/h"), font=font, fill=255)
    fat_labels = {0: "OK", 1: "ATTENTION", 2: "ALERTE!"}
    draw.text((0, 30), safe_text(f"Fatigue: {fat_labels.get(fatigue_level, '-')}"), font=font, fill=255)
    gps_ico = "FIX" if gps_fix else "---"
    q_txt = f"Q:{queue_size}" if queue_size > 0 else ""
    draw.text((0, 42), safe_text(f"GPS:{gps_ico} {network} {q_txt}"), font=font, fill=255)
    draw.text((72, 52), safe_text("[S]Stop"), font=font, fill=255)
    _show(img)

def screen_stop_confirm():
    img, draw, font = _draw()
    draw.text((8, 10), safe_text("Terminer trajet ?"), font=font, fill=255)
    draw.rectangle([(10, 30), (55, 48)], outline=255)
    draw.text((16, 34), safe_text("[>]Oui"), font=font, fill=255)
    draw.rectangle([(65, 30), (115, 48)], outline=255)
    draw.text((72, 34), safe_text("[<]Non"), font=font, fill=255)
    _show(img)

def screen_warning_lock(message: str = "Ne conduisez pas"):
    img, draw, font = _draw()
    draw.rectangle([(0, 0), (W, H)], fill=255)
    draw.text((5, 8), safe_text("!! ALERTE !!"), font=font, fill=0)
    if len(message) > 20:
        draw.text((2, 28), safe_text(message[:20]), font=font, fill=0)
        draw.text((2, 40), safe_text(message[20:40]), font=font, fill=0)
    else:
        draw.text((2, 30), safe_text(message), font=font, fill=0)
    draw.text((2, 52), safe_text("[>]Refaire [<]Quit"), font=font, fill=0)
    _show(img)

def screen_menu(page: int = 0, data: dict = None):
    img, draw, font = _draw()
    data = data or {}
    draw.rectangle([(0, 0), (W, 12)], fill=255)
    draw.text((2, 1), safe_text(f"MENU ({page + 1}/4)"), font=font, fill=0)
    if page == 0:  # Capteurs
        draw.text((0, 16), safe_text("-- Capteurs --"), font=font, fill=255)
        sensors = data.get("sensors", {})
        y = 28
        for name, ok in sensors.items():
            if y > 54:
                break
            draw.text((0, y), safe_text(f"  {name}: {'OK' if ok else 'KO'}"), font=font, fill=255)
            y += 10
    elif page == 1:  # Sync
        draw.text((0, 16), safe_text("-- Sync --"), font=font, fill=255)
        draw.text((0, 28), safe_text(f"Queue: {data.get('queue_size', 0)}"), font=font, fill=255)
        draw.text((0, 38), safe_text(f"Last: {data.get('last_sync', '-')}"), font=font, fill=255)
        draw.text((0, 48), safe_text(f"Fails: {data.get('sync_fails', 0)}"), font=font, fill=255)
    elif page == 2:  # GPS
        draw.text((0, 16), safe_text("-- GPS --"), font=font, fill=255)
        draw.text((0, 28), safe_text(f"Fix: {data.get('gps_fix', False)}"), font=font, fill=255)
        draw.text((0, 38), safe_text(f"Sats: {data.get('gps_sats', 0)}"), font=font, fill=255)
        draw.text((0, 48), safe_text(f"Lat: {data.get('lat', 0):.4f}"), font=font, fill=255)
    elif page == 3:  # Info
        draw.text((0, 16), safe_text("-- Info --"), font=font, fill=255)
        draw.text((0, 28), safe_text(f"Kit: {data.get('serial', '-')}"), font=font, fill=255)
        draw.text((0, 38), safe_text(f"FW: {data.get('version', '-')}"), font=font, fill=255)
        draw.text((0, 48), safe_text(f"Up: {data.get('uptime', '-')}"), font=font, fill=255)
    draw.text((0, 54), safe_text("[M]Next [<]Exit"), font=font, fill=255)
    _show(img)

def cleanup():
    clear()