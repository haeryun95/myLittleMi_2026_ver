import time
import json
import random
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QVBoxLayout, QWidget, QMenu, QSystemTrayIcon,
    QStyle, QStyleOption, QComboBox
)

from config import app_icon_DIR
from utils.helpers import trigger_pet_action_bubble
from state import PetState, clamp
from windows.name_window import NameWindow
from windows.house_window import HouseWindow
from windows.job_window import JobWindow
from windows.study_window import StudyWindow


# -------------------------
# 0. Language manager (i18n)
# -------------------------
class LangManager:
    def __init__(self, default_lang="ko"):
        self.lang_code = default_lang
        self.data = {}
        self.load_lang(default_lang)

    def load_lang(self, lang_code):
        self.lang_code = lang_code
        path = Path(__file__).resolve().parents[1] / "asset" / "lang" / f"{lang_code}.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        else:
            print(f"DEBUG: Lang file not found at {path}")

    def get(self, key_path, default=""):
        keys = key_path.split(".")
        temp = self.data
        try:
            for k in keys:
                temp = temp[k]
            return temp
        except (KeyError, TypeError):
            return default


# -------------------------
# Helpers
# -------------------------
def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


THEME_BASE_DIR = _project_root() / "asset" / "theme"


def _p(p: Path) -> str:
    return p.resolve().as_posix()


# -------------------------
# 1. Base widget
# -------------------------
class StyledWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, painter, self)
        painter.end()


# -------------------------
# 2. Title bar
# -------------------------
class TitleBar(StyledWidget):
    def __init__(self, frame_parent: QWidget, panel: "ControlPanel"):
        super().__init__(frame_parent)
        self.panel = panel
        self.setObjectName("TitleBar")
        self.setFixedHeight(36)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(6)

        self.sys_icon = QLabel()
        self.sys_icon.setObjectName("SystemIcon")
        self.sys_icon.setFixedSize(20, 20)
        lay.addWidget(self.sys_icon)

        self.title_label = QLabel()
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setStyleSheet("font-size: 11px;")
        lay.addWidget(self.title_label)

        lay.addStretch(1)

        self.set_btn = QPushButton()
        self.min_btn = QPushButton()
        self.close_btn = QPushButton()

        for btn, slot in [
            (self.set_btn, self.panel.open_settings),
            (self.min_btn, self.panel.minimize_to_tray),
            (self.close_btn, self.panel.quit_app),
        ]:
            btn.setFixedSize(20, 20)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("background: transparent; border: none;")
            btn.clicked.connect(slot)
            lay.addWidget(btn)


# -------------------------
# 2-1. Settings title bar
# -------------------------
class SettingsTitleBar(StyledWidget):
    def __init__(self, frame_parent: QWidget, win: "SettingsWindow"):
        super().__init__(frame_parent)
        self.win = win
        self.setObjectName("TitleBar")
        self.setFixedHeight(36)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(6)

        self.sys_icon = QLabel()
        self.sys_icon.setObjectName("SystemIcon")
        self.sys_icon.setFixedSize(20, 20)
        lay.addWidget(self.sys_icon)

        self.title_label = QLabel()
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setStyleSheet("font-size: 11px;")
        lay.addWidget(self.title_label)

        lay.addStretch(1)

        self.close_btn = QPushButton()
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet("background: transparent; border: none;")
        self.close_btn.clicked.connect(self.win.close)
        lay.addWidget(self.close_btn)


# -------------------------
# 3. Main panel
# -------------------------
class ControlPanel(QWidget):
    def __init__(
        self,
        state: PetState,
        pet,
        app_icon: Optional[QIcon] = None,
        default_theme: str = "pink",
        default_lang: str = "ko",
        save_callback=None,
    ):
        super().__init__()
        self.state = state
        self.pet = pet
        self.theme = default_theme
        self.lang = LangManager(default_lang)
        self.save_callback = save_callback

        # Default names
        self.user_name = self.lang.get("user_name", "나")
        if not self.state.pet_name:
            self.state.pet_name = self.lang.get("pet_name", "라이미")

        self.home_window = None
        self.job_window = None
        self.study_window = None
        self.name_window = None
        self.sw = None

        QApplication.instance().setQuitOnLastWindowClosed(False)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(300, 380)
        self.setWindowOpacity(0.95)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.frame = StyledWidget()
        self.frame.setObjectName("WindowFrame")
        outer.addWidget(self.frame)

        frame_lay = QVBoxLayout(self.frame)
        frame_lay.setContentsMargins(0, 0, 0, 0)
        frame_lay.setSpacing(0)

        self.titlebar = TitleBar(self.frame, self)
        frame_lay.addWidget(self.titlebar)

        content_widget = QWidget()
        self.root = QVBoxLayout(content_widget)
        self.root.setContentsMargins(10, 2, 10, 2)
        self.root.setSpacing(4)
        frame_lay.addWidget(content_widget)

        # Header
        self.header_widget = StyledWidget()
        self.header_widget.setObjectName("PanelHeader")
        self.header_widget.setFixedSize(280, 36)

        h_lay = QHBoxLayout(self.header_widget)
        h_lay.setContentsMargins(10, 0, 10, 0)
        h_lay.setSpacing(8)

        self.money_icon = QLabel()
        self.money_icon.setFixedSize(20, 20)

        self.money_label = QLabel("0")
        self.money_label.setObjectName("MoneyLabel")
        self.money_label.setStyleSheet("font-size: 10px;")

        self.name_label = QLabel("")
        self.name_label.setObjectName("NameLabel")
        self.name_label.setStyleSheet("font-weight: bold; font-size: 11px;")

        self.mood_label = QLabel("")
        self.mood_label.setObjectName("MoodLabel")
        self.mood_label.setAlignment(Qt.AlignCenter)
        self.mood_label.setStyleSheet(
            "background: rgba(255,255,255,0.2); border-radius: 6px; padding: 2px 6px; font-size: 10px;"
        )

        h_lay.addWidget(self.money_icon)
        h_lay.addWidget(self.money_label)
        h_lay.addStretch(1)
        h_lay.addWidget(self.name_label)
        h_lay.addStretch(1)
        h_lay.addWidget(self.mood_label)
        self.root.addWidget(self.header_widget)

        # Chat log
        chat_bg = StyledWidget()
        chat_bg.setObjectName("ChatLog")
        chat_bg.setFixedSize(280, 85)

        chat_lay = QVBoxLayout(chat_bg)
        chat_lay.setContentsMargins(8, 6, 2, 6)
        chat_lay.setSpacing(0)

        self.chat_log = QTextEdit()
        self.chat_log.setObjectName("ChatText")
        self.chat_log.setReadOnly(True)
        self.chat_log.setStyleSheet("background: transparent; border: none; font-size: 11px;")
        chat_lay.addWidget(self.chat_log)

        self.root.addWidget(chat_bg, 0, Qt.AlignCenter)

        # Status panel
        self.status_container = StyledWidget()
        self.status_container.setObjectName("PanelStatus")
        self.status_container.setFixedSize(280, 120)

        s_vbox = QVBoxLayout(self.status_container)
        s_vbox.setContentsMargins(8, 4, 8, 4)
        s_vbox.setSpacing(0)

        self.status_rows = {}
        s_info = [
            ("fun", "ic_fun.png", "GaugeFun"),
            ("mood", "ic_mood.png", "GaugeMood"),
            ("hunger", "ic_hunger.png", "GaugeHunger"),
            ("energy", "ic_energy.png", "GaugeEnergy"),
        ]

        for key, icon_n, obj_n in s_info:
            row = QWidget()
            row.setFixedSize(264, 28)

            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)

            si = QLabel()
            si.setFixedSize(20, 20)
            si.setAlignment(Qt.AlignCenter)

            kl = QLabel()
            kl.setFixedWidth(36)
            kl.setStyleSheet("font-size: 10px; background: transparent;")

            tr = QLabel()
            tr.setObjectName("BarTrack")
            tr.setFixedSize(180, 18)

            ga = QLabel(tr)
            ga.setObjectName(obj_n)
            ga.setFixedSize(0, 18)

            vl = QLabel(tr)
            vl.setFixedSize(180, 18)
            vl.setAlignment(Qt.AlignCenter)
            vl.setStyleSheet("color: white; font-weight: bold; font-size: 9px;")

            rl.addWidget(si)
            rl.addWidget(kl)
            rl.addSpacing(4)
            rl.addWidget(tr)
            rl.addStretch(1)

            s_vbox.addWidget(row, 0, Qt.AlignCenter)
            self.status_rows[key] = (ga, si, icon_n, vl, kl)

        self.root.addWidget(self.status_container, 0, Qt.AlignCenter)

        # Bottom buttons
        self.btn_widgets = []
        bc = QWidget()
        bc.setFixedWidth(280)

        bg = QGridLayout(bc)
        bg.setContentsMargins(0, 0, 0, 0)
        bg.setSpacing(4)

        acts = [
            ("feed", "feed.png", self.feed_pet),
            ("chat", "pet.png", self.pet_pet),
            ("play", "play.png", self.play_pet),
            ("home", "home.png", self.open_home),
            ("job", "job.png", self.open_job),
            ("study", "study.png", self.open_study),
        ]

        for i, (k, img, f) in enumerate(acts):
            b = QPushButton()
            b.setObjectName("MenuButton")
            b.setFixedSize(84, 28)
            b.clicked.connect(f)
            b.setStyleSheet("font-size: 11px;")
            bg.addWidget(b, i // 3, i % 3)
            self.btn_widgets.append((b, img, k))

        self.root.addWidget(bc, 0, Qt.AlignCenter)

        self.guide_label = QLabel()
        self.guide_label.setAlignment(Qt.AlignCenter)
        self.guide_label.setStyleSheet("color: #fff; font-size: 9px; font-weight: bold;")
        self.root.addWidget(self.guide_label, 0, Qt.AlignCenter)

        self.apply_theme(self.theme)
        self._init_tray(app_icon)
        self.retranslate_ui()
        self._sync_ui()

        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._sync_ui)
        self.ui_timer.start(250)

        # Auto save every 60 seconds
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self._auto_save)
        self.auto_save_timer.start(60000)

        self.chat_log.append(f"<div style='color:#aaaaaa;'>{self.lang.get('ui.sys_ready')}</div>")

    # -------------------------
    # Save
    # -------------------------
    def _auto_save(self):
        try:
            if callable(self.save_callback):
                self.save_callback(reason="auto")
                return

            if hasattr(self.state, "save") and callable(getattr(self.state, "save")):
                self.state.save()
                return

            if hasattr(self.state, "save_now") and callable(getattr(self.state, "save_now")):
                self.state.save_now(reason="auto")
                return

        except Exception as ex:
            self.chat_log.append(
                f"<div style='color:#ff8080;'>[Auto Save Error] {ex}</div>"
            )

    def manual_save(self):
        try:
            if callable(self.save_callback):
                self.save_callback(reason="manual")
                self.chat_log.append(
                    f"<div style='color:#aaaaaa;'>{self.lang.get('ui.saved', 'Saved.')}</div>"
                )
                return

            if hasattr(self.state, "save") and callable(getattr(self.state, "save")):
                self.state.save()
                self.chat_log.append(
                    f"<div style='color:#aaaaaa;'>{self.lang.get('ui.saved', 'Saved.')}</div>"
                )
                return

            if hasattr(self.state, "save_now") and callable(getattr(self.state, "save_now")):
                self.state.save_now(reason="manual")
                self.chat_log.append(
                    f"<div style='color:#aaaaaa;'>{self.lang.get('ui.saved', 'Saved.')}</div>"
                )
                return

        except Exception as ex:
            self.chat_log.append(
                f"<div style='color:#ff8080;'>[Save Error] {ex}</div>"
            )

    # -------------------------
    # Chat reset for language change
    # -------------------------
    def reset_chat_log(self, reason_key: str = "ui.sys_ready"):
        self.chat_log.clear()
        self.chat_log.append(
            f"<div style='color:#aaaaaa;'>{self.lang.get(reason_key)}</div>"
        )

    # -------------------------
    # i18n
    # -------------------------
    def _get_localized_mood(self):
        m = self.state.mood
        mk = "v_happy" if m > 80 else "happy" if m > 60 else "normal" if m > 40 else "sad" if m > 20 else "angry"
        return self.lang.get(f"moods.{mk}")

    def retranslate_ui(self):
        L = self.lang
        self.titlebar.title_label.setText(f"{self.state.pet_name} - {L.get('title')}")
        self.guide_label.setText(L.get("ui.guide"))

        for b, _, k in self.btn_widgets:
            b.setText(L.get(f"buttons.{k}"))

        for k, r in self.status_rows.items():
            r[4].setText(L.get(f"status.{k}"))

        if hasattr(self, "action_open"):
            self.action_open.setText(L.get("ui.tray_open"))
            self.action_quit.setText(L.get("ui.tray_quit"))

        if self.sw is not None and self.sw.isVisible():
            self.sw.retranslate_ui()

    def _sync_ui(self):
        self.money_label.setText(str(int(self.state.money)))
        self.name_label.setText(self.state.pet_name)
        self.mood_label.setText(self._get_localized_mood())
        self.titlebar.title_label.setText(f"{self.state.pet_name} - {self.lang.get('title')}")

        for k, r in self.status_rows.items():
            val = getattr(self.state, k)
            r[0].setFixedWidth(int((val / 100) * 180))
            r[3].setText(f"{int(val)} / 100")

    # -------------------------
    # Theme / icons
    # -------------------------
    def apply_theme(self, tn: str):
        self.theme = tn
        tp = THEME_BASE_DIR / tn
        ud = tp / "ui"
        self.current_icon_dir = tp / "icon"

        style = ""
        for p in [THEME_BASE_DIR / "common.qss", tp / f"{tn}.qss"]:
            if p.exists():
                style += p.read_text(encoding="utf-8") + "\n"

        tc = "#ffffff" if tn == "dark" else "#703355"

        mapping = {
            "window_frame": _p(ud / "window_frame.png"),
            "titlebar_bg": _p(ud / "window_titlebar.png"),
            "panel_header": _p(ud / "panel_header.png"),
            "panel_status": _p(ud / "panel_status.png"),
            "panel_chat": _p(ud / "panel_chat.png"),
            "btn_m": _p(ud / "btn_m.png"),
            "btn_m_press": _p(ud / "btn_m_press.png"),
            "btn_ic": _p(ud / "btn_ic.png"),
            "btn_close_hover": _p(ud / "btn_close_hover.png"),
            "bar_track": _p(ud / "bar_track.png"),
            "bar_track_fun": _p(ud / "bar_track_fun.png"),
            "bar_track_mood": _p(ud / "bar_track_mood.png"),
            "bar_track_hunger": _p(ud / "bar_track_hunger.png"),
            "bar_track_energy": _p(ud / "bar_track_energy.png"),
            "text_color": tc,
            "ic_setting": _p(self.current_icon_dir / "ic_setting.png"),
            "ic_min": _p(self.current_icon_dir / "ic_min.png"),
            "ic_close": _p(self.current_icon_dir / "ic_close.png"),
        }

        for k, v in mapping.items():
            style = style.replace(f"{{{k}}}", v)

        if Path(_p(ud / "panel_chat.png")).exists():
            style += f"\n#ChatLog {{ border-image: url('{_p(ud / 'panel_chat.png')}') 0 0 0 0 stretch stretch; }}"

        if Path(_p(ud / "panel_status.png")).exists():
            style += f"\n#PanelStatus {{ border-image: url('{_p(ud / 'panel_status.png')}') 0 0 0 0 stretch stretch; }}"

        self.setStyleSheet(style)

        if self.sw is not None:
            self.sw.setStyleSheet(style)
            self.sw._update_icons()

        self._update_icons()

    def _update_icons(self):
        sys_p = self.current_icon_dir / "ic_main.png"
        if sys_p.exists():
            self.titlebar.sys_icon.setPixmap(
                QPixmap(str(sys_p.resolve())).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

        for btn, img in [
            (self.titlebar.set_btn, "ic_setting.png"),
            (self.titlebar.min_btn, "ic_min.png"),
            (self.titlebar.close_btn, "ic_close.png"),
        ]:
            p = self.current_icon_dir / img
            if p.exists():
                btn.setIcon(QIcon(str(p.resolve())))
                btn.setIconSize(QSize(20, 20))

        coin_p = self.current_icon_dir / "ic_coin.png"
        if coin_p.exists():
            self.money_icon.setPixmap(
                QPixmap(str(coin_p.resolve())).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

        for _, r in self.status_rows.items():
            p = self.current_icon_dir / r[2]
            if p.exists():
                r[1].setPixmap(
                    QPixmap(str(p.resolve())).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )

        for b, img, _ in self.btn_widgets:
            p = self.current_icon_dir / img
            if not p.exists():
                p = app_icon_DIR / img
            if p.exists():
                b.setIcon(QIcon(str(p.resolve())))
                b.setIconSize(QSize(20, 20))

    # -------------------------
    # Sub-window management
    # -------------------------
    def _close_all_sub_windows(self, except_win=None):
        for w in [self.home_window, self.job_window, self.study_window]:
            if w and w != except_win and w.isVisible():
                w.close()

    def _sync_and_show_main_pet(self, sub_window):
        if not any(w and w != sub_window and w.isVisible() for w in [self.home_window, self.job_window, self.study_window]):
            sub_pet = getattr(sub_window, "house_pet", getattr(sub_window, "pet", None))
            if sub_pet and self.pet:
                self.pet.sleeping = getattr(sub_pet, "sleeping", False)
                self.pet.sleep_end_at = getattr(sub_pet, "sleep_end_at", 0)
                mode = "sleep" if self.pet.sleeping else "normal"
                self.pet.set_mode(
                    mode,
                    sec=max(0.1, self.pet.sleep_end_at - time.time()) if self.pet.sleeping else 99999
                )

            if self.pet:
                self.pet.show()
                self.pet.raise_()

    def open_home(self):
        self._close_all_sub_windows()
        is_sleeping, sleep_end = (self.pet.sleeping, self.pet.sleep_end_at) if self.pet else (False, 0)

        if self.pet:
            self.pet.hide()

        if self.home_window is None:
            self.home_window = HouseWindow(self.state, self.pet, self.windowIcon())
            orig_close = self.home_window.closeEvent
            self.home_window.closeEvent = lambda e: (self._sync_and_show_main_pet(self.home_window), orig_close(e))

        if is_sleeping and hasattr(self.home_window, "house_pet"):
            h_pet = self.home_window.house_pet
            h_pet.sleeping = True
            h_pet.sleep_end_at = sleep_end
            h_pet.set_mode("sleep", sec=max(0.1, sleep_end - time.time()))

        self.home_window.show()
        self.home_window.raise_()

    def open_job(self):
        self._close_all_sub_windows()

        if self.pet:
            self.pet.hide()

        if self.job_window is None:
            self.job_window = JobWindow(self.state, self.windowIcon())
            orig_close = self.job_window.closeEvent
            self.job_window.closeEvent = lambda e: (self._sync_and_show_main_pet(self.job_window), orig_close(e))

        self.job_window.show()
        self.job_window.raise_()

    def open_study(self):
        self._close_all_sub_windows()

        if self.pet:
            self.pet.hide()

        if self.study_window is None:
            self.study_window = StudyWindow(self.state, self.windowIcon())
            orig_close = self.study_window.closeEvent
            self.study_window.closeEvent = lambda e: (self._sync_and_show_main_pet(self.study_window), orig_close(e))

        self.study_window.show()
        self.study_window.raise_()

    def open_settings(self):
        if self.sw is None:
            self.sw = SettingsWindow(self.state, self)
            self.sw.sync_from_panel()
        else:
            self.sw.sync_from_panel()

        p = self.geometry().topRight()
        self.sw.move(p.x() + 10, p.y())
        self.sw.show()
        self.sw.raise_()

    # -------------------------
    # Tray / window
    # -------------------------
    def _init_tray(self, icon):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray = QSystemTrayIcon(icon if icon else self.windowIcon(), self)
        self.tray_menu = QMenu()

        self.action_open = self.tray_menu.addAction("", lambda: self._on_tray_activated(QSystemTrayIcon.DoubleClick))
        self.action_quit = self.tray_menu.addAction("", lambda: QApplication.instance().quit())

        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.raise_()
            self.activateWindow()

    def minimize_to_tray(self):
        self.hide()

    def quit_app(self):
        QApplication.instance().quit()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._old_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if hasattr(self, "_old_pos"):
            delta = e.globalPosition().toPoint() - self._old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self._old_pos = e.globalPosition().toPoint()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.minimize_to_tray()
        else:
            super().keyPressEvent(event)

    # -------------------------
    # Interaction helpers
    # -------------------------
    def _active_pet_for_chat(self):
        for w in [self.home_window, self.job_window, self.study_window]:
            if w and w.isVisible():
                return getattr(w, "house_pet", getattr(w, "pet", self.pet))
        return self.pet

    def _format_stat(self, k, v):
        name = self.lang.get(f"status.{k}")
        style = "font-size:10px; font-weight:bold;"
        return f"<span style='color:{('#FF5E5E' if v > 0 else '#4A90E2')}; {style}'>{'▲' if v > 0 else '▼'}{name} {abs(v)}</span>"

    def _delayed_pet_response(self, target, msg, stats, anim):
        stat_block = f"<br>&nbsp;└ <span style='background:rgba(255,160,209,0.15);'>{stats}</span>" if stats else ""
        self.chat_log.append(f"<div><b>{self.state.pet_name}</b> : {msg}{stat_block}</div>")
        self.chat_log.verticalScrollBar().setValue(self.chat_log.verticalScrollBar().maximum())

        if anim:
            anim()

        if target:
            trigger_pet_action_bubble(target, self.chat_log, [msg])

    def handle_interaction(self, user_key, logic):
        user_msg = self.lang.get(f"interactions.{user_key}_user")
        target = self._active_pet_for_chat()

        self.chat_log.append(
            f"<div style='color:#888;'><b>{self.user_name}</b> : {user_msg}</div>"
        )

        is_sleeping = getattr(target, "sleeping", False) or (
            hasattr(target, "sleep_end_at") and time.time() < target.sleep_end_at
        )

        def respond():
            if is_sleeping:
                delta_value = -random.randint(5, 15)
                self.state.mood = clamp(self.state.mood + delta_value)
                self._delayed_pet_response(
                    target,
                    random.choice(self.lang.get("interactions.sleep_pet")),
                    self._format_stat("mood", delta_value),
                    lambda: target.start_shake(0.5, 3) if hasattr(target, "start_shake") else None
                )
            else:
                logic(target)

        QTimer.singleShot(100, respond)

    # -------------------------
    # Interactions
    # -------------------------
    def feed_pet(self):
        def logic(target):
            hunger_up = random.randint(1, 20)
            mood_up = random.randint(1, 10)
            self.state.hunger = clamp(self.state.hunger + hunger_up)
            self.state.mood = clamp(self.state.mood + mood_up)

            self._delayed_pet_response(
                target,
                random.choice(self.lang.get("interactions.feed_pet")),
                f"{self._format_stat('hunger', hunger_up)} {self._format_stat('mood', mood_up)}",
                lambda: target.trigger_eat_visual() if hasattr(target, "trigger_eat_visual") else target.set_action("eat")
            )

        self.handle_interaction("feed", logic)

    def pet_pet(self):
        def logic(target):
            mood_up = random.randint(1, 20)
            fun_up = random.randint(1, 20)
            self.state.mood = clamp(self.state.mood + mood_up)
            self.state.fun = clamp(self.state.fun + fun_up)

            self._delayed_pet_response(
                target,
                random.choice(self.lang.get("interactions.chat_pet")),
                f"{self._format_stat('mood', mood_up)} {self._format_stat('fun', fun_up)}",
                lambda: target.start_shake(0.4, 2) if hasattr(target, "start_shake") else target.set_action("jump")
            )

        self.handle_interaction("chat", logic)

    def play_pet(self):
        def logic(target):
            energy_down = -random.randint(1, 20)
            fun_up = random.randint(1, 20)
            mood_up = random.randint(1, 20)

            self.state.energy = clamp(self.state.energy + energy_down, 0, 100)
            self.state.fun = clamp(self.state.fun + fun_up)
            self.state.mood = clamp(self.state.mood + mood_up)

            def anim():
                if hasattr(target, "do_jump"):
                    target.do_jump(14)
                if self.state.energy < 4 and hasattr(target, "start_sleep_for_60s"):
                    QTimer.singleShot(1000, target.start_sleep_for_60s)

            self._delayed_pet_response(
                target,
                random.choice(self.lang.get("interactions.play_pet")),
                f"{self._format_stat('energy', energy_down)} {self._format_stat('fun', fun_up)} {self._format_stat('mood', mood_up)}",
                anim
            )

        self.handle_interaction("play", logic)


# -------------------------
# 4. Settings window
# -------------------------
class SettingsWindow(StyledWidget):
    BASE_W, BASE_H = 300, 420
    SCALE = 0.90
    WIN_W = int(BASE_W * SCALE)
    WIN_H = int(BASE_H * SCALE)

    def __init__(self, state, panel: ControlPanel):
        super().__init__()
        self.state = state
        self.panel = panel

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(self.WIN_W, self.WIN_H)
        self.setObjectName("SettingsWindow")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.frame = StyledWidget(self)
        self.frame.setObjectName("WindowFrame")
        outer.addWidget(self.frame)

        frame_lay = QVBoxLayout(self.frame)
        frame_lay.setContentsMargins(0, 0, 0, 0)
        frame_lay.setSpacing(0)

        self.titlebar = SettingsTitleBar(self.frame, self)
        frame_lay.addWidget(self.titlebar)

        content = QWidget(self.frame)
        frame_lay.addWidget(content, 1)

        pad = int(20 * self.SCALE)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(pad, pad - 2, pad, pad)
        lay.setSpacing(int(10 * self.SCALE))

        self.tl = QLabel()
        self.tl.setStyleSheet("font-size: 14px; font-weight: bold; color: white;")
        lay.addWidget(self.tl)

        self.ul = QLabel()
        lay.addWidget(self.ul)

        self.ui = QTextEdit()
        self.ui.setFixedHeight(int(30 * self.SCALE))
        self.ui.setText(panel.user_name)
        lay.addWidget(self.ui)

        self.pl = QLabel()
        lay.addWidget(self.pl)

        self.pi = QTextEdit()
        self.pi.setFixedHeight(int(30 * self.SCALE))
        self.pi.setText(state.pet_name)
        lay.addWidget(self.pi)

        self.thl = QLabel()
        lay.addWidget(self.thl)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["pink", "dark"])
        self.theme_combo.setCurrentText(self.panel.theme)
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        lay.addWidget(self.theme_combo)

        self.ll = QLabel()
        lay.addWidget(self.ll)

        lang_row = QHBoxLayout()
        lang_row.setSpacing(int(8 * self.SCALE))

        self.lang_ko_btn = QPushButton()
        self.lang_en_btn = QPushButton()

        for b in (self.lang_ko_btn, self.lang_en_btn):
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(int(34 * self.SCALE))
            b.setStyleSheet("""
                QPushButton {
                    border-radius: 10px;
                    padding: 6px 10px;
                    border: 1px solid rgba(255,255,255,90);
                    background: rgba(0,0,0,35);
                    color: white;
                    font-weight: 800;
                }
                QPushButton:checked {
                    background: rgba(255,160,209,80);
                    border: 1px solid rgba(255,255,255,150);
                }
            """)

        self.lang_ko_btn.clicked.connect(lambda: self._select_lang("ko"))
        self.lang_en_btn.clicked.connect(lambda: self._select_lang("en"))

        lang_row.addWidget(self.lang_ko_btn, 1)
        lang_row.addWidget(self.lang_en_btn, 1)
        lay.addLayout(lang_row)

        lay.addStretch(1)

        self.sb = QPushButton()
        self.sb.setFixedHeight(int(36 * self.SCALE))
        self.sb.clicked.connect(self.save)
        lay.addWidget(self.sb)

        self._selected_lang = self.panel.lang.lang_code
        self.sync_from_panel()
        self.retranslate_ui()

        self.setStyleSheet(self.panel.styleSheet())
        self._update_icons()

    def sync_from_panel(self):
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentText(self.panel.theme)
        self.theme_combo.blockSignals(False)

        self._selected_lang = self.panel.lang.lang_code
        self._apply_lang_btn_state()

        self.ui.setText(self.panel.user_name)
        self.pi.setText(self.state.pet_name)

        self.retranslate_ui()
        self._update_icons()

    def _apply_lang_btn_state(self):
        self.lang_ko_btn.setChecked(self._selected_lang == "ko")
        self.lang_en_btn.setChecked(self._selected_lang == "en")

    def _select_lang(self, code: str):
        self._selected_lang = code
        self._apply_lang_btn_state()

    def retranslate_ui(self):
        L = self.panel.lang
        self.titlebar.title_label.setText(L.get("ui.settings"))
        self.tl.setText(L.get("ui.settings"))
        self.ul.setText(L.get("ui.user_name"))
        self.pl.setText(L.get("ui.pet_name"))
        self.thl.setText(L.get("ui.theme"))
        self.ll.setText(L.get("ui.lang"))
        self.sb.setText(L.get("ui.save"))

        self.lang_ko_btn.setText("한국어")
        self.lang_en_btn.setText("English")

    def _on_theme_changed(self, theme_name: str):
        if theme_name and theme_name != self.panel.theme:
            self.panel.apply_theme(theme_name)

    def _update_icons(self):
        icon_dir = getattr(self.panel, "current_icon_dir", None)
        if not icon_dir:
            return

        sys_p = icon_dir / "ic_main.png"
        if sys_p.exists():
            self.titlebar.sys_icon.setPixmap(
                QPixmap(str(sys_p.resolve())).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

        close_p = icon_dir / "ic_close.png"
        if close_p.exists():
            self.titlebar.close_btn.setIcon(QIcon(str(close_p.resolve())))
            self.titlebar.close_btn.setIconSize(QSize(20, 20))

    def save(self):
        user_name = self.ui.toPlainText().strip()
        pet_name = self.pi.toPlainText().strip()
        lang_code = self._selected_lang

        if user_name:
            self.panel.user_name = user_name
        if pet_name:
            self.state.pet_name = pet_name

        if lang_code != self.panel.lang.lang_code:
            self.panel.lang.load_lang(lang_code)

            if self.panel.user_name in ["나", "Me"]:
                self.panel.user_name = self.panel.lang.get("user_name")

            if self.state.pet_name in ["라이미", "Raimi"]:
                self.state.pet_name = self.panel.lang.get("pet_name")

            self.panel.retranslate_ui()
            self.retranslate_ui()
            self.panel.reset_chat_log("ui.sys_ready")

        self.panel._sync_ui()
        self.close()