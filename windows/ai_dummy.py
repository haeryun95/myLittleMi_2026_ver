"""
windows/ai_dummy.py - AI 키가 없을 때 사용하는 로컬 더미 응답
"""
import random
from typing import Any, Dict


DUMMY_RESPONSES = [
    ("헤헤… 뭐해?", "normal01", {"fun": 1, "mood": 1, "energy": 0, "hunger": 0}),
    ("찍찍… 심심해!", "normal02", {"fun": 2, "mood": 0, "energy": 0, "hunger": 0}),
    ("배고파… 밥 줘!", "normal03", {"fun": 0, "mood": -1, "energy": 0, "hunger": -2}),
    ("졸려… 잠깐만…", "normal01", {"fun": 0, "mood": 0, "energy": -1, "hunger": 0}),
    ("주인 좋아 💗", "normal01", {"fun": 3, "mood": 3, "energy": 0, "hunger": 0}),
]


def get_dummy_reply(last_face: str = "normal01") -> Dict[str, Any]:
    reply, face, delta = random.choice(DUMMY_RESPONSES)
    return {
        "reply": reply,
        "face": face,
        "bubble_sec": 2.2,
        "delta": delta,
        "commands": [],
    }
