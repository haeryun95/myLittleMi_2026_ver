from dataclasses import dataclass, asdict
from typing import Dict, Any, List


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


@dataclass
class PetState:
    hunger: float = 60.0
    energy: float = 70.0
    mood: float = 70.0
    joy: float = 20.0
    last_face: str = "normal01"

    def apply_delta(self, delta: Dict[str, float]):
        self.joy += float(delta.get("joy", 0))
        self.mood += float(delta.get("mood", 0))
        self.energy += float(delta.get("energy", 0))
        self.hunger += float(delta.get("hunger", 0))
        self.clamp_all()

    def clamp_all(self):
        self.hunger = clamp(self.hunger, 0, 100)
        self.energy = clamp(self.energy, 0, 100)
        self.mood = clamp(self.mood, 0, 100)
        self.joy = clamp(self.joy, 0, 100)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# AI에게 보내는 이벤트 payload 예시:
# { "event": {"type": "CHAT", "text": "...", "source":"chat"}, "state": {...} }