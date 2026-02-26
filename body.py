"""
body.py - AI 결과를 펫 상태/애니메이션에 적용하는 함수
"""
import random
from typing import Any, Dict

from config import FACE_HOLD_SEC
from state import PetState


def apply_ai_result(state: PetState, pet_obj, result: Dict[str, Any]):
    """
    Groq AI 응답(result)을 PetState + 펫 위젯에 반영한다.
    pet_obj: PetWindow 또는 HousePetWidget
    """
    state.apply_delta(result.get("delta", {}))

    face = result.get("face")
    if face:
        try:
            is_low = (
                (state.mood <= 35) or (state.fun <= 20)
                or (state.energy <= 20) or (state.hunger <= 18)
            )
            sad_faces = getattr(pet_obj, "sad_faces", [])
            normal_faces = getattr(pet_obj, "normal_faces", None)
            if (not is_low) and (face in sad_faces) and normal_faces:
                face = random.choice(list(normal_faces))
        except Exception:
            pass

        if hasattr(pet_obj, "set_face"):
            pet_obj.set_face(face, hold_sec=FACE_HOLD_SEC)

    reply = result.get("reply", "")
    sec = float(result.get("bubble_sec", 2.2))
    if reply and hasattr(pet_obj, "say"):
        pet_obj.say(reply, duration=sec)

    for cmd in result.get("commands", []):
        ctype = cmd.get("type")
        if ctype == "SHAKE" and hasattr(pet_obj, "start_shake"):
            pet_obj.start_shake(sec=float(cmd.get("sec", 0.5)), strength=int(cmd.get("strength", 3)))
        elif ctype == "JUMP" and hasattr(pet_obj, "do_jump"):
            pet_obj.do_jump(int(cmd.get("strength", 12)))
        elif ctype == "SET_MODE" and hasattr(pet_obj, "set_mode"):
            pet_obj.set_mode(str(cmd.get("mode", "normal")), sec=float(cmd.get("sec", 1.5)))
