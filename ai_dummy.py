import random
from typing import Dict, Any

# ✅ 내가 가진 emotion 프레임(파일명 stem)과 맞춰줘야 함
# 지금은 예시로 normal01~03만 사용 (내 폴더에 맞춰 늘려도 됨)
FACES = ["normal01", "normal02", "normal03"]

AUTO_LINES = [
    ("찍찍! 혼자 달리는 중!", "normal01", [{"type": "SET_MODE", "mode": "walk", "sec": 1.4}]),
    ("음… 졸려서 꾸벅…", "normal02", [{"type": "SET_MODE", "mode": "sleep", "sec": 2.8}]),
    ("점프! 점프!", "normal01", [{"type": "JUMP", "strength": 12}]),
    ("부르르…", "normal03", [{"type": "SHAKE", "sec": 0.6, "strength": 3}]),
]

def dummy_ai(payload: Dict[str, Any]) -> Dict[str, Any]:
    event = payload.get("event", {})
    etype = event.get("type", "CHAT")
    text = event.get("text", "")
    state = payload.get("state", {})

    hunger = float(state.get("hunger", 50))
    energy = float(state.get("energy", 50))

    # ✅ 기본 응답 틀
    result = {
        "reply": "",
        "face": random.choice(FACES),
        "bubble_sec": 2.2,
        "delta": {"joy": 0, "mood": 0, "energy": 0, "hunger": 0},
        "commands": []
    }

    if etype == "AUTO":
        # 상태 기반 가중치 느낌
        if energy < 25:
            result["reply"] = "찍… 너무 졸려… 자야 해…"
            result["face"] = "normal02"
            result["delta"] = {"joy": 1, "mood": 0, "energy": +3, "hunger": -1}
            result["commands"] = [{"type": "SET_MODE", "mode": "sleep", "sec": 3.5}]
            return result

        if hunger < 20:
            result["reply"] = "배고파… 밥…"
            result["face"] = "normal03"
            result["delta"] = {"joy": 1, "mood": -1, "energy": 0, "hunger": -1}
            return result

        line, face, cmds = random.choice(AUTO_LINES)
        result["reply"] = line
        result["face"] = face
        result["delta"] = {"joy": 2, "mood": 1, "energy": -1, "hunger": -1}
        result["commands"] = cmds
        return result

    if etype == "FEED":
        result["reply"] = "냠냠! 맛있어!"
        result["face"] = random.choice(FACES)
        result["delta"] = {"joy": 6, "mood": 2, "energy": +1, "hunger": +18}
        result["commands"] = [{"type": "SHAKE", "sec": 0.5, "strength": 2}]
        return result

    if etype == "PET":
        result["reply"] = "헤헤… 쓰다듬어줘서 좋아…"
        result["face"] = "normal01"
        result["delta"] = {"joy": 7, "mood": 4, "energy": 0, "hunger": -1}
        return result

    if etype == "PLAY":
        result["reply"] = "놀자!!"
        result["face"] = "normal01"
        result["delta"] = {"joy": 8, "mood": 3, "energy": -2, "hunger": -2}
        result["commands"] = [{"type": "JUMP", "strength": 13}, {"type": "SET_MODE", "mode": "walk", "sec": 1.2}]
        return result

    # CHAT
    if "슬퍼" in text or "안돼" in text:
        result["reply"] = "안됐다… 내가 옆에 있어줄게."
        result["face"] = "normal03"
        result["delta"] = {"joy": 4, "mood": 1, "energy": 0, "hunger": -1}
        return result

    result["reply"] = f"찍찍! {text}라니 신기해!"
    result["face"] = random.choice(FACES)
    result["delta"] = {"joy": 5, "mood": 1, "energy": 0, "hunger": -1}
    return result