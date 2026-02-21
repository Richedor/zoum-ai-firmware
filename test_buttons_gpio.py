import RPi.GPIO as GPIO
import time

# Liste des GPIO à tester (modifie selon tes besoins)
PINS = [5, 6, 13, 19]

GPIO.setmode(GPIO.BCM)
for pin in PINS:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    try:
        GPIO.add_event_detect(pin, GPIO.FALLING, bouncetime=200)
        print(f"[OK] Edge detection activée sur GPIO {pin}")
    except Exception as e:
        print(f"[ERREUR] Impossible d'activer edge detection sur GPIO {pin}: {e}")

print("Appuie sur les boutons (Ctrl+C pour quitter)...")
try:
    while True:
        for pin in PINS:
            if GPIO.event_detected(pin):
                print(f"[EVENT] Appui détecté sur GPIO {pin}")
        time.sleep(0.05)
except KeyboardInterrupt:
    print("\nTest terminé.")
finally:
    GPIO.cleanup()
    print("GPIO nettoyés.")
