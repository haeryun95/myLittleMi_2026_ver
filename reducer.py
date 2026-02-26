"""
reducer.py - 시간 경과에 따른 상태 decay 로직
"""
from state import PetState, clamp
from config import DECAY_MULT


def tick_decay(state: PetState, dt_sec: float = 1.0) -> None:
    """
    1초 단위로 호출하는 상태 감소 함수.
    dt_sec: 경과 시간(초)
    """
    rate = DECAY_MULT * dt_sec

    # 배고픔 증가 (시간이 지날수록 배고파짐)
    state.hunger = clamp(state.hunger - rate * 0.5)

    # 재미 감소
    state.fun = clamp(state.fun - rate * 0.3)

    # 에너지 감소 (깨어있으면 조금씩 소모)
    state.energy = clamp(state.energy - rate * 0.2, 0.0, state.max_energy)

    # 기분은 욕구에 의해 간접적으로 변하도록 위임
    state.update_mood_from_needs(dt_sec=dt_sec)
