import time
import board
import adafruit_dht

# Initialise le capteur sur le GPIO 4
dhtDevice = adafruit_dht.DHT22(board.D4)

while True:
    try:
        # Lecture des valeurs
        temperature_c = dhtDevice.temperature
        humidity = dhtDevice.humidity

        print("Temp: {:.1f} °C    Humidité: {}%".format(temperature_c, humidity))

    except RuntimeError as error:
        # Les erreurs de lecture sont fréquentes avec les DHT, on continue
        print(error.args[0])
        time.sleep(2.0)
        continue
    except Exception as error:
        dhtDevice.exit()
        raise error

    time.sleep(2.0)