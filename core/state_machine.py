"""
Machine d'état — Gestion du flux conducteur.

États :
  BOOT → READY → AUTH_NFC → ALCOHOL_CHECK → TRIP_ACTIVE
  TRIP_ACTIVE → TRIP_STOP_CONFIRM → READY
  * → MENU → retour
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Optional

# ── États ────────────────────────────────────────────────────────────
BOOT              = "BOOT"
READY             = "READY"
AUTH_NFC           = "AUTH_NFC"
ALCOHOL_CHECK      = "ALCOHOL_CHECK"
TRIP_ACTIVE        = "TRIP_ACTIVE"
TRIP_STOP_CONFIRM  = "TRIP_STOP_CONFIRM"
WARNING_LOCK       = "WARNING_LOCK"
MENU               = "MENU"

# ── Sous-états alcool ────────────────────────────────────────────────
ALC_WARMUP = "warmup"
ALC_BLOW   = "blow"
ALC_PASS   = "pass"
ALC_FAIL   = "fail"


@dataclass
class State:
    """État courant de la machine."""
    current: str = BOOT
    previous: str = BOOT
    driver_id: Optional[str] = None
    driver_name: str = "—"
    badge_uid: Optional[str] = None
    trip_id: Optional[str] = None
    trip_start_time: Optional[float] = None
    alcohol_phase: str = ALC_WARMUP
    alcohol_start: float = 0.0
    alcohol_result: Optional[str] = None   # "pass" / "fail"
    menu_page: int = 0
    changed_at: float = field(default_factory=time.time)

    def transition(self, new_state: str):
        """Change d'état et enregistre le timestamp."""
        if new_state == self.current:
            return
        self.previous = self.current
        self.current = new_state
        self.changed_at = time.time()
        print(f"[STATE] {self.previous} → {self.current}")

    @property
    def time_in_state(self) -> float:
        """Secondes dans l'état courant."""
        return time.time() - self.changed_at

    @property
    def is_trip(self) -> bool:
        return self.current == TRIP_ACTIVE

    def reset_auth(self):
        self.driver_id = None
        self.driver_name = "—"
        self.badge_uid = None

    def reset_trip(self):
        self.trip_id = None
        self.trip_start_time = None

    def reset_alcohol(self):
        self.alcohol_phase = ALC_WARMUP
        self.alcohol_start = 0.0
        self.alcohol_result = None
