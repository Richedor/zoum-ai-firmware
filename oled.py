import time
import board
import adafruit_dht
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont
import RPi.GPIO as GPIO
from picamera2 import Picamera2

# --- CONFIGURATION ---
GAS_PIN = 17    # Pin DO du MQ-9 branché sur GPIO 17
DHT_PIN = board.D4  # Pin DATA du DHT22 branché sur GPIO 4

# Initialisation OLED
i2c = board.I2C()
oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)

# Initialisation Capteurs
dht_device = adafruit_dht.DHT22(DHT_PIN)
GPIO.setmode(GPIO.BCM)
GPIO.setup(GAS_PIN, GPIO.IN)

# Initialisation Caméra
picam2 = Picamera2()
picam2.start()

print("Système de surveillance démarré...")

def draw_screen(temp, hum, status):
    # Créer une image vide (fond noir)
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    
    # Dessiner les infos
    draw.text((0, 0),  f"TEMP: {temp:.1f}C", font=font, fill=255)
    draw.text((0, 20), f"HUMID: {hum}%", font=font, fill=255)
    draw.text((0, 45), f"GAZ: {status}", font=font, fill=255)
    
    oled.image(image)
    oled.show()

try:
    while True:
        try:
            # Lectures
            temperature = dht_device.temperature
            humidity = dht_device.humidity
            
            # Détection Gaz (MQ-9 envoie LOW si détection)
            gas_detected = GPIO.input(GAS_PIN) == GPIO.LOW
            gas_status = "ALERTE !!!" if gas_detected else "NORMAL"
            
            # Mise à jour de l'écran
            draw_screen(temperature, humidity, gas_status)

            # Si alerte gaz : Prendre une photo
            if gas_detected:
                ts = time.strftime("%Y%m%d-%H%M%S")
                picam2.capture_file(f"alerte_{ts}.jpg")
                print(f"Gaz détecté ! Photo enregistrée : alerte_{ts}.jpg")
                time.sleep(5) # Pause pour éviter de prendre trop de photos

        except RuntimeError:
            # Erreurs de lecture DHT22 fréquentes, on ignore
            pass
            
        time.sleep(2)

except KeyboardInterrupt:
    print("Arrêt du système...")
    picam2.stop()
    GPIO.cleanup()