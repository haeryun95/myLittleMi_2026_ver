"""
utils/image_loader.py - 이미지/픽스맵 로딩 유틸리티
"""
from pathlib import Path
from typing import Dict, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QTransform


def load_folder_pixmaps_as_map(folder: Path, scale: float) -> Dict[str, QPixmap]:
    result: Dict[str, QPixmap] = {}
    if not folder.exists():
        return result
    for f in sorted(folder.glob("*.png")):
        p = QPixmap(str(f))
        if p.isNull():
            continue
        if scale != 1.0:
            p = p.scaled(
                int(p.width() * scale),
                int(p.height() * scale),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        result[f.stem] = p
    return result


def load_folder_pixmaps_as_list(folder: Path, scale: float) -> List[QPixmap]:
    if not folder.exists():
        return []
    frames: List[QPixmap] = []
    for f in sorted(folder.glob("*.png")):
        p = QPixmap(str(f))
        if p.isNull():
            continue
        if scale != 1.0:
            p = p.scaled(
                int(p.width() * scale),
                int(p.height() * scale),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        frames.append(p)
    return frames


def make_flipped_frames(frames: List[QPixmap]) -> List[QPixmap]:
    """좌우 반전 프레임 리스트 생성"""
    t = QTransform()
    t.scale(-1, 1)
    return [fr.transformed(t, Qt.SmoothTransformation) for fr in frames]
