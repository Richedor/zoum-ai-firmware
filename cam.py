import time
from picamera2 import Picamera2

print("Initialisation IMX219...")

picam2 = Picamera2()
print("Cameras détectées:", picam2.global_camera_info())

config = picam2.create_still_configuration(
    main={"size": (1640, 1232)}  # bon compromis qualité/perf
)
picam2.configure(config)

picam2.start()
time.sleep(2)

nom_fichier = "test_imx219.jpg"
picam2.capture_file(nom_fichier)

picam2.stop()
picam2.close()

print("OK ->", nom_fichier)
