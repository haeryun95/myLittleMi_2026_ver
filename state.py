"""
state.py - PetState 클래스 (펫 상태 관리)
"""
from typing import Dict, List, Optional, Set, Tuple

from config import BG_CATEGORIES


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


class PetState:
    """
    mood 유지 + fun 분리
    energy/max_energy (stamina 역할)
    JobWindow 기대(stats/inventory)도 state가 기본 보유
    """
    MOOD_BANDS: List[Tuple[int, str]] = [
        (15, "절망"),
        (30, "우울"),
        (45, "슬픔"),
        (55, "무덤덤"),
        (70, "기분좋음"),
        (85, "행복"),
        (101, "기쁨"),
    ]

    def __init__(self):
        self.pet_name = "라이미"

        self.energy = 100.0
        self.max_energy = 150.0

        self.hunger = 60.0
        self.fun = 70.0
        self.mood = 70.0

        self.stats: Dict[str, int] = {
            "power": 0,
            "cute": 5,
            "interest": 0,
        }
        self.inventory: Dict[str, int] = {}

        self.money = 0
        self.last_face = "normal01"

        self.owned_bg: Dict[str, Set[str]] = {cat: set() for cat in BG_CATEGORIES}
        self.selected_bg: Dict[str, Optional[str]] = {cat: None for cat in BG_CATEGORIES}

    @property
    def mood_label(self) -> str:
        v = int(round(clamp(self.mood)))
        for limit, name in self.MOOD_BANDS:
            if v < limit:
                return name
        return self.MOOD_BANDS[-1][1]

    def update_mood_from_needs(self, dt_sec: float = 1.0) -> None:
        fun_n = clamp(self.fun) / 100.0
        energy_n = clamp(self.energy, 0.0, self.max_energy) / float(self.max_energy)
        hunger_n = clamp(self.hunger) / 100.0
        hunger_good = hunger_n

        base = 50.0
        target = (
            base
            + (fun_n - 0.5) * 70.0
            + (energy_n - 0.5) * 50.0
            + (hunger_good - 0.5) * 30.0
        )
        target = clamp(target)

        follow_speed_per_sec = 6.0
        max_step = follow_speed_per_sec * max(0.0, dt_sec)
        diff = target - self.mood
        step = clamp(diff, -max_step, max_step)
        self.mood = clamp(self.mood + step)

    def add_fun(self, amount: float) -> None:
        self.fun = clamp(self.fun + amount)
        self.update_mood_from_needs(dt_sec=0.5)

    def add_energy(self, amount: float) -> None:
        self.energy = clamp(self.energy + amount, 0.0, self.max_energy)
        self.update_mood_from_needs(dt_sec=0.5)

    def apply_delta(self, delta: dict) -> None:
        """AI 결과 delta를 상태에 반영"""
        for k, v in (delta or {}).items():
            k2 = "energy" if k == "stamina" else k
            if k2 == "energy":
                self.energy = clamp(self.energy + float(v), 0.0, self.max_energy)
            elif k2 == "max_energy":
                self.max_energy = max(50.0, self.max_energy + float(v))
            elif k2 == "mood":
                self.mood = clamp(self.mood + float(v))
            elif k2 == "hunger":
                self.hunger = clamp(self.hunger + float(v))
            elif k2 == "fun":
                self.fun = clamp(self.fun + float(v))

    def clamp_all(self) -> None:
        self.energy = clamp(self.energy, 0.0, self.max_energy)
        self.hunger = clamp(self.hunger)
        self.fun = clamp(self.fun)
        self.mood = clamp(self.mood)

        if not isinstance(self.stats, dict):
            self.stats = {"power": 0, "cute": 5, "interest": 0}
        for k in ("power", "cute", "interest"):
            self.stats[k] = int(self.stats.get(k, 0))

        if not isinstance(self.inventory, dict):
            self.inventory = {}
        for k in list(self.inventory.keys()):
            self.inventory[k] = max(0, int(self.inventory[k]))
