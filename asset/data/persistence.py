from __future__ import annotations

import json
import os
import time
from pathlib import Path
from state import PetState 
from typing import Any, Dict, Optional,Callable
from dataclasses import asdict, dataclass, field
from PySide6.QtCore import QObject, QStandardPaths, QTimer, Signal


def app_data_dir(app_name: str = "Maripet") -> Path:
    base = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    # AppDataLocation에 이미 앱 폴더가 들어가기도 하는데, 안전하게 한번 더 고정하고 싶으면:
    # base = base / app_name
    base.mkdir(parents=True, exist_ok=True)
    return base


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """
    저장 중 앱이 죽어도 파일이 깨질 확률을 줄이는 방식.
    tmp에 쓰고 replace로 덮어씀(원자적 교체).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)

    class SaveManager(QObject):
    saved = Signal(str)          # 저장 성공 메시지
    save_failed = Signal(str)    # 저장 실패 메시지

    def __init__(
        self,
        state: PetState,
        save_path: Optional[Path] = None,
        autosave_sec: float = 30.0,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.state = state
        self.save_path = save_path or (app_data_dir() / "save.json")

        self._dirty = False
        self._last_saved_at = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(int(max(2.0, autosave_sec) * 1000))
        self._timer.timeout.connect(self._autosave_tick)
        self._timer.start()

    def mark_dirty(self) -> None:
        self._dirty = True

    def load(self) -> PetState:
        try:
            if not self.save_path.exists():
                return self.state
            raw = json.loads(self.save_path.read_text(encoding="utf-8"))
            loaded = PetState.from_dict(raw)
            # 기존 state 객체를 유지하고 싶으면(모든 창이 같은 객체 참조 중일 가능성 높아서)
            # "교체"가 아니라 "필드 덮어쓰기"로 가자:
            self._apply_loaded_to_existing(loaded)
            self._dirty = False
            return self.state
        except Exception as e:
            self.save_failed.emit(f"불러오기 실패: {e}")
            return self.state

    def _apply_loaded_to_existing(self, loaded: PetState) -> None:
        # 필요한 필드만 덮어쓰기 (창들이 self.state를 잡고 있으니까 객체 교체하면 꼬일 수 있음)
        self.state.user_name = loaded.user_name
        self.state.pet_name = loaded.pet_name
        self.state.hunger = loaded.hunger
        self.state.energy = loaded.energy
        self.state.max_energy = loaded.max_energy
        self.state.mood = loaded.mood
        self.state.fun = loaded.fun
        self.state.money = loaded.money
        self.state.inventory = loaded.inventory
        self.state.owned_bg = loaded.owned_bg
        self.state.placed_bg = loaded.placed_bg
        self.state.last_face = loaded.last_face

    def save_now(self, reason: str = "manual") -> None:
        try:
            payload = {
                "version": 1,
                "saved_at": time.time(),
                "reason": reason,
                "state": self.state.to_dict(),
            }
            atomic_write_json(self.save_path, payload)
            self._dirty = False
            self._last_saved_at = time.time()
            self.saved.emit("저장 완료")
        except Exception as e:
            self.save_failed.emit(f"저장 실패: {e}")

    def _autosave_tick(self) -> None:
        if not self._dirty:
            return
        self.save_now(reason="autosave")