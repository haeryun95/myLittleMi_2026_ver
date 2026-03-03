"""
utils/json_utils.py - JSON 관련 유틸리티 (가구 카탈로그 포함)
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import BG_CATEGORIES, BG_DIR, FURNITURE_JSON_PATH
from utils.helpers import safe_read_json


def scan_bg_items_fallback() -> Dict[str, Dict[str, Path]]:
    items: Dict[str, Dict[str, Path]] = {}
    for cat in BG_CATEGORIES:
        folder = BG_DIR / cat
        m: Dict[str, Path] = {}
        if folder.exists():
            for p in sorted(folder.glob("*.png")):
                m[p.stem] = p
        items[cat] = m
    return items

def load_furniture_catalog() -> Dict[str, List[dict]]:
    raw = safe_read_json(FURNITURE_JSON_PATH)
    if isinstance(raw, dict) and raw:
        out: Dict[str, List[dict]] = {cat: [] for cat in BG_CATEGORIES}
        for cat in BG_CATEGORIES:
            arr = raw.get(cat, [])
            if not isinstance(arr, list):
                continue
            for it in arr:
                if not isinstance(it, dict):
                    continue

                iid = str(it.get("id", "")).strip()
                name = str(it.get("name", iid)).strip() or iid
                price = int(it.get("price", 0) or 0)
                file_rel = str(it.get("file", "")).replace("\\", "/").strip()

                # ✅ B안: wheel 애니 경로
                anim_dir = it.get("anim_dir")
                anim_dir_rel = None
                if anim_dir is not None:
                    anim_dir_rel = str(anim_dir).replace("\\", "/").strip() or None

                if not iid or not file_rel:
                    continue

                row = {"id": iid, "name": name, "price": price, "file": file_rel}
                # ✅ anim_dir이 있는 경우에만 추가(다른 카테고리도 확장 가능)
                if anim_dir_rel:
                    row["anim_dir"] = anim_dir_rel

                out[cat].append(row)
        return out

    scanned = scan_bg_items_fallback()
    out2: Dict[str, List[dict]] = {cat: [] for cat in BG_CATEGORIES}
    for cat in BG_CATEGORIES:
        for iid, p in scanned.get(cat, {}).items():
            base_price = {
                "wallpaper": 900, "wheel": 700, "house": 1200,
                "deco": 600, "flower": 500
            }.get(cat, 600)
            price = int(base_price + min(400, len(iid) * 10))
            rel = f"{cat}/{p.name}"
            out2[cat].append({"id": iid, "name": iid, "price": price, "file": rel})
    return out2

# def load_furniture_catalog() -> Dict[str, List[dict]]:
#     raw = safe_read_json(FURNITURE_JSON_PATH)
#     if isinstance(raw, dict) and raw:
#         out: Dict[str, List[dict]] = {cat: [] for cat in BG_CATEGORIES}
#         for cat in BG_CATEGORIES:
#             arr = raw.get(cat, [])
#             if not isinstance(arr, list):
#                 continue
#             for it in arr:
#                 if not isinstance(it, dict):
#                     continue
#                 iid = str(it.get("id", "")).strip()
#                 name = str(it.get("name", iid)).strip() or iid
#                 price = int(it.get("price", 0) or 0)
#                 file_rel = str(it.get("file", "")).replace("\\", "/").strip()
#                 if not iid or not file_rel:
#                     continue
#                 out[cat].append({"id": iid, "name": name, "price": price, "file": file_rel})
#         return out

#     scanned = scan_bg_items_fallback()
#     out2: Dict[str, List[dict]] = {cat: [] for cat in BG_CATEGORIES}
#     for cat in BG_CATEGORIES:
#         for iid, p in scanned.get(cat, {}).items():
#             base_price = {
#                 "wallpaper": 900, "wheel": 700, "house": 1200,
#                 "deco": 600, "flower": 500
#             }.get(cat, 600)
#             price = int(base_price + min(400, len(iid) * 10))
#             rel = f"{cat}/{p.name}"
#             out2[cat].append({"id": iid, "name": iid, "price": price, "file": rel})
#     return out2


def resolve_bg_path(file_rel: str) -> Path:
    return (BG_DIR / file_rel).resolve()


def get_catalog() -> Dict[str, List[dict]]:
    return load_furniture_catalog()


def item_name(items_db: dict, item_id: str) -> str:
    items = items_db.get("items") or {}
    if isinstance(items, list):
        for it in items:
            if it.get("id") == item_id:
                return it.get("name", item_id)
        return item_id
    return (items.get(item_id) or {}).get("name", item_id)


def item_rarity(items_db: dict, item_id: str) -> str:
    items = items_db.get("items") or {}
    if isinstance(items, list):
        for it in items:
            if it.get("id") == item_id:
                return str(it.get("rarity", "common")).lower()
        return "common"
    return str((items.get(item_id) or {}).get("rarity", "common")).lower()
