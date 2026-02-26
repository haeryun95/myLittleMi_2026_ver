from typing import Dict, Any

def apply_ai_result(state, pet, result: Dict[str, Any]):
    # 1) delta
    delta = result.get("delta", {})
    state.apply_delta(delta)

    # 2) face
    face = result.get("face")
    if face:
        state.last_face = face
        pet.set_face(face, hold_sec=6.0)

    # 3) bubble
    reply = result.get("reply", "")
    sec = float(result.get("bubble_sec", 2.2))
    if reply:
        pet.say(reply, duration=sec)

    # 4) commands
    for cmd in result.get("commands", []):
        ctype = cmd.get("type")

        if ctype == "SHAKE":
            pet.start_shake(
                sec=float(cmd.get("sec", 0.5)),
                strength=int(cmd.get("strength", 3)),
            )
        elif ctype == "JUMP":
            pet.do_jump(int(cmd.get("strength", 12)))
        elif ctype == "SET_MODE":
            pet.set_mode(
                mode=str(cmd.get("mode", "normal")),
                sec=float(cmd.get("sec", 1.5)),
            )