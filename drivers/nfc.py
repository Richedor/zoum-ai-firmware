"""
Driver NFC PN532 — Authentification badge I2C.

Capteur : PN532 sur I2C (adresse 0x24)
Fonction : scan badges NFC/RFID, retourne UID + hash SHA-256.
"""
from __future__ import annotations
import hashlib

_pn532 = None
_initialized = False
_firmware = ""


def init() -> bool:
    global _pn532, _initialized, _firmware
    try:
        import board
        import busio
        from adafruit_pn532.i2c import PN532_I2C

        i2c = busio.I2C(board.SCL, board.SDA)
        _pn532 = PN532_I2C(i2c, debug=False)

        ic, ver, rev, support = _pn532.firmware_version
        _firmware = f"{ic}.{ver}.{rev}"

        _pn532.SAM_configuration()
        _initialized = True
        print(f"[NFC] PN532 initialisé — firmware {_firmware}")
        return True
    except Exception as e:
        print(f"[NFC] Init échoué: {e}")
        return False


def scan(timeout: float = 0.3) -> dict | None:
    """
    Scan un badge NFC. Non-bloquant (timeout court par défaut).
    Retourne dict avec uid, uid_hash, firmware ou None.
    """
    if not _initialized or _pn532 is None:
        return None

    try:
        uid = _pn532.read_passive_target(timeout=timeout)
        if uid is None:
            return None

        uid_hex = ":".join(f"{b:02X}" for b in uid)
        uid_bytes = bytes(uid)
        uid_hash = hashlib.sha256(uid_bytes).hexdigest()

        return {
            "uid": uid_hex,
            "uid_raw": uid_bytes,
            "uid_hash": uid_hash,
            "firmware": _firmware,
        }
    except Exception as e:
        print(f"[NFC] Erreur scan: {e}")
        return None


def firmware_version() -> str:
    return _firmware


def cleanup():
    global _initialized
    _initialized = False
