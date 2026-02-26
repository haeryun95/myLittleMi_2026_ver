"""
windows/job_window.py - 알바 창 (장소 선택 / 텍스트RPG / 드랍 / 판매)
"""
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSpinBox, QStackedWidget,
    QTextEdit, QVBoxLayout, QWidget, QFrame,
)

from config import (
    BASE_DIR, ITEMS_JSON_PATH, JOBS_JSON_PATH,
    PINK, SCRIPT_LINES_DEFAULT, SCRIPT_LINES_RANGE, STAT_LABELS,
)
from state import PetState, clamp
from utils.helpers import load_json_file


class JobWindow(QWidget):
    def __init__(
        self,
        state: PetState,
        app_icon=None,
        jobs_json_path: Path = JOBS_JSON_PATH,
        items_json_path: Path = ITEMS_JSON_PATH,
        close_on_exhaust: bool = True,
        script_random_lines: bool = True,
    ):
        super().__init__()
        self.state = state
        self.jobs_json_path = Path(jobs_json_path)
        self.items_json_path = Path(items_json_path)
        self.close_on_exhaust = bool(close_on_exhaust)
        self.script_random_lines = bool(script_random_lines)

        self.setWindowTitle("알바")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        if app_icon:
            self.setWindowIcon(app_icon)

        self.jobs_data: Dict[str, Any] = {}
        self.items_db: Dict[str, Any] = {}
        self.places: List[Dict[str, Any]] = []

        self.current_place: Optional[Dict[str, Any]] = None
        self.script_lines: List[str] = []
        self.script_i = 0
        self.running = False

        self.timer = QTimer(self)
        self.timer.setInterval(900)
        self.timer.timeout.connect(self._tick_script)

        self.stack = QStackedWidget()
        self._stats_label_sets: List[Dict[str, QLabel]] = []
        self._money_labels: List[QLabel] = []
        self._need_labels: List[Dict[str, QLabel]] = []

        # ===== page_select =====
        self.page_select = QWidget()
        v1 = QVBoxLayout(self.page_select)
        v1.setSpacing(10)
        v1.addWidget(self._build_stats_bar())

        self.place_list = QListWidget()
        self.place_list.setViewMode(QListWidget.IconMode)
        self.place_list.setResizeMode(QListWidget.Adjust)
        self.place_list.setMovement(QListWidget.Static)
        self.place_list.setWrapping(True)
        self.place_list.setIconSize(QSize(64, 64))
        self.place_list.setGridSize(QSize(190, 110))
        self.place_list.setSpacing(8)
        self.place_list.itemClicked.connect(self._on_click_place)
        v1.addWidget(self.place_list, 1)

        row1 = QHBoxLayout()
        self.btn_open_sell = QPushButton("인벤토리 / 판매")
        self.btn_open_sell.clicked.connect(self._open_sell_page)
        row1.addWidget(self.btn_open_sell)
        self.btn_reload = QPushButton("새로고침")
        self.btn_reload.clicked.connect(self._reload_all_ui)
        row1.addWidget(self.btn_reload)
        row1.addStretch(1)
        v1.addLayout(row1)

        self.hint = QLabel("장소를 선택해줘.")
        self.hint.setObjectName("HintLabel")
        v1.addWidget(self.hint)

        # ===== page_run =====
        self.page_run = QWidget()
        v2 = QVBoxLayout(self.page_run)
        v2.setSpacing(10)
        v2.addWidget(self._build_stats_bar())

        self.run_title = QLabel("")
        self.run_title.setStyleSheet("font-size: 16px; font-weight: 900;")
        v2.addWidget(self.run_title)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        v2.addWidget(self.log, 1)

        row2 = QHBoxLayout()
        self.btn_stop = QPushButton("중단")
        self.btn_stop.clicked.connect(self._stop_and_back)
        row2.addWidget(self.btn_stop)
        self.btn_skip = QPushButton("빠르게 끝내기")
        self.btn_skip.clicked.connect(self._finish_immediately)
        row2.addWidget(self.btn_skip)
        self.btn_back = QPushButton("목록으로")
        self.btn_back.clicked.connect(self._stop_and_back)
        row2.addWidget(self.btn_back)
        v2.addLayout(row2)

        self.result = QLabel("")
        self.result.setObjectName("HintLabel")
        v2.addWidget(self.result)

        # ===== page_sell =====
        self.page_sell = QWidget()
        v3 = QVBoxLayout(self.page_sell)
        v3.setSpacing(10)
        v3.addWidget(self._build_stats_bar())

        top = QHBoxLayout()
        t = QLabel("🧺 인벤토리 판매")
        t.setStyleSheet("font-size: 16px; font-weight: 900;")
        top.addWidget(t)
        self.btn_back_to_jobs = QPushButton("알바 목록")
        self.btn_back_to_jobs.clicked.connect(lambda: self.stack.setCurrentWidget(self.page_select))
        top.addWidget(self.btn_back_to_jobs)
        v3.addLayout(top)

        self.inv_list = QListWidget()
        self.inv_list.setSpacing(8)
        self.inv_list.itemClicked.connect(self._on_click_inv_item)
        v3.addWidget(self.inv_list, 1)

        sell_row = QHBoxLayout()
        self.sell_hint = QLabel("판매할 아이템을 선택해줘.")
        self.sell_hint.setObjectName("HintLabel")
        sell_row.addWidget(self.sell_hint, 1)
        self.sell_qty = QSpinBox()
        self.sell_qty.setRange(1, 9999)
        self.sell_qty.setValue(1)
        self.sell_qty.valueChanged.connect(self._update_sell_preview)
        sell_row.addWidget(QLabel("수량:"))
        sell_row.addWidget(self.sell_qty)
        self.btn_sell = QPushButton("판매")
        self.btn_sell.clicked.connect(self._sell_selected)
        sell_row.addWidget(self.btn_sell)
        v3.addLayout(sell_row)

        self.sell_preview = QLabel("총 판매 예상액: 0원")
        self.sell_preview.setObjectName("HintLabel")
        v3.addWidget(self.sell_preview)

        self.sell_result = QLabel("")
        self.sell_result.setObjectName("HintLabel")
        v3.addWidget(self.sell_result)

        self.stack.addWidget(self.page_select)
        self.stack.addWidget(self.page_run)
        self.stack.addWidget(self.page_sell)

        lay = QVBoxLayout(self)
        lay.addWidget(self.stack)

        self._reload_all_ui()
        self.stack.setCurrentWidget(self.page_select)

        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._refresh_stats_ui)
        self.ui_timer.start(400)

    # -------------------------
    # 헬퍼
    # -------------------------
    def _norm_key(self, k: str) -> str:
        return "energy" if k == "stamina" else k

    def _get_need_stats(self) -> Dict[str, int]:
        return {
            "energy": int(getattr(self.state, "energy", 0)),
            "max_energy": int(getattr(self.state, "max_energy", 0)),
            "hunger": int(getattr(self.state, "hunger", 0)),
            "fun_need": int(getattr(self.state, "fun", 0)),
            "mood": int(getattr(self.state, "mood", 0)),
        }

    def _item_info(self, item_id: str) -> Dict[str, Any]:
        return ((self.items_db.get("items") or {}).get(item_id) or {})

    def _item_name(self, item_id: str) -> str:
        return self._item_info(item_id).get("name") or item_id

    def _item_effects(self, item_id: str) -> Dict[str, int]:
        return self._item_info(item_id).get("effects") or {}

    def _item_sell_price(self, item_id: str) -> int:
        return int(self._item_info(item_id).get("sell_price") or 0)

    def _item_rarity(self, item_id: str) -> str:
        return str(self._item_info(item_id).get("rarity") or "common").lower()

    def _rarity_fx(self, rarity: str) -> str:
        r = (rarity or "common").lower()
        if r == "legendary": return "🌈✨ 레전더리 획득!!"
        if r == "epic":      return "💜✨ 에픽 획득!"
        if r == "rare":      return "💛✨ 레어 획득!"
        if r == "uncommon":  return "💚 희귀한 아이템 획득!"
        return ""

    def _calc_item_bonus(self, inventory: Dict[str, int]) -> Dict[str, int]:
        bonus: Dict[str, int] = {k: 0 for k in STAT_LABELS.keys()}
        for item_id, count in (inventory or {}).items():
            count = int(count)
            if count <= 0:
                continue
            eff = self._item_effects(item_id)
            for stat, v in (eff or {}).items():
                stat = self._norm_key(stat)
                if stat in bonus:
                    bonus[stat] = int(bonus.get(stat, 0)) + int(v) * count
        return bonus

    def _merged_stats(self, base: Dict[str, int], bonus: Dict[str, int]) -> Dict[str, int]:
        out = dict(base or {})
        for k, v in (bonus or {}).items():
            out[k] = int(out.get(k, 0)) + int(v)
        out["energy"] = int(getattr(self.state, "energy", 0))
        return out

    def _meets_requirements(self, total_stats: Dict[str, int], req: Dict[str, int]) -> Tuple[bool, List[str]]:
        lacks: List[str] = []
        for stat, need in (req or {}).items():
            stat = self._norm_key(stat)
            cur = int(total_stats.get(stat, 0))
            if cur < int(need):
                if stat == "energy":
                    lacks.append(f"에너지 {need} 필요(현재 {cur})")
                else:
                    lacks.append(f"{STAT_LABELS.get(stat, stat)} {need} 필요(현재 {cur})")
        return (len(lacks) == 0), lacks

    def _resolve_drop_table(self, place: Dict[str, Any]) -> List[Dict[str, Any]]:
        if place.get("drop_table"):
            return place.get("drop_table") or []
        cat_id = place.get("category")
        cats = self.jobs_data.get("categories") or {}
        cat = cats.get(cat_id) or {}
        return cat.get("drop_table") or []

    def _roll_items_from_table(self, drop_table: List[Dict[str, Any]]) -> Dict[str, int]:
        got: Dict[str, int] = {}
        for it in (drop_table or []):
            item_id = it.get("id")
            if not item_id:
                continue
            chance = float(it.get("chance", 0))
            if random.random() <= chance:
                mn = int(it.get("min", 1))
                mx = int(it.get("max", mn))
                qty = random.randint(mn, mx)
                got[item_id] = got.get(item_id, 0) + qty
        return got

    def _roll_money(self, range_pair) -> int:
        if isinstance(range_pair, list) and len(range_pair) == 2:
            return random.randint(int(range_pair[0]), int(range_pair[1]))
        return int(range_pair or 0)

    # -------------------------
    # stats bar
    # -------------------------
    def _build_stats_bar(self) -> QFrame:
        wrap = QFrame()
        wrap.setFrameShape(QFrame.StyledPanel)
        row = QHBoxLayout(wrap)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(12)

        money = QLabel("")
        money.setStyleSheet("font-weight: 900;")
        row.addWidget(money)
        self._money_labels.append(money)

        need_labels: Dict[str, QLabel] = {}
        for key in ["energy", "mood", "fun_need", "hunger"]:
            lb = QLabel()
            lb.setMinimumWidth(110)
            need_labels[key] = lb
            row.addWidget(lb)
        self._need_labels.append(need_labels)

        labels: Dict[str, QLabel] = {}
        for k in STAT_LABELS.keys():
            lb = QLabel()
            lb.setTextFormat(Qt.RichText)
            lb.setMinimumWidth(120)
            labels[k] = lb
            row.addWidget(lb)
        self._stats_label_sets.append(labels)
        row.addStretch(1)
        return wrap

    def _refresh_stats_ui(self):
        for ml in self._money_labels:
            ml.setText(f"💰 {int(getattr(self.state, 'money', 0))}원")

        need = self._get_need_stats()
        for d in self._need_labels:
            d["energy"].setText(f"에너지: {need['energy']}/{need['max_energy']}")
            d["mood"].setText(f"기분: {need['mood']}")
            d["fun_need"].setText(f"재미: {need['fun_need']}")
            d["hunger"].setText(f"허기: {need['hunger']}")

        base = getattr(self.state, "stats", {k: 0 for k in STAT_LABELS.keys()})
        inv = getattr(self.state, "inventory", {})
        bonus = self._calc_item_bonus(inv)

        for labels in self._stats_label_sets:
            for key, lb in labels.items():
                b = int(base.get(key, 0))
                plus = int(bonus.get(key, 0))
                if plus > 0:
                    lb.setText(f"{STAT_LABELS[key]}: {b} <span style='color:{PINK}; font-weight:900'>+{plus}</span>")
                else:
                    lb.setText(f"{STAT_LABELS[key]}: {b}")

    # -------------------------
    # data load
    # -------------------------
    def _load_data(self):
        missing = []
        if not self.jobs_json_path.exists():
            missing.append(f"❌ JSON 없음: {self.jobs_json_path}")
        if not self.items_json_path.exists():
            missing.append(f"❌ JSON 없음: {self.items_json_path}")
        if missing:
            self.hint.setText("\n".join(missing))

        self.jobs_data = load_json_file(self.jobs_json_path, {"categories": {}, "places": []})
        self.items_db = load_json_file(self.items_json_path, {"items": {}})
        self.places = self.jobs_data.get("places", []) or []

        if not hasattr(self.state, "stats") or not isinstance(self.state.stats, dict):
            self.state.stats = {k: 0 for k in STAT_LABELS.keys()}
        for k in STAT_LABELS.keys():
            self.state.stats.setdefault(k, 0)

        if not hasattr(self.state, "inventory") or not isinstance(self.state.inventory, dict):
            self.state.inventory = {}

    def _reload_all_ui(self):
        self._load_data()
        self._refresh_stats_ui()
        self._reload_places()
        self._refresh_inventory_ui()

    # -------------------------
    # places list
    # -------------------------
    def _reload_places(self):
        self.place_list.clear()

        if not self.places:
            it = QListWidgetItem("알바 장소가 없어… (jobs.json places 확인)")
            it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
            self.place_list.addItem(it)
            self.place_list.setIconSize(QSize(64, 64))
            return

        base = self.state.stats
        bonus = self._calc_item_bonus(self.state.inventory)
        total = self._merged_stats(base, bonus)

        for p in self.places:
            name = p.get("name", "이름없음")
            req = p.get("requirements", {}) or {}
            ok, _ = self._meets_requirements(total, req)

            it = QListWidgetItem(name)
            it.setData(Qt.UserRole, p)

            thumb_path = p.get("thumb")
            if thumb_path:
                from PySide6.QtGui import QPixmap
                abs_path = (BASE_DIR / str(thumb_path)).resolve() if not os.path.isabs(str(thumb_path)) else Path(str(thumb_path))
                pm = QPixmap(str(abs_path))
                if not pm.isNull():
                    it.setIcon(QIcon(pm))

            money_rng = p.get("reward_money", [0, 0])
            if isinstance(money_rng, list) and len(money_rng) == 2:
                money_txt = f"{money_rng[0]}~{money_rng[1]}원"
            else:
                money_txt = f"{money_rng}원"

            pretty_req = []
            for k, v in req.items():
                k2 = self._norm_key(k)
                if k2 == "energy":
                    pretty_req.append(f"에너지 {v}")
                else:
                    pretty_req.append(f"{STAT_LABELS.get(k2, k2)} {v}")
            req_txt = ", ".join(pretty_req) or "없음"

            drop_table = self._resolve_drop_table(p)
            preview = []
            for d in drop_table[:3]:
                did = d.get("id")
                if not did:
                    continue
                ch = float(d.get("chance", 0)) * 100
                preview.append(f"{self._item_name(did)}({ch:.1f}%)")
            drop_txt = ", ".join(preview) + ("..." if len(drop_table) > 3 else "")
            if not drop_txt:
                drop_txt = "없음"

            tip = f"요구: {req_txt}\n보상: {money_txt}\n드랍: {drop_txt}"
            if not ok:
                tip += "\n🔒 잠김"
            it.setToolTip(tip)

            if not ok:
                it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
                it.setForeground(Qt.gray)

            self.place_list.addItem(it)

        self.place_list.setIconSize(QSize(64, 64))

    def _on_click_place(self, item: QListWidgetItem):
        place = item.data(Qt.UserRole)
        if not isinstance(place, dict):
            return

        base = self.state.stats
        bonus = self._calc_item_bonus(self.state.inventory)
        total = self._merged_stats(base, bonus)
        ok, lacks = self._meets_requirements(total, place.get("requirements", {}) or {})
        if not ok:
            QMessageBox.information(self, "조건 부족", "갈 수 없어!\n" + "\n".join(lacks))
            return

        self._start_job(place)

    # -------------------------
    # run
    # -------------------------
    def _start_job(self, place: Dict[str, Any]):
        self.current_place = place
        lines = list(place.get("script", []) or [])
        if not lines:
            lines = ["일을 시작했다.", "열심히 일하는 중…", "퇴근했다!"]

        random.shuffle(lines)
        n = random.randint(*SCRIPT_LINES_RANGE) if self.script_random_lines else SCRIPT_LINES_DEFAULT
        self.script_lines = lines[:n]
        self.script_i = 0
        self.running = True

        self.run_title.setText(f"📍 {place.get('name','')}")
        self.log.clear()
        self.result.setText("")

        self._refresh_stats_ui()
        self.stack.setCurrentWidget(self.page_run)
        self.timer.stop()
        self.timer.start()

    def _tick_script(self):
        if not self.running or not self.current_place:
            self.timer.stop()
            return

        if self.script_i < len(self.script_lines):
            self.log.append(self.script_lines[self.script_i])
            self.script_i += 1
            return

        self.timer.stop()
        self.running = False
        self._apply_rewards(self.current_place)

    def _finish_immediately(self):
        if not self.current_place:
            return
        while self.script_i < len(self.script_lines):
            self.log.append(self.script_lines[self.script_i])
            self.script_i += 1
        self.timer.stop()
        self.running = False
        self._apply_rewards(self.current_place)

    def _stop_and_back(self):
        self.timer.stop()
        self.running = False
        self.current_place = None
        self.stack.setCurrentWidget(self.page_select)
        self._refresh_stats_ui()
        self._reload_places()

    def _apply_rewards(self, place: Dict[str, Any]):
        delta = dict(place.get("delta", {}) or {})
        if "stamina" in delta and "energy" not in delta:
            delta["energy"] = delta["stamina"]

        energy_cost = float(delta.get("energy", 0))
        after_energy = float(getattr(self.state, "energy", 0.0)) + energy_cost

        if after_energy < 0:
            QMessageBox.warning(self, "탈진!", "에너지가 바닥나서 쓰러졌어…\n알바를 중단하고 돌아갈게!")
            self.state.energy = 0.0
            self.result.setText("에너지 부족으로 알바 실패… (보상 없음)")
            self._stop_and_back()
            if self.close_on_exhaust:
                self.close()
            return

        money = self._roll_money(place.get("reward_money", [0, 0]))
        self.state.money += int(money)

        drop_table = self._resolve_drop_table(place)
        got_items = self._roll_items_from_table(drop_table)

        for item_id, qty in got_items.items():
            self.state.inventory[item_id] = int(self.state.inventory.get(item_id, 0)) + int(qty)

        for item_id, qty in got_items.items():
            fx = self._rarity_fx(self._item_rarity(item_id))
            if fx:
                self.log.append(f"{fx}  {self._item_name(item_id)} x{qty}")

        for k, v in delta.items():
            k2 = self._norm_key(k)
            if k2 == "energy":
                self.state.energy = max(0.0, min(float(self.state.max_energy), float(self.state.energy) + float(v)))
            elif k2 == "mood":
                self.state.mood = max(0.0, min(100.0, float(self.state.mood) + float(v)))
            elif k2 == "hunger":
                self.state.hunger = max(0.0, min(100.0, float(self.state.hunger) + float(v)))
            elif k2 == "fun":
                self.state.fun = max(0.0, min(100.0, float(self.state.fun) + float(v)))
            elif k2 in self.state.stats:
                self.state.stats[k2] = int(self.state.stats.get(k2, 0)) + int(v)

        if got_items:
            item_txt = ", ".join([f"{self._item_name(k)} x{v}" for k, v in got_items.items()])
        else:
            item_txt = "없음"

        self.result.setText(f"알바 완료! (+{money}원) / 아이템: {item_txt}")
        self._refresh_stats_ui()
        self._reload_places()
        self._refresh_inventory_ui()

    # -------------------------
    # sell
    # -------------------------
    def _open_sell_page(self):
        self._refresh_stats_ui()
        self._refresh_inventory_ui()
        self.sell_result.setText("")
        self.sell_preview.setText("총 판매 예상액: 0원")
        self.stack.setCurrentWidget(self.page_sell)

    def _refresh_inventory_ui(self):
        self.inv_list.clear()
        inv = self.state.inventory or {}
        for item_id, qty in inv.items():
            qty = int(qty)
            if qty <= 0:
                continue
            name = self._item_name(item_id)
            price = self._item_sell_price(item_id)
            rarity = self._item_rarity(item_id)
            it = QListWidgetItem(f"{name}  x{qty}   (판매가 {price}원)")
            it.setData(Qt.UserRole, {"id": item_id, "qty": qty})
            if rarity in ("rare", "epic", "legendary"):
                it.setForeground(Qt.darkYellow)
            it.setToolTip(f"희귀도: {rarity}\n판매가: {price}원")
            self.inv_list.addItem(it)
        self.inv_list.setIconSize(QSize(40, 40))

    def _on_click_inv_item(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole) or {}
        item_id = data.get("id")
        have = int(data.get("qty") or 1)
        self.sell_qty.setRange(1, max(1, have))
        self.sell_qty.setValue(1)
        name = self._item_name(item_id)
        price = self._item_sell_price(item_id)
        self.sell_hint.setText(f"선택: {name} (1개 {price}원)")
        self._update_sell_preview()

    def _update_sell_preview(self):
        item = self.inv_list.currentItem()
        if not item:
            self.sell_preview.setText("총 판매 예상액: 0원")
            return
        data = item.data(Qt.UserRole) or {}
        item_id = data.get("id")
        have = int(data.get("qty") or 0)
        if not item_id or have <= 0:
            self.sell_preview.setText("총 판매 예상액: 0원")
            return
        qty = min(int(self.sell_qty.value()), have)
        price = self._item_sell_price(item_id)
        total = max(0, price * qty)
        self.sell_preview.setText(f"총 판매 예상액: {total}원")

    def _sell_selected(self):
        sel = self.inv_list.currentItem()
        if not sel:
            QMessageBox.information(self, "판매", "판매할 아이템을 선택해줘.")
            return
        data = sel.data(Qt.UserRole) or {}
        item_id = data.get("id")
        have = int(data.get("qty") or 0)
        qty = min(int(self.sell_qty.value()), have)
        if not item_id or qty <= 0:
            return
        price = self._item_sell_price(item_id)
        if price <= 0:
            QMessageBox.information(self, "판매", "이 아이템은 판매할 수 없어.")
            return
        total = price * qty
        self.state.inventory[item_id] = max(0, int(self.state.inventory.get(item_id, 0)) - qty)
        self.state.money += int(total)
        name = self._item_name(item_id)
        self.sell_result.setText(f"판매 완료! {name} x{qty} → +{total}원")
        self._refresh_stats_ui()
        self._refresh_inventory_ui()
        self._reload_places()
        self.sell_preview.setText("총 판매 예상액: 0원")
