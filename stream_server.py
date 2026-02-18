"""
stream_server.py — Serveur MJPEG léger pour visualisation distante.

Lance un serveur HTTP qui diffuse les frames annotées en MJPEG.
Accessible depuis un navigateur :  http://<ip-du-pi>:8080

Aucune dépendance externe (stdlib Python uniquement).
Thread séparé pour ne pas bloquer le pipeline principal.
"""
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import cv2

# Frame partagée entre le pipeline et le serveur
_lock = threading.Lock()
_current_frame = None  # JPEG bytes
_running = False


def update_frame(bgr_frame, quality=50):
    """Appelé par le pipeline pour mettre à jour la frame diffusée."""
    global _current_frame
    if bgr_frame is None:
        return
    ret, jpeg = cv2.imencode(".jpg", bgr_frame,
                             [cv2.IMWRITE_JPEG_QUALITY, quality])
    if ret:
        with _lock:
            _current_frame = jpeg.tobytes()


class _MJPEGHandler(BaseHTTPRequestHandler):
    """Gère les requêtes HTTP — renvoie un flux MJPEG ou une page HTML."""

    def do_GET(self):
        if self.path == "/stream":
            self._stream()
        else:
            self._index()

    def _index(self):
        """Page HTML minimale avec le flux vidéo."""
        html = (
            '<!DOCTYPE html><html><head>'
            '<title>Fatigue Detection — Live</title>'
            '<style>body{background:#111;margin:0;display:flex;'
            'justify-content:center;align-items:center;height:100vh}'
            'img{max-width:100%;max-height:100vh}</style></head>'
            '<body><img src="/stream"></body></html>'
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def _stream(self):
        """Flux MJPEG continu."""
        self.send_response(200)
        self.send_header("Content-Type",
                         "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        try:
            while _running:
                with _lock:
                    frame_data = _current_frame
                if frame_data is None:
                    time.sleep(0.1)
                    continue
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(frame_data)}\r\n".encode())
                self.wfile.write(b"\r\n")
                self.wfile.write(frame_data)
                self.wfile.write(b"\r\n")
                # ~10 FPS max pour le stream (économise bande passante)
                time.sleep(0.1)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *args):
        """Supprimer les logs HTTP pour ne pas polluer la console."""
        pass


def start(port=8080):
    """Démarre le serveur MJPEG en arrière-plan."""
    global _running
    _running = True
    server = HTTPServer(("0.0.0.0", port), _MJPEGHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[STREAM] Serveur MJPEG démarré → http://0.0.0.0:{port}")
    return server


def stop(server):
    """Arrête le serveur."""
    global _running
    _running = False
    if server:
        server.shutdown()
