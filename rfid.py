import time
import board
import busio
from adafruit_pn532.i2c import PN532_I2C

def format_uid(uid: bytes) -> str:
    return ":".join(f"{b:02X}" for b in uid)

def main():
    # I2C du Raspberry Pi (GPIO2 SDA, GPIO3 SCL)
    i2c = busio.I2C(board.SCL, board.SDA)

    # La plupart des PN532 I2C sont à 0x24
    pn532 = PN532_I2C(i2c, debug=False)

    ic, ver, rev, support = pn532.firmware_version
    print(f"PN532 firmware: {ic}.{ver}.{rev}  support=0x{support:02X}")

    # Configure en mode lecteur RFID/NFC
    pn532.SAM_configuration()
    print("Prêt. Approche une carte/badge... (Ctrl+C pour quitter)")

    last_uid = None
    last_time = 0.0
    debounce_s = 1.0  # évite de spammer si la carte reste posée

    while True:
        uid = pn532.read_passive_target(timeout=0.2)
        if uid is not None:
            now = time.time()
            if uid != last_uid or (now - last_time) > debounce_s:
                print("UID:", format_uid(uid), " (len=", len(uid), ")")
                last_uid = uid
                last_time = now
        time.sleep(0.05)

if __name__ == "__main__":
    main()
