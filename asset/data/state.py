from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Set

@dataclass
class PetState:
    user_name: str = "나"
    pet_name: str = "라이미"

    # needs
    hunger: float = 50.0
    energy: float = 50.0
    max_energy: float = 50.0
    mood: float = 50.0
    fun: float = 50.0

    # economy
    money: int = 0
    inventory: Dict[str, int] = field(default_factory=dict)

    # background / furniture
    # owned_bg[category] = set(item_id)
    owned_bg: Dict[str, Set[str]] = field(default_factory=dict)

    # currently selected placements etc (너 프로젝트에 맞춰 추가)
    placed_bg: Dict[str, str] = field(default_factory=dict)  # 예: {"wallpaper":"pink01", ...}

    last_face: str = "normal01"

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "user_name": self.user_name,
            "pet_name": self.pet_name,
            "hunger": float(self.hunger),
            "energy": float(self.energy),
            "max_energy": float(self.max_energy),
            "mood": float(self.mood),
            "fun": float(self.fun),
            "money": int(self.money),
            "inventory": {k: int(v) for k, v in (self.inventory or {}).items()},
            "owned_bg": {cat: sorted(list(s)) for cat, s in (self.owned_bg or {}).items()},
            "placed_bg": dict(self.placed_bg or {}),
            "last_face": str(self.last_face),
        }
        return d

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "PetState":
        st = cls()
        if not isinstance(raw, dict):
            return st

        st.user_name = str(raw.get("user_name", st.user_name))
        st.pet_name = str(raw.get("pet_name", st.pet_name))

        st.hunger = float(raw.get("hunger", st.hunger))
        st.energy = float(raw.get("energy", st.energy))
        st.max_energy = float(raw.get("max_energy", st.max_energy))
        st.mood = float(raw.get("mood", st.mood))
        st.fun = float(raw.get("fun", st.fun))

        st.money = int(raw.get("money", st.money))

        inv = raw.get("inventory", {})
        if isinstance(inv, dict):
            st.inventory = {str(k): max(0, int(v)) for k, v in inv.items()}
        else:
            st.inventory = {}

        ob = raw.get("owned_bg", {})
        st.owned_bg = {}
        if isinstance(ob, dict):
            for cat, arr in ob.items():
                if isinstance(arr, list):
                    st.owned_bg[str(cat)] = set(str(x) for x in arr)
                elif isinstance(arr, set):
                    st.owned_bg[str(cat)] = set(str(x) for x in arr)
                else:
                    st.owned_bg[str(cat)] = set()

        pb = raw.get("placed_bg", {})
        st.placed_bg = dict(pb) if isinstance(pb, dict) else {}

        st.last_face = str(raw.get("last_face", st.last_face))
        return st