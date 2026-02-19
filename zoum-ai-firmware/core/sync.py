"""
Sync — Client API multi-endpoint avec retry.

Endpoints :
  telemetry  → POST /v1/ingest/telemetry
  nfc_auth   → POST /v1/ingest/nfc_auth
  alcohol    → POST /v1/ingest/alcohol_test
  alert      → POST /v1/ingest/alert
  trip_open  → POST /v1/trips/open
  trip_close → POST /v1/trips/close
  health     → POST /v1/device/health
"""
from __future__ import annotations
import requests
import time

ENDPOINT_PATHS = {
    "telemetry":  "/v1/ingest/telemetry",
    "nfc_auth":   "/v1/ingest/nfc_auth",
    "alcohol":    "/v1/ingest/alcohol_test",
    "alert":      "/v1/ingest/alert",
    "trip_open":  "/v1/trips/open",
    "trip_close": "/v1/trips/close",
    "health":     "/v1/device/health",
}


class ApiClient:
    def __init__(self, api_base_url: str, kit_serial: str, kit_key: str):
        self.api_base_url = api_base_url.rstrip("/")
        self.headers = {
            "X-Kit-Serial": kit_serial,
            "X-Kit-Key": kit_key,
            "Content-Type": "application/json",
        }
        self.last_ok_time = 0.0
        self.consecutive_fails = 0

    def post(self, endpoint: str, payload: dict) -> tuple[bool, str]:
        """Envoie un payload. Retourne (success, message)."""
        path = ENDPOINT_PATHS.get(endpoint)
        if path is None:
            return False, f"Endpoint inconnu: {endpoint}"

        url = f"{self.api_base_url}{path}"
        try:
            r = requests.post(url, json=payload, headers=self.headers, timeout=10)
            if 200 <= r.status_code < 300:
                self.last_ok_time = time.time()
                self.consecutive_fails = 0
                return True, r.text
            self.consecutive_fails += 1
            return False, f"{r.status_code} {r.text[:200]}"
        except requests.ConnectionError:
            self.consecutive_fails += 1
            return False, "Connection refused"
        except requests.Timeout:
            self.consecutive_fails += 1
            return False, "Timeout"
        except Exception as e:
            self.consecutive_fails += 1
            return False, repr(e)

    # Raccourcis
    def post_telemetry(self, payload):
        return self.post("telemetry", payload)

    def post_nfc_auth(self, payload):
        return self.post("nfc_auth", payload)

    def post_alcohol(self, payload):
        return self.post("alcohol", payload)

    def post_alert(self, payload):
        return self.post("alert", payload)

    def post_trip_open(self, payload):
        return self.post("trip_open", payload)

    def post_trip_close(self, payload):
        return self.post("trip_close", payload)

    @property
    def is_online(self) -> bool:
        return self.consecutive_fails < 3

    @property
    def seconds_since_sync(self) -> float:
        if self.last_ok_time == 0:
            return float("inf")
        return time.time() - self.last_ok_time
