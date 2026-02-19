import RPi.GPIO as GPIO
import time
from datetime import datetime

# Configuration
GAS_PIN = 4
GPIO.setmode(GPIO.BCM)
GPIO.setup(GAS_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print("=== Moniteur de Gaz Multi-Cibles MQ-9 ===")
print("Gaz détectables : Alcool, CO, CH4, GPL")
print("Appuyez sur Ctrl+C pour arrêter\n")

try:
    while True:
        # Lecture du capteur (0 = Détection, 1 = Normal sur la plupart des modules)
        gas_present = GPIO.input(GAS_PIN) 
        
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        if gas_present:
            print(f"[{timestamp}] !!! ALERTE : Anomalie détectée !!!")
            print("Action : Vérifiez l'air (Alcool, fumée ou fuite de gaz possible)")
        else:
            print(f"[{timestamp}] Statut : Air normal")
            
        time.sleep(2) # On vérifie toutes les 2 secondes

except KeyboardInterrupt:
    print("\nFermeture du moniteur...")
    GPIO.cleanup()