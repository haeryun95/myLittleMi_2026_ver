"""
main.py - 앱 진입점
"""
import sys

from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from config import ASSET_DIR, FURNITURE_JSON_PATH, QSS_PATH, app_icon_PATH
from state import PetState
from utils.helpers import load_qss
from windows.pet_window import PetWindow
from windows.control_panel import ControlPanel


def main():
    app = QApplication(sys.argv)

    # 앱 아이콘
    app_icon = QIcon(str(app_icon_PATH)) if app_icon_PATH.exists() else None
    if app_icon:
        app.setWindowIcon(app_icon)

    # 폰트 로드
    font_dir = ASSET_DIR / "font"
    if font_dir.exists():
        ttf_list = list(font_dir.glob("*.ttf"))
        if ttf_list:
            for fp in ttf_list:
                QFontDatabase.addApplicationFont(str(fp))
        else:
            print("❌ asset/font 폴더에 .ttf가 없어:", font_dir)
    else:
        print("❌ font 폴더가 없어:", font_dir)

    # QSS 로드
    load_qss(app, QSS_PATH)

    if not FURNITURE_JSON_PATH.exists():
        print("⚠️ furniture.json이 없어! 폴더 스캔 폴백으로 실행 중:", FURNITURE_JSON_PATH)

    # 앱 시작
    state = PetState()
    pet = PetWindow(state, app_icon=app_icon)
    panel = ControlPanel(state, pet, app_icon=app_icon)

    pet.show()
    panel.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
