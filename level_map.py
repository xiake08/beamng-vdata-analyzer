# -*- coding: utf-8 -*-
"""把游戏 level 里的真实地形数据拼成"真实地图"底图，给 3D 赛道页用。

数据来源（都在游戏目录 content/levels/<level>.zip 里，不用解压）：
  <level>/export/theTerrain_heightmap.png    16 位地形高度图（2048²）
  <level>/export/theTerrain_layerMap_*.png   各材质覆盖权重（草地/泥土/沥青/森林…）
  <level>/main/**/items.level.json           TerrainBlock 参数（position / maxHeight /
                                             squareSize / minimapImage）

做法：用材质层 + 调色板拼出真实地表颜色，再乘山体阴影（西北光），
裁出路线所在范围，编码成 WebP data URI 交给前端当底图贴在地面平面上。
（高度图/材质层只在第一次读，之后缓存；每次换数据只做裁剪+上色+编码。）
"""

import base64
import io
import os
import re
import zipfile

import numpy as np
from PIL import Image

# 材质 → 颜色（按 layerMap 文件名里的材质名）
MAT_COLORS = {
    "grass": (122, 158, 92),
    "dirt": (152, 126, 94),
    "grass2": (134, 168, 100),
    "beachsand": (226, 210, 166),
    "dirt_grass": (146, 158, 108),
    "rock": (132, 132, 126),
    "mud": (112, 98, 78),
    "asphalt": (92, 94, 98),
    "forest": (74, 108, 70),
    "forest_floor": (100, 114, 80),
}

CACHE = {}          # level -> {"zip": path, "params": {...}, "height": np.uint16, "layers": {...}, "alpha": np}
_MAX_PX = 1024      # 输出图片最长边


def _game_dir():
    try:
        import beamng_data as T
        exe = getattr(T, "GAME_EXE", "") or ""
        if exe and os.path.isfile(exe):
            return os.path.dirname(os.path.dirname(exe))
        if exe:
            return os.path.dirname(os.path.dirname(exe))
    except Exception:                   # noqa: BLE001
        pass
    return ""


def _find_level_zip(level):
    game = _game_dir()
    if not game:
        return None
    levels = os.path.join(game, "content", "levels")
    if not os.path.isdir(levels):
        return None
    want = (level or "").strip().lower()
    try:
        names = os.listdir(levels)
    except OSError:
        return None
    for n in names:
        if n.lower() == want + ".zip":
            return os.path.join(levels, n)
    for n in names:
        if n.lower() == want:
            return os.path.join(levels, n)     # 解压过的 level 目录
    return None


def _parse_params(z, level):
    """从 items.level.json 里抠 TerrainBlock 参数。"""
    pref = "levels/%s/" % level.lower()
    for name in z.namelist():
        low = name.lower()
        if not low.endswith(".level.json") or not low.startswith(pref.replace("\\", "/")):
            continue
        try:
            raw = z.read(name).decode("utf-8", "ignore")
        except Exception:               # noqa: BLE001
            continue
        m = re.search(r'"class"\s*:\s*"TerrainBlock"', raw)
        if not m:
            continue
        start = raw.rfind("{", 0, m.start())
        if start < 0:
            continue
        depth = 0
        end = start
        for i in range(start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        obj = raw[start:end]

        def num(key, default=None):
            mm = re.search(r'"%s"\s*:\s*([-\d.eE+]+)' % key, obj)
            return float(mm.group(1)) if mm else default

        pos = re.search(r'"position"\s*:\s*\[\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)'
                        r'\s*,\s*([-\d.eE+]+)\s*\]', obj)
        params = {
            "x0": float(pos.group(1)) if pos else None,
            "y0": float(pos.group(2)) if pos else None,
            "z0": float(pos.group(3)) if pos else 0.0,
            "max_height": num("maxHeight", 100.0),
            "square_size": num("squareSize", 1.0),
            "base_tex": num("baseTexSize", 2048.0),
        }
        if params["x0"] is None:
            return None
        return params
    return None


def _load_level(level):
    """读并缓存 level 的高度图 / 材质层 / minimap alpha。"""
    key = (level or "").strip().lower()
    if key in CACHE:
        return CACHE[key]
    path = _find_level_zip(key)
    if not path:
        CACHE[key] = None
        return None
    try:
        z = zipfile.ZipFile(path)
    except Exception:                   # noqa: BLE001
        CACHE[key] = None
        return None
    params = _parse_params(z, key)
    if not params:
        CACHE[key] = None
        return None
    names = z.namelist()
    hm_name = None
    layer_names = []
    mm_name = None
    for n in names:
        low = n.lower()
        if low.endswith("/export/theterrain_heightmap.png"):
            hm_name = n
        elif "/export/theterrain_layermap_" in low and low.endswith(".png"):
            layer_names.append(n)
        elif low.endswith("_minimap.png") or low.endswith("/minimap.png"):
            mm_name = mm_name or n
    if not hm_name:
        CACHE[key] = None
        return None
    try:
        height = np.array(Image.open(io.BytesIO(z.read(hm_name))))
        if height.ndim != 2:
            height = height[..., 0]
    except Exception:                   # noqa: BLE001
        CACHE[key] = None
        return None
    layers = {}
    for n in layer_names:
        fn = os.path.basename(n)
        try:
            mat = fn.split("_layerMap_")[1].split("_", 1)[1][:-4].lower()
        except Exception:               # noqa: BLE001
            continue
        try:
            im = Image.open(io.BytesIO(z.read(n))).convert("L")
            a = np.asarray(im, dtype=np.uint8)
            if a.shape == height.shape:
                layers[mat] = a
        except Exception:               # noqa: BLE001
            continue
    alpha = None
    if mm_name:
        try:
            mm = Image.open(io.BytesIO(z.read(mm_name))).convert("RGBA")
            alpha = np.asarray(mm.getchannel("A"), dtype=np.uint8)
            if alpha.shape != height.shape:
                alpha = None
        except Exception:               # noqa: BLE001
            alpha = None
    z.close()
    n_px = height.shape[1]
    size_m = n_px * float(params["square_size"])
    data = {
        "path": path,
        "params": params,
        "height": height,
        "layers": layers,
        "alpha": alpha,
        "n_px": n_px,
        "size_m": size_m,
    }
    CACHE[key] = data
    return data


def _encode(img):
    for fmt, kw in (("WEBP", {"quality": 82, "method": 4}), ("JPEG", {"quality": 86}), ("PNG", {})):
        try:
            buf = io.BytesIO()
            img.save(buf, fmt, **kw)
            mime = {"WEBP": "image/webp", "JPEG": "image/jpeg", "PNG": "image/png"}[fmt]
            return "data:%s;base64,%s" % (mime, base64.b64encode(buf.getvalue()).decode("ascii"))
        except Exception:               # noqa: BLE001
            continue
    return None


def build_map_for_route(level, x0, x1, y0, y1, max_px=_MAX_PX):
    """裁出 [x0,x1]×[y0,y1] 范围的真实地图，返回 {img, x0,x1,y0,y1,w,h,level} 或 None。"""
    data = _load_level(level)
    if not data:
        return None
    p = data["params"]
    n = data["n_px"]
    world_x0, world_y0 = p["x0"], p["y0"]
    size = data["size_m"]
    world_x1, world_y1 = world_x0 + size, world_y0 + size
    # 裁剪范围夹到地形范围内
    x0 = max(x0, world_x0)
    x1 = min(x1, world_x1)
    y0 = max(y0, world_y0)
    y1 = min(y1, world_y1)
    if x1 - x0 < 20 or y1 - y0 < 20:
        return None
    # 世界坐标 → 像素（图片第 0 行 = 世界最大 y）
    c0 = int(round((x0 - world_x0) / size * (n - 1)))
    c1 = int(round((x1 - world_x0) / size * (n - 1))) + 1
    r0 = int(round((world_y1 - y1) / size * (n - 1)))
    r1 = int(round((world_y1 - y0) / size * (n - 1))) + 1
    c0 = max(0, min(n - 2, c0))
    c1 = max(c0 + 2, min(n, c1))
    r0 = max(0, min(n - 2, r0))
    r1 = max(r0 + 2, min(n, r1))
    # 实际裁剪对应的世界范围（用像素边界反算，避免和图片错位）
    real_x0 = world_x0 + c0 / (n - 1) * size
    real_x1 = world_x0 + (c1 - 1) / (n - 1) * size
    real_y1 = world_y1 - r0 / (n - 1) * size
    real_y0 = world_y1 - (r1 - 1) / (n - 1) * size

    h = data["height"][r0:r1, c0:c1].astype(np.float32) / 65535.0
    # 只取真的覆盖到这块区域的材质层（beachsand/rock 之类经常整块是 0）
    mats, weights = [], []
    for mat, arr in data["layers"].items():
        w = arr[r0:r1, c0:c1]
        if w.size and int(w.max()) > 12:
            mats.append(mat)
            weights.append(w.astype(np.float32) / 255.0)
    if weights:
        wstack = np.stack(weights, axis=0)                     # (L,H,W)
        pal = np.array([MAT_COLORS.get(m, (128, 128, 128)) for m in mats],
                       dtype=np.float32)                        # (L,3)
        col = np.tensordot(wstack, pal, axes=([0], [0]))        # (H,W,3)
        wsum = wstack.sum(axis=0)
    else:
        col = np.zeros(h.shape + (3,), dtype=np.float32)
        wsum = np.zeros(h.shape, dtype=np.float32)
    t = np.clip(h, 0, 1)
    base = np.stack([150 + 60 * t, 168 + 30 * t, 120 + 30 * t], axis=-1)
    col = col + base * np.clip(1.0 - wsum, 0, 1)[..., None]
    col = np.clip(col, 0, 255)

    # 山体阴影：西北光，按真实米制坡度算（半分辨率算再放大，快 4 倍且更柔和）
    if h.shape[0] > 4 and h.shape[1] > 4:
        hh = h[::2, ::2]
        gy, gx = np.gradient(hh * float(p["max_height"]))
        step = float(p["square_size"]) * 2.0
        gx = gx / max(step, 1e-6)
        gy = gy / max(step, 1e-6)
        shade_s = np.clip(0.93 + (-gx * 0.55 + gy * 0.35), 0.72, 1.18)
        sh_img = Image.fromarray((shade_s * 255).clip(0, 255).astype(np.uint8), "L")
        sh_img = sh_img.resize((h.shape[1], h.shape[0]), Image.BILINEAR)
        shade = np.asarray(sh_img, dtype=np.float32) / 255.0
        col = np.clip(col * shade[..., None], 0, 255)

    # 提亮 + 轻微提饱和（minimap 那张 alpha 是等高线斜纹，叠上去反而显脏，不用它）
    col = col * 0.86 + 255.0 * 0.14
    gray = col.mean(axis=2, keepdims=True)
    col = np.clip(gray + (col - gray) * 1.18, 0, 255)
    img = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8), "RGB")

    # 缩到最长边 max_px
    iw, ih = img.size
    scale = min(1.0, float(max_px) / max(iw, ih))
    if scale < 1.0:
        img = img.resize((max(2, int(round(iw * scale))), max(2, int(round(ih * scale)))),
                         Image.LANCZOS)
    uri = _encode(img)
    if not uri:
        return None
    return {
        "img": uri,
        "x0": round(real_x0, 2), "x1": round(real_x1, 2),
        "y0": round(real_y0, 2), "y1": round(real_y1, 2),
        "w": img.size[0], "h": img.size[1],
        "level": level,
    }


# ══════════════════════════════════════════════════════════════════════
# 用户导入的游戏地图截图（Esc→地图 俯视图）+ 手动校准
#   图片存 project/mapshots/<level>.webp，校准范围存 config.json 的 mapshots 里
# ══════════════════════════════════════════════════════════════════════
SHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mapshots")


def _safe_key(level):
    return re.sub(r"[^\w\-]+", "_", (level or "unknown").strip().lower()) or "unknown"


def _cfg_path():
    try:
        import beamng_data as T
        return getattr(T, "CFG_FILE", "config.json")
    except Exception:                   # noqa: BLE001
        return "config.json"


def _read_cfg():
    try:
        import json
        with open(_cfg_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:                   # noqa: BLE001
        return {}


def _write_cfg(cfg):
    import json
    p = _cfg_path()
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)


def terrain_bounds(level):
    """该地图地形方块的世界范围 (x0, y0, x1, y1)，用作截图默认校准。"""
    data = _load_level(level)
    if not data:
        return None
    p = data["params"]
    size = data["size_m"]
    return [round(p["x0"], 1), round(p["y0"], 1),
            round(p["x0"] + size, 1), round(p["y0"] + size, 1)]


def load_user_shot(level):
    """读用户导入并校准过的地图截图；没有就返回 None。"""
    key = _safe_key(level)
    shot = os.path.join(SHOT_DIR, key + ".webp")
    cfg = _read_cfg()
    calib = ((cfg.get("mapshots") or {}).get(key) or {})
    if not os.path.isfile(shot) or not calib:
        return None
    try:
        from PIL import Image
        img = Image.open(shot)
        w, h = img.size
        with open(shot, "rb") as f:
            import base64
            uri = "data:image/webp;base64," + base64.b64encode(f.read()).decode("ascii")
        return {
            "img": uri,
            "x0": float(calib["x0"]), "x1": float(calib["x1"]),
            "y0": float(calib["y0"]), "y1": float(calib["y1"]),
            "w": w, "h": h, "level": level, "custom": True,
        }
    except Exception:                   # noqa: BLE001
        return None


def save_user_shot(level, img_bytes, x0, y0, x1, y1):
    """保存导入的地图截图（webp）并写入校准范围。"""
    key = _safe_key(level)
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, key + ".webp")
    from PIL import Image
    img = Image.open(io.BytesIO(img_bytes))
    img = img.convert("RGB")
    if max(img.size) > 2000:
        sc = 2000.0 / max(img.size)
        img = img.resize((max(2, int(img.size[0] * sc)), max(2, int(img.size[1] * sc))),
                         Image.LANCZOS)
    img.save(path, "WEBP", quality=86, method=4)
    cfg = _read_cfg()
    shots = cfg.get("mapshots") or {}
    shots[key] = {"x0": round(float(x0), 2), "y0": round(float(y0), 2),
                  "x1": round(float(x1), 2), "y1": round(float(y1), 2),
                  "w": img.size[0], "h": img.size[1]}
    cfg["mapshots"] = shots
    _write_cfg(cfg)
    return {"path": path, "w": img.size[0], "h": img.size[1]}


def set_calibration(level, x0, y0, x1, y1):
    """只更新校准范围（截图已经在导入时存好了）。"""
    key = _safe_key(level)
    shot = os.path.join(SHOT_DIR, key + ".webp")
    if not os.path.isfile(shot):
        return False
    cfg = _read_cfg()
    shots = cfg.get("mapshots") or {}
    cur = shots.get(key) or {}
    shots[key] = {"x0": round(float(x0), 2), "y0": round(float(y0), 2),
                  "x1": round(float(x1), 2), "y1": round(float(y1), 2),
                  "w": cur.get("w"), "h": cur.get("h")}
    cfg["mapshots"] = shots
    _write_cfg(cfg)
    return True


def clear_user_shot(level):
    key = _safe_key(level)
    shot = os.path.join(SHOT_DIR, key + ".webp")
    if os.path.isfile(shot):
        try:
            os.remove(shot)
        except OSError:
            pass
    cfg = _read_cfg()
    shots = cfg.get("mapshots") or {}
    if key in shots:
        shots.pop(key, None)
        cfg["mapshots"] = shots
        _write_cfg(cfg)


def clear_cache():
    CACHE.clear()
