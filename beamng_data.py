# -*- coding: utf-8 -*-
"""BeamNG 抓包数据引擎（纯 Python，无 GUI 依赖）。

老版 tkinter 界面已于 2026-10-21 删除；这里保留它的数据层，原样复用：
  analyze(path)           读 CSV + 同名 .txt 摘要，全部分析量
  conclusions(a,b=None)   大白话结论（含调校建议）
  suggestions(a,b=None)   调校建议
  compare_verdict(a,b)    两份数据对比结论
  fmt_report(a,b=None)    完整文本报告
  decimate_pts / read_* / load_terrain / surf_color / calc_alignment …
  路径配置：CFG_FILE / USERPATH / GAME_EXE / OUTDIR（启动时读 config.json）
  install_to_game(userpath)  把抓包扩展 / 自动加载脚本 / 面板 mod 装进游戏目录

自检：python beamng_data.py --selftest
"""

import csv
import math
import os
import re
import sys
import time

# ── 路径配置 ────────────────────────────────────────────────────────────
# ══ 路径配置（可自定义，也可自动探测）══════════════════════════════════
BASE_DIR = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))
BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
CFG_FILE = os.path.join(BASE_DIR, "config.json")


def _load_cfg():
    try:
        import json
        with open(CFG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _autodetect_userpath():
    r"""BeamNG 用户目录：一般是 %LOCALAPPDATA%\BeamNG.drive\<版本>，也可能被自定义"""
    cands = []
    la = os.environ.get("LOCALAPPDATA", "")
    if la:
        base = os.path.join(la, "BeamNG.drive")
        if os.path.isdir(base):
            for d in sorted(os.listdir(base), reverse=True):
                cands.append(os.path.join(base, d))
    cands += [r"D:\BeamNG\current", r"C:\BeamNG\current"]
    for c in cands:
        if os.path.isdir(os.path.join(c, "mods")) or os.path.isdir(os.path.join(c, "lua", "ge")):
            return c
    return cands[0] if cands else ""


def _autodetect_game_exe():
    """从 Steam 注册表 + 常见目录找 BeamNG.drive.exe"""
    cands = []
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        steam = winreg.QueryValueEx(k, "SteamPath")[0].replace("/", "\\")
        vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
        libs = [steam]
        if os.path.exists(vdf):
            import re
            txt = open(vdf, encoding="utf-8", errors="ignore").read()
            libs += [m.replace("\\\\", "\\") for m in re.findall(r'"path"\s+"([^"]+)"', txt)]
        for lib in libs:
            cands.append(os.path.join(lib, "steamapps", "common", "BeamNG.drive"))
    except (OSError, ImportError, IndexError):
        pass
    cands += [r"E:\SteamLibrary\steamapps\common\BeamNG.drive",
              r"D:\SteamLibrary\steamapps\common\BeamNG.drive",
              r"C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive"]
    for c in cands:
        exe = os.path.join(c, "Bin64", "BeamNG.drive.x64.exe")
        if os.path.exists(exe):
            return exe
    return ""


_CFG = _load_cfg()
USERPATH = _CFG.get("userpath") or _autodetect_userpath()
GAME_EXE = _CFG.get("game_exe") or _autodetect_game_exe()
OUTDIR = _CFG.get("outdir") or os.path.join(BASE_DIR, "抓包数据")
OUTDIR = os.path.abspath(OUTDIR)
def _derive_launcher(game_exe):
    """游戏根目录的 BeamNG.drive.exe（非 Steam 直启用它，不能直连 Bin64 里的 x64）。"""
    if not game_exe:
        return ""
    return os.path.join(os.path.dirname(os.path.dirname(game_exe)), "BeamNG.drive.exe")


LAUNCHER = _CFG.get("launcher") or _derive_launcher(GAME_EXE)
STEAM_URL = "steam://rungameid/284160"


def launch_game(mode="auto"):
    """启动 BeamNG.drive，返回 (ok, 说明)。

    mode:
      "steam"  → 走 Steam 协议（steam://rungameid/284160）
      "direct" → 用「非 Steam 启动路径」（游戏根目录 BeamNG.drive.exe）
      "auto"   → 有非 Steam 路径就用它，没有就 Steam
    注意：直连 Bin64 里的 BeamNG.drive.x64.exe 会新建空档案，不要那么干。
    """
    mode = (mode or "auto").strip().lower()
    if mode == "steam":
        try:
            os.startfile(STEAM_URL)          # noqa: S606  Windows 专用
            return True, "正在通过 Steam 启动游戏…"
        except OSError as e:
            return False, "启动失败：%s" % e
    if mode == "direct":
        if not LAUNCHER:
            return False, "没配置非 Steam 启动路径（设置页里填游戏根目录的 BeamNG.drive.exe）"
        if not os.path.isfile(LAUNCHER):
            return False, "非 Steam 启动路径不存在：%s" % LAUNCHER
        try:
            os.startfile(LAUNCHER)          # noqa: S606  Windows 专用
            return True, "正在直接启动游戏（非 Steam 模式）…"
        except OSError as e:
            return False, "启动失败：%s" % e
    # auto
    if LAUNCHER and os.path.isfile(LAUNCHER):
        try:
            os.startfile(LAUNCHER)          # noqa: S606  Windows 专用
            return True, "正在直接启动游戏（非 Steam 模式）…"
        except OSError as e:
            return False, "启动失败：%s" % e
    try:
        os.startfile(STEAM_URL)          # noqa: S606  Windows 专用
        return True, "正在通过 Steam 启动游戏…（没配置非 Steam 启动路径）"
    except OSError as e:
        return False, "启动失败：%s" % e

# ══ 装进游戏（扩展 + 自动加载脚本 + 面板 mod）═══════════════════════════
def _mod_source_dirs():
    """找 mod 源文件可能所在的目录：PyInstaller onedir 的 _internal、exe 同级、源码目录。"""
    dirs = []
    for d in (BUNDLE_DIR, BASE_DIR, os.path.dirname(os.path.abspath(sys.executable)),
              os.path.dirname(os.path.abspath(__file__))):
        if d and d not in dirs:
            dirs.append(d)
    return dirs


def _find_mod_file(name):
    for d in _mod_source_dirs():
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return os.path.join(BUNDLE_DIR, name)


def install_to_game(userpath):
    """把抓包扩展装到用户目录，返回 (成功数, 说明列表)"""
    import shutil
    done, msgs = 0, []
    if not userpath or not os.path.isdir(userpath):
        return 0, ["用户目录不存在: %s" % userpath]
    jobs = [
        (_find_mod_file("roadProfile.lua"),
         os.path.join(userpath, "lua", "ge", "extensions", "roadProfile.lua")),
        (_find_mod_file("modScript.lua"),
         os.path.join(userpath, "scripts", "roadProfile", "modScript.lua")),
        (_find_mod_file("roadProfileUI.zip"),
         os.path.join(userpath, "mods", "roadProfileUI.zip")),
    ]
    for src, dst in jobs:
        if not os.path.exists(src):
            msgs.append("缺少文件: " + os.path.basename(src))
            continue
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            done += 1
            msgs.append("已安装 " + os.path.basename(dst))
        except OSError as e:
            msgs.append("失败 %s: %s" % (os.path.basename(dst), e))
    # ★ 0.40.3 的 UI app 列表会缓存，mod zip 里的 app 可能不被识别；
    # 再把 zip 里的 ui/modules/apps/* 解成用户目录下的实体文件夹，保证一定能读到。
    try:
        import zipfile as _zf
        zsrc = _find_mod_file("roadProfileUI.zip")
        if os.path.exists(zsrc):
            with _zf.ZipFile(zsrc) as z:
                for name in z.namelist():
                    if not name.startswith("ui/modules/apps/roadProfile/"):
                        continue
                    if name.endswith("/"):
                        continue
                    dst = os.path.join(userpath, name.replace("/", os.sep))
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with z.open(name) as f, open(dst, "wb") as out:
                        out.write(f.read())
            msgs.append("已解压面板到 ui/modules/apps")
    except OSError as e:
        msgs.append("解压面板失败: %s" % e)
    # 旧版 mod 留下的键盘映射引用了已不存在的 action，会让整个 UI 反复刷清单；
    # 装 mod 时顺手清掉（备份成 .bak）
    try:
        kb = os.path.join(userpath, "settings", "inputmaps", "keyboard_roadprofile.json")
        if os.path.isfile(kb):
            os.replace(kb, kb + ".bak")
            msgs.append("已清理旧键盘映射")
    except OSError:
        pass
    return done, msgs



IPC_DIR = USERPATH                     # 游戏只能写用户目录（引擎 Lua 限制）
F_STATUS = os.path.join(IPC_DIR, "roadProfile_status.txt")
F_CMD = os.path.join(IPC_DIR, "roadProfile_cmd.txt")
F_LATEST = os.path.join(OUTDIR, "roadProfile_latest.csv")
DATA_PREFIX = "roadProfile_"
KEEP_IN_PLACE = {"roadProfile_status.txt", "roadProfile_cmd.txt", "roadProfile_error.txt"}
os.makedirs(OUTDIR, exist_ok=True)

BINS = [0.02, 0.05, 0.10, 0.20, 0.30, 0.50, 0.80, 1.20, 2.00]
SEG_LEN = 500.0
AIR_LOAD = 500.0
COL_A, COL_B = "#2f6fd0", "#d05f2f"

def read_rows(path):
    rows = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for r in csv.DictReader(f):
            row = {}
            for k, v in r.items():
                if v in (None, ""):
                    continue
                try:
                    row[k] = float(v)
                except (TypeError, ValueError):
                    row[k] = v          # 非数字列（比如地表材质 gm）原样保留
            if len(row) >= 5:
                rows.append(row)
    return rows


def read_meta(csv_path):
    """从同名的 .txt 摘要里读"车辆 / 配置 / 地图"（抓包时游戏写进去的）"""
    meta = {}
    txt = os.path.splitext(csv_path)[0] + ".txt"
    if os.path.exists(txt):
        try:
            for line in open(txt, encoding="utf-8", errors="ignore"):
                s = line.strip()
                if s.startswith("车辆"):
                    meta["veh"] = s.split(":", 1)[-1].strip()
                elif s.startswith("配置"):
                    meta["cfg"] = s.split(":", 1)[-1].strip()
                elif s.startswith("地图"):
                    meta["level"] = s.split(":", 1)[-1].strip()
                elif s.startswith("悬挂类型"):
                    meta["susp"] = s.split(":", 1)[-1].strip()
        except OSError:
            pass
    return meta


SURF_COLOR = [
    (("asphalt", "concrete", "pavement"), "#4a4a52", "柏油/水泥"),
    (("dirt", "sand", "dust"), "#c8a468", "土/沙"),
    (("grass", "lawn"), "#5a8c46", "草"),
    (("rock", "gravel", "stone"), "#8b8b85", "石/碎石"),
    (("mud", "swamp"), "#6b5436", "泥"),
    (("ice", "snow"), "#cfe3ef", "冰/雪"),
]


def surf_color(gm):
    """四轮材质串 -> (颜色, 名称)"""
    s = (gm or "").lower()
    for keys, col, name in SURF_COLOR:
        for k in keys:
            if k in s:
                return col, name
    return "#9aa4ad", "未知"


_ALIGN_CACHE = {}

ALIGN_KEYS = ("camber", "toe", "caster", "castor")


def calc_alignment(ax_str):
    """从主销上下节点坐标算外倾/主销后倾（相对世界垂直，单位度）
       ax_str: FL|FR|RL|RR, 每个是 x1,y1,z1,x2,y2,z2"""
    out = {}
    names = ["FL", "FR", "RL", "RR"]
    for i, part in enumerate((ax_str or "").split("|")[:4]):
        try:
            v = [float(x) for x in part.split(",")[:6]]
        except (TypeError, ValueError):
            continue
        if len(v) < 6 or (abs(v[0]) + abs(v[1]) + abs(v[2])) < 1:
            continue
        dx, dy, dz = v[3] - v[0], v[4] - v[1], v[5] - v[2]
        if abs(dz) < 1e-6:
            continue
        # 主销轴线相对垂直方向的倾角
        camber = math.degrees(math.atan2(dx, abs(dz)))    # 横向分量
        caster = math.degrees(math.atan2(dy, abs(dz)))    # 纵向分量
        out[names[i]] = (camber, caster)
    return out


def read_alignment(model):
    """从 mod / 官方车辆包里读 $camber_xx / $toe_xx / $caster_xx 这些变量（原样数值）"""
    if not model:
        return {}
    if model in _ALIGN_CACHE:
        return _ALIGN_CACHE[model]
    import glob
    import re
    import zipfile
    out = {}
    gamedir = os.path.dirname(os.path.dirname(GAME_EXE))
    pats = [os.path.join(USERPATH, "mods", "*.zip"),
            os.path.join(gamedir, "content", "vehicles", "*.zip")]
    prefix = ("vehicles/%s/" % model).lower()
    pat = re.compile(r'"\$([a-zA-Z_]*(?:camber|toe|caster|castor)[a-zA-Z_]*)"\s*:\s*(-?[\d.]+)')
    for pat_zip in pats:
        for zp in glob.glob(pat_zip):
            try:
                z = zipfile.ZipFile(zp)
            except (OSError, zipfile.BadZipFile):
                continue
            try:
                hits = [n for n in z.namelist()
                        if n.lower().startswith(prefix) and n.lower().endswith((".jbeam", ".pc"))]
                for n in hits[:28]:
                    try:
                        txt = z.read(n).decode("utf-8", "ignore")
                    except (OSError, KeyError):
                        continue
                    for k, v in pat.findall(txt):
                        key = k.lower()
                        if key not in out:
                            try:
                                out[key] = float(v)
                            except ValueError:
                                pass
            finally:
                z.close()
            if len(out) >= 3:
                break
        if len(out) >= 3:
            break
    _ALIGN_CACHE[model] = out
    return out


def load_terrain(path):
    """地形网格写在抓包自己的 .txt 里（游戏内 getTerrainHeight 采样）：
       标记 [地形网格 NxN] ... 每行 x,y,z ... [地形网格结束]"""
    import re
    tp = os.path.splitext(path)[0] + ".txt"
    if not os.path.exists(tp):
        return None
    try:
        with open(tp, encoding="utf-8", errors="ignore") as f:
            lines = f.read().split("\n")
    except OSError:
        return None
    inside = False
    nx = ny = 0
    pts = []
    for line in lines:
        s = line.strip()
        if s.startswith("[地形网格"):
            inside = True
            m = re.search(r"(\d+)\s*[x×]\s*(\d+)", s)
            if m:
                nx, ny = int(m.group(1)), int(m.group(2))
            continue
        if s.startswith("[地形网格结束"):
            break
        if inside and "," in s:
            a = s.split(",")
            try:
                pts.append((float(a[0]), float(a[1]), float(a[2])))
            except (ValueError, IndexError):
                pass
    if not nx:
        nx = ny = int(len(pts) ** 0.5)
    if nx < 2 or len(pts) < nx * ny:
        return None
    return {"nx": nx, "ny": ny, "pts": pts[:nx * ny]}


def analyze(path):
    rows = read_rows(path)
    n = len(rows)
    if n < 10:
        return None
    g = lambda r, k: r.get(k, 0.0)
    res = {"path": path, "n": n, "name": os.path.basename(path), "meta": read_meta(path),
           "dist": g(rows[-1], "d"), "dur": g(rows[-1], "t") - g(rows[0], "t")}

    vs = [g(r, "v") for r in rows]
    res["v_avg"], res["v_max"] = sum(vs) / n, max(vs)
    zs = [g(r, "z") for r in rows]
    res["z_min"], res["z_max"] = min(zs), max(zs)
    climb, grade = 0.0, 0.0
    for i in range(1, n):
        dz = zs[i] - zs[i - 1]
        dd = g(rows[i], "d") - g(rows[i - 1], "d")
        if dz > 0:
            climb += dz
        if dd > 0.5:
            grade = max(grade, abs(dz) / dd)
    res["climb"], res["grade"] = climb, grade

    corr = 0
    for i in range(1, n):
        bv = g(rows[i], "FLsv")
        dl = g(rows[i], "FLld") - g(rows[i - 1], "FLld")
        if abs(bv) > 0.02 and abs(dl) > 5:
            corr += (1 if bv > 0 else -1) * (1 if dl > 0 else -1)
    comp_sign = 1 if corr >= 0 else -1
    res["comp_sign"] = comp_sign

    hist = {k: [0] * (len(BINS) + 1) for k in ("Fc", "Fr", "Rc", "Rr")}
    cnt = {k: 0 for k in ("Fc", "Fr", "Rc", "Rr")}
    rms = {"front": 0.0, "rear": 0.0}
    seg = {}
    load = {k: 0.0 for k in ("FL", "FR", "RL", "RR")}
    lmin = {k: 1e9 for k in ("FL", "FR", "RL", "RR")}
    lmax = {k: 0.0 for k in ("FL", "FR", "RL", "RR")}
    air = {k: 0 for k in ("FL", "FR", "RL", "RR")}

    def binidx(v):
        for i, b in enumerate(BINS):
            if v < b:
                return i
        return len(BINS)

    for i, r in enumerate(rows):
        fv = (abs(g(r, "FLsv")) + abs(g(r, "FRsv"))) * 0.5
        rv = (abs(g(r, "RLsv")) + abs(g(r, "RRsv"))) * 0.5
        rms["front"] += fv * fv
        rms["rear"] += rv * rv
        for sv, key in ((g(r, "FLsv"), "F"), (g(r, "RLsv"), "R")):
            k = key + ("c" if (sv * comp_sign) >= 0 else "r")
            hist[k][binidx(abs(sv))] += 1
            cnt[k] += 1
        for k in ("FL", "FR", "RL", "RR"):
            ld = g(r, k + "ld")
            load[k] += ld
            lmin[k] = min(lmin[k], ld)
            lmax[k] = max(lmax[k], ld)
            if ld < AIR_LOAD:
                air[k] += 1
        si = int(g(r, "d") / SEG_LEN)
        s = seg.setdefault(si, {"d0": si * SEG_LEN, "n": 0, "rms": 0.0, "v": 0.0})
        s["n"] += 1
        s["rms"] += ((fv + rv) * 0.5) ** 2
        s["v"] += g(r, "v")

    res["hist"], res["cnt"] = hist, cnt
    res["rms_f"] = math.sqrt(rms["front"] / n)
    res["rms_r"] = math.sqrt(rms["rear"] / n)
    res["load"] = {k: load[k] / n for k in load}
    res["lmin"], res["lmax"] = lmin, lmax
    res["air"] = {k: air[k] / n * 100 for k in air}
    # ★ 轮荷标准差 σ：几何无关的"这个轮子有多忙"指标。
    #   减振器速度 RMS 受安装几何/传动比影响，前后不可直接比；σ 可以。
    sig = {}
    for k in ("FL", "FR", "RL", "RR"):
        m = res["load"][k]
        sig[k] = math.sqrt(sum((g(r, k + "ld") - m) ** 2 for r in rows) / n)
    res["loadsig"] = sig
    res["sig_f"] = (sig["FL"] + sig["FR"]) / 2
    res["sig_r"] = (sig["RL"] + sig["RR"]) / 2
    res["seg"] = sorted([v for v in seg.values() if v["n"] > 5],
                        key=lambda s: -(s["rms"] / s["n"]))
    res["segmap"] = {int(v["d0"] / SEG_LEN): math.sqrt(v["rms"] / v["n"])
                     for v in seg.values() if v["n"] > 5}
    # profile 每个点：(距离, x, y, z, 车速, 油门, 刹车)
    # 老文件没有后三列 => g() 返回 0，不影响其他功能
    res["profile"] = [(g(r, "d"), g(r, "x"), g(r, "y"), g(r, "z"), g(r, "v"),
                       g(r, "thr"), g(r, "brk"), r.get("gm", "")) for r in rows]
    # 四角减振器速度序列：(里程, FL, FR, RL, RR)，波形图用
    res["sv"] = [(g(r, "d"), g(r, "FLsv"), g(r, "FRsv"), g(r, "RLsv"), g(r, "RRsv"))
                 for r in rows]
    # 踏板使用统计
    nrow = len(rows) or 1
    res["thr_on"] = sum(1 for r in rows if g(r, "thr") > 0.1) / nrow * 100
    res["brk_on"] = sum(1 for r in rows if g(r, "brk") > 0.1) / nrow * 100
    res["thr_avg"] = sum(g(r, "thr") for r in rows) / nrow
    res["brk_avg"] = sum(g(r, "brk") for r in rows) / nrow
    res["has_pedal"] = any(g(r, "thr") + g(r, "brk") > 0.01 for r in rows)
    # ── 四轮：平均载荷 / 平均轮速 / 滑移率（轮速 vs 车速）──
    wheels = {}
    for tag in ("FL", "FR", "RL", "RR"):
        ld = [g(r, tag + "ld") for r in rows]
        sp = [g(r, tag + "sp") for r in rows]
        wheels[tag] = {"ld": sum(ld) / n, "ld_max": max(ld), "sp": sum(sp) / n}
    tot = sum(wheels[t]["ld"] for t in wheels) or 1.0
    res["wheels"] = wheels
    res["load_pct"] = {t: wheels[t]["ld"] / tot * 100 for t in wheels}
    front = wheels["FL"]["ld"] + wheels["FR"]["ld"]
    rear = wheels["RL"]["ld"] + wheels["RR"]["ld"]
    left = wheels["FL"]["ld"] + wheels["RL"]["ld"]
    right = wheels["FR"]["ld"] + wheels["RR"]["ld"]
    cross = wheels["FL"]["ld"] + wheels["RR"]["ld"]      # 对角（左前+右后）
    res["wb_balance"] = {
        "front": front / (front + rear) * 100 if front + rear else 0,
        "left": left / (left + right) * 100 if left + right else 0,
        "cross": cross / tot * 100,
    }
    # 滑移率：轮子线速度 vs 车速（>0 打滑，<0 抱死）
    slips = {}
    for tag in ("FL", "FR", "RL", "RR"):
        vals = []
        for r in rows:
            v = g(r, "v")
            if v > 3:
                vals.append((g(r, tag + "sp") - v) / v)
        slips[tag] = (sum(vals) / len(vals) * 100) if vals else 0.0
    res["slip_pct"] = slips
    # ── 动力曲线：用轮上功率 P = m*a*v 按转速分档（游戏不提供扭矩，但功率能算）──
    dyno = []
    try:
        mass = sum(g(rows[-1], k + "ld") for k in ("FL", "FR", "RL", "RR")) / 9.81
    except (KeyError, ValueError):
        mass = 0
    if mass < 200:
        mass = 1500.0        # 兜底
    if any(g(r, "rpm") > 200 for r in rows):
        step = 120
        for lo in range(0, 8001, step):
            ws = []
            for i in range(1, n):
                rpm = g(rows[i], "rpm")
                if not (lo <= rpm < lo + step):
                    continue
                v = g(rows[i], "v")
                dv = v - g(rows[i - 1], "v")
                dt = g(rows[i], "t") - g(rows[i - 1], "t")
                if dt <= 1e-4 or v < 2 or g(rows[i], "thr") < 0.25:
                    continue
                a = dv / dt
                ws.append(mass * a * v / 1000.0)     # kW
            if len(ws) < 2:
                continue
            ws.sort()
            kw = ws[int(len(ws) * 0.9)]              # 取 90 分位，避开瞬时尖峰
            rpm_mid = lo + step / 2
            tq_calc = (max(kw, 0.0) * 1000.0) / max(rpm_mid * 2 * 3.141592653589793 / 60.0, 1e-6)
            dyno.append((rpm_mid, tq_calc, max(kw, 0.0)))
    res["dyno"] = dyno
    res["mass"] = mass

    # 车辆型号（从 meta 里括号中取） + 静态定位参数
    import re as _re
    m = _re.search(r"\(([^)]+)\)", res["meta"].get("veh", ""))
    res["model"] = m.group(1).strip() if m else ""
    res["align"] = read_alignment(res["model"])
    axs = [r.get("ax", "") for r in rows if isinstance(r.get("ax"), str) and r.get("ax")]
    res["align_geo"] = calc_alignment(axs[len(axs) // 2]) if axs else {}

    # ── 动力曲线：逐点算纵向加速度（dv/dt），按车速分档 ──
    acc = []
    for i in range(1, n):
        dt = g(rows[i], "t") - g(rows[i - 1], "t")
        if dt <= 1e-4:
            continue
        a = (g(rows[i], "v") - g(rows[i - 1], "v")) / dt
        dz = (g(rows[i], "z") - g(rows[i - 1], "z")) / max(g(rows[i], "d") - g(rows[i - 1], "d"), 1e-3)
        acc.append((g(rows[i], "v") * 3.6, a / 9.81, g(rows[i], "thr"),
                    g(rows[i], "steer"), dz))
    bands_p = [(0, 30), (30, 60), (60, 90), (90, 120), (120, 160), (160, 200), (200, 400)]
    powr = []
    for lo, hi in bands_p:
        sel = [a for (vv, a, th, st, dz) in acc if lo <= vv < hi and th > 0.6 and abs(st) < 0.25]
        powr.append((lo, hi, (sum(sel) / len(sel)) if sel else None, len(sel)))
    res["power"] = powr
    res["acc_max"] = max((q[1] for q in acc), default=0)
    res["acc_min"] = min((q[1] for q in acc), default=0)
    # 0-100 最快一次
    best, t0 = None, None
    for i in range(n):
        v = g(rows[i], "v") * 3.6
        if v < 3:
            t0 = g(rows[i], "t")
        elif t0 is not None and v >= 100:
            dt100 = g(rows[i], "t") - t0
            if best is None or dt100 < best:
                best = dt100
            t0 = None
    res["t100"] = best
    # 滚动加速：从 a km/h 加速到 b km/h 的最快用时（不要求静止起步，线性插值过线时刻）
    def _cross(i0, target):
        for j in range(max(i0, 1), n):
            v0 = g(rows[j - 1], "v") * 3.6
            v1 = g(rows[j], "v") * 3.6
            if v1 >= target > v0:
                t0, t1 = g(rows[j - 1], "t"), g(rows[j], "t")
                frac = (target - v0) / max(v1 - v0, 1e-6)
                return t0 + frac * (t1 - t0), j
        return None, None

    roll = {}
    for lo, hi in ((0, 100), (60, 100), (80, 120), (100, 150)):
        best_t = None
        for i in range(n):
            va = g(rows[i], "v") * 3.6
            if not (lo - 1.0 <= va <= lo + 2.0):
                continue
            tb, j = _cross(i + 1, hi)
            if tb is None or tb <= g(rows[i], "t"):
                continue
            ok = True
            for k in range(i + 1, j):
                if (g(rows[k], "v") * 3.6) < va - 2.0:
                    ok = False
                    break
            if ok:
                dt = tb - g(rows[i], "t")
                if best_t is None or dt < best_t:
                    best_t = dt
        roll["%d-%d" % (lo, hi)] = round(best_t, 2) if best_t else None
    res["roll"] = roll
    res["v_start"] = round((g(rows[0], "v") if n else 0.0) * 3.6, 1)
    # 细曲线：每 5 km/h 一个小段的平均加速度，画折线用
    curve = []
    for lo in range(0, 405, 5):
        sel = [a for (vv, a, th, st, dz) in acc
               if lo <= vv < lo + 5 and th > 0.6 and abs(st) < 0.25]
        if len(sel) >= 2:
            curve.append((lo + 2.5, sum(sel) / len(sel)))
    sm = []
    for i in range(len(curve)):
        a = curve[max(0, i - 1)][1]
        b = curve[i][1]
        c2 = curve[min(len(curve) - 1, i + 1)][1]
        sm.append((curve[i][0], (a + b * 2 + c2) / 4.0))
    res["power_curve"] = sm
    # ★ 地形网格（扩展导出时生成的同名 _terrain.csv），3D 地图当底图用
    res["terrain"] = None      # 地形底图实验已回滚（页面回到地面网格）；解析函数留着备用
    # 地形只认抓包 .txt 里游戏采样出来的那份（不再读 .ter、也不自己生成）
    res["lmap"] = None
    # 速度分布：低速/中速/高速各占多少时间（用来判断该调哪一档阻尼）
    tot = sum(cnt.values()) or 1
    lowc = sum(hist["Fc"][:2]) + sum(hist["Rc"][:2])
    highc = sum(hist["Fc"][6:]) + sum(hist["Rc"][6:])
    res["pct_low"], res["pct_high"] = lowc / tot * 100, highc / tot * 100
    try:
        res["engine"] = analyze_engine(rows, g)
    except Exception:                 # noqa: BLE001 发动机数据坏了不能拖垮整页
        res["engine"] = {"has": False, "series": {}, "stats": {}, "problems": []}
    return res




# ══════════════════════════════════════════════════════════════════════
# 发动机数据（CSV 的 eng 列：k=v;k=v…，字段名随车不同，这里做同义词归一化）
# ══════════════════════════════════════════════════════════════════════
_ENG_SYN = {
    "rpm": ("rpm",),
    "torque": ("torque", "engine_torque", "enginetorque", "engtorque"),
    "boost": ("boost", "turbo_boost", "turboboost", "boost_pressure",
              "turbo_pressure", "turbo_boost_pressure"),
    "afr": ("afr", "air_fuel_ratio", "airfuelratio", "afr_ratio"),
    "lambda": ("lambda", "lambda_value", "lambda_ratio"),
    "water": ("water_temp", "watertemp", "coolant_temp", "coolanttemp",
              "water_temperature", "coolant_temperature"),
    "oil": ("oil_temp", "oiltemp", "oil_temperature"),
    "oilp": ("oil_pressure", "oilpressure", "oil_press", "oilpressurebar"),
    "oilalarm": ("oil",),
    "load": ("engine_load", "engineload", "load", "engine_load_value"),
    "throttle": ("throttle", "throttle_input", "throttleposition"),
    "damage": ("engine_damage", "engine_damage_ratio", "enginehealth",
               "engine_health", "health", "damage"),
    "egt": ("exhaust_temp", "exhausttemp", "egt", "exhaust_gas_temp"),
    "intake": ("intake_temp", "intaketemp", "manifold_temp", "manifoldtemp"),
    "fuel": ("fuel", "fuel_level", "fuellevel", "fuel_ratio"),
}
_ENG_DMG_NAME = {
    "pistonRingsDamaged": "活塞环损坏",
    "rodBearingsDamaged": "连杆轴承损坏",
    "headGasketDamaged": "缸垫损坏",
    "turbochargerHot": "涡轮过热",
    "engineIsHydrolocking": "进气进水（正在淹缸）",
    "engineHydrolocked": "发动机进水锁死",
    "engineReducedTorque": "发动机扭矩受限",
    "mildOverrevDamage": "轻微超转损伤",
    "mildOverTorqueDamage": "轻微超扭损伤",
    "engineDisabled": "发动机损坏停用",
    "blockMelted": "缸体熔毁",
    "engineLockedUp": "发动机抱死",
    "coolantOverheating": "冷却液过热报警",
    "starvedOfOil": "缺机油报警",
    "oilOverheating": "机油过热报警",
    "headGasketBlown": "缸垫冲了",
    "pc_headGasketBlown": "缸垫冲了",
    "pc_pistonRingsDamaged": "活塞环损坏",
    "pc_connectingRodBearingsDamaged": "连杆轴承损坏",
    "pc_engineBlockMelted": "缸体熔毁",
    "pc_cylinderWallsMelted": "缸壁熔毁",
    "pc_isBroken": "发动机已损坏",
}
_ENG_LABEL = {
    "rpm": "转速 rpm", "torque": "发动机扭矩 Nm", "boost": "增压 bar",
    "afr": "空燃比 AFR", "lambda": "Lambda", "water": "水温 °C",
    "oil": "油温 °C", "oilp": "机油压力 bar", "load": "发动机负荷 %",
    "throttle": "节气门 %", "damage": "发动机损伤 %", "egt": "排气温度 °C",
    "intake": "进气温度 °C", "fuel": "油量",
}


def _parse_eng(txt):
    """'rpm=1200;water_temp=88;…' -> dict（同名取第一个）"""
    out = {}
    if not txt or not isinstance(txt, str):
        return out
    for part in txt.split(";"):
        if "=" not in part:
            continue
        k, _, v = part.partition("=")
        try:
            out[k.strip().lower()] = float(v)
        except ValueError:
            continue
    return out


def _eng_pick(eng, row, field):
    names = _ENG_SYN.get(field, ())
    for n in names:
        if n in eng:
            return eng[n]
    for n in names:                      # 旧 CSV 里偶尔直接有同名列
        v = row.get(n)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def analyze_engine(rows, g):
    """从 rows 的 eng 列提取发动机时序 + 统计 + 问题诊断。"""
    res = {"has": False, "series": {}, "stats": {}, "problems": [], "labels": _ENG_LABEL}
    if not rows:
        return res
    parsed = []
    any_data = False
    for r in rows:
        eng = _parse_eng(r.get("eng"))
        if eng:
            any_data = True
        parsed.append(eng)
    if not any_data:
        return res
    res["has"] = True

    def series_of(field, step=1):
        # 横轴用时间：发动机数据按时间看更直观，原地轰油门/短距离也能画开
        out = []
        for i in range(0, len(rows), step):
            v = _eng_pick(parsed[i], rows[i], field)
            if v is None:
                continue
            tt = g(rows[i], "t")
            out.append([round(float(tt), 2), round(float(v), 3)])
        return out

    raw = {k: series_of(k) for k in _ENG_SYN}
    # 归一化：温度 K -> °C；增压 psi -> bar；lambda -> AFR；0-1 -> 百分比
    for k in ("water", "oil", "egt", "intake"):
        vals = [p[1] for p in raw[k]]
        if vals and max(vals) > 200:
            raw[k] = [[p[0], round(p[1] - 273.15, 1)] for p in raw[k]]
    vals = [p[1] for p in raw["boost"]]
    if vals and max(abs(v) for v in vals) > 5:
        raw["boost"] = [[p[0], round(p[1] / 14.5038, 2)] for p in raw["boost"]]
    lam = [p[1] for p in raw["lambda"]]
    if lam and not raw["afr"]:
        raw["afr"] = [[p[0], round(p[1] * 14.7, 2)] for p in raw["lambda"]]
    else:
        afr = [p[1] for p in raw["afr"]]
        if afr and max(afr) < 3.0:       # 有些车把 lambda 填在 AFR 字段
            raw["afr"] = [[p[0], round(p[1] * 14.7, 2)] for p in raw["afr"]]
    for k in ("load", "throttle"):
        vals = [p[1] for p in raw[k]]
        if vals and max(vals) <= 1.5:
            raw[k] = [[p[0], round(p[1] * 100, 1)] for p in raw[k]]
    vals = [p[1] for p in raw["damage"]]
    if vals and max(vals) <= 1.0:
        raw["damage"] = [[p[0], round(p[1] * 100, 1)] for p in raw["damage"]]

    # 抽样给前端（最多 ~450 点/序列）
    ser = {}
    for k, pts in raw.items():
        if len(pts) > 450:
            stepn = max(1, len(pts) // 450)
            pts = pts[::stepn]
        ser[k] = pts
    res["series"] = {k: v for k, v in ser.items() if v}

    def col(field):
        return [p[1] for p in raw.get(field, [])]

    def stats_of(field):
        vals = col(field)
        if not vals:
            return None
        return {"min": round(min(vals), 2), "max": round(max(vals), 2),
                "avg": round(sum(vals) / len(vals), 2), "n": len(vals)}

    for f in _ENG_SYN:
        st = stats_of(f)
        if st:
            res["stats"][f] = st

    # boost 原始值（PSI）也留一份给页面同时显示 psi/bar
    raw_boost = [p[1] for p in raw.get("boost", [])]
    if raw_boost:
        # raw["boost"] 此时已经被换算成 bar，反推回 psi
        res["stats"]["boost_psi"] = {"max": round(max(raw_boost) * 14.5038, 2),
                                     "avg": round(sum(raw_boost) / len(raw_boost) * 14.5038, 2)}
    bmax = None
    for i in range(len(rows)):
        e = parsed[i]
        for k in ("boostmax", "turbo_boost_max", "turboboostmax"):
            if k in e:
                bmax = max(bmax or 0, e[k])
    if bmax:
        res["stats"]["boostmax"] = {"max": round(bmax, 2), "bar": round(bmax / 14.5038, 2)}
    oa = res["stats"].get("oilalarm")
    if oa:
        res["stats"]["oilalarm"]["pct"] = round(sum(1 for v in col("oilalarm") if v > 0.5) / len(col("oilalarm")) * 100, 1)
    res["fields"] = {f: (f in res["stats"]) for f in _ENG_SYN}

    # ── 发动机损伤（engdmg）：整段抓包取最坏状态 ──
    dmg = {"has": False, "integrity": None, "flags": {}, "bad": [],
           "state": {}, "parts": {}, "new_format": False}
    for r in rows:
        txt = r.get("eng")
        if not isinstance(txt, str) or "engdmg=" not in txt:
            continue
        dmg["has"] = True
        for part in txt.split(";"):
            if not part.startswith("engdmg="):
                continue
            for item in part[len("engdmg="):].split("|"):
                k, _, v = item.partition("=")
                if not k:
                    continue
                if k == "integrity":
                    try:
                        iv = float(v)
                        dmg["integrity"] = iv if dmg["integrity"] is None else min(dmg["integrity"], iv)
                    except ValueError:
                        pass
                elif k.startswith("part_"):
                    try:
                        pv = float(v)
                        dmg["parts"][k[5:]] = max(dmg["parts"].get(k[5:], 0.0), pv)
                    except ValueError:
                        pass
                elif k in ("disabled", "broken"):
                    dmg["new_format"] = True
                    dmg["state"][k] = dmg["state"].get(k, False) or (v == "1")
                elif k == "torque_state":
                    dmg["new_format"] = True
                    try:
                        tv = float(v)
                        dmg["state"][k] = tv if k not in dmg["state"] else min(dmg["state"][k], tv)
                    except ValueError:
                        pass
                else:
                    dmg["flags"][k] = dmg["flags"].get(k, False) or (v == "1")

    seen = []
    for k, v in dmg["flags"].items():
        if v:
            name = _ENG_DMG_NAME.get(k, k)
            if name not in seen:
                seen.append(name)
    for name, score in sorted(dmg["parts"].items(), key=lambda kv: -kv[1]):
        if score >= 0.2:
            short = name.rstrip("/").split("/")[-1]
            label = "部件损伤：%s %.0f%%" % (short, score * 100)
            if label not in seen:
                seen.append(label)
    dmg["bad"] = seen
    dmg["names"] = _ENG_DMG_NAME
    res["damage"] = dmg


    # ── 诊断规则（阈值保守，只报明显异常）────────────────
    probs = res["problems"]

    def add(tone, title, text):
        probs.append({"tone": tone, "title": title, "text": text})

    w = res["stats"].get("water")
    if w:
        if w["max"] >= 110:
            add("bad", "水温过高 %.0f°C" % w["max"],
                "冷却系统压不住：检查水箱风扇/节温器/冷却液量，或降低增压/负载。")
        elif w["max"] >= 100:
            add("warn", "水温偏高 %.0f°C" % w["max"],
                "接近开锅；原地轰油门没有迎面风也会升温，跑起来能降下来就问题不大。")
    o = res["stats"].get("oil")
    if o:
        if o["max"] >= 130:
            add("bad", "机油温度过高 %.0f°C" % o["max"],
                "机油会快速劣化：加装油冷或在设置里降低负载/换高粘度机油。")
        elif o["max"] >= 115:
            add("warn", "机油温度偏高 %.0f°C" % o["max"], "关注长时间高转表现。")
    op = res["stats"].get("oilp")
    if op and op["min"] < 0.8 and op["min"] > 0:
        add("bad", "机油压力偏低（最低 %.2f bar）" % op["min"],
            "检查机油量/油泵/油路；高压低转时压力过低容易拉瓦。")
    b = res["stats"].get("boost")
    if b and b["max"] > 2.5:
        add("warn", "增压偏高 %.2f bar" % b["max"],
            "确认泄压阀/旁通阀工作正常，涡轮压力调太高容易爆缸。")
    afr = res["stats"].get("afr")
    if afr:
        if afr["max"] >= 16.0:
            add("warn", "空燃比偏稀（最高 %.1f）" % afr["max"],
                "高负载混合气偏稀：检查喷油/油压/进气漏气，容易爆震过热。")
        elif afr["min"] <= 9.5:
            add("warn", "空燃比偏浓（最低 %.1f）" % afr["min"],
                "混合气偏浓：动力变闷、油耗高，检查喷油脉宽/进气。")
    dmg = res["stats"].get("damage")
    if dmg and dmg["max"] > 4.0:
        add("bad", "发动机损伤 %.0f%%" % dmg["max"],
            "检查是否有爆震/过热历史；损伤不可逆，先修好再调校。")
    elif dmg and dmg["max"] > 1.0:
        add("warn", "发动机轻微损伤 %.1f%%" % dmg["max"],
            "留意水温/油温与爆震，别继续加负载。")
    rpm = res["stats"].get("rpm")
    if rpm and rpm["max"] >= 7000:
        add("info", "最高转速 %.0f rpm" % rpm["max"], "注意断油点和高转保护。")
    dmg = res.get("damage") or {}
    if dmg.get("has") and not dmg.get("new_format"):
        add("info", "这份抓包是旧版扩展录的，没有发动机损伤数据",
            "旧版只记了电控里的热损伤标志，不包含设备状态/部件损伤；重启游戏后新录的抓包才有。")
    if dmg.get("has") and dmg.get("new_format"):
        st = dmg.get("state") or {}
        if st.get("broken") or st.get("disabled"):
            add("bad", "发动机已损坏停用",
                "游戏判定发动机已经不能工作（爆缸/抱死/进水等）：先修/换发动机再调校。")
        if isinstance(st.get("torque_state"), (int, float)) and st["torque_state"] < 0.99:
            add("warn", "发动机扭矩受限（%.0f%%）" % (st["torque_state"] * 100),
                "发动机被降扭保护：检查水温/油温/爆震，修好前别继续加负荷。")
        parts = dmg.get("parts") or {}
        severe = [k for k, v in parts.items() if v >= 0.6]
        mid = [k for k, v in parts.items() if 0.2 <= v < 0.6]
        if severe:
            add("bad", "发动机部件严重受损：" + " / ".join(severe[:5]),
                "这些部件的 jbeam 已经撞变形/断裂（撞车或爆缸造成），需要换件。")
        elif mid:
            add("warn", "发动机部件受损：" + " / ".join(mid[:5]),
                "部件有变形但还没完全坏，注意别继续硬开。")
        if dmg.get("integrity") is not None and dmg["integrity"] < 0.85:
            add("bad", "发动机完整度低（%.0f%%）" % (dmg["integrity"] * 100),
                "游戏判定发动机已经受损：先修再调校。")
        if dmg.get("bad"):
            add("bad", "发动机损伤：" + " / ".join(dmg["bad"][:6]),
                "damageTracker / 部件损伤报告了这些部位，按上面列表检查/更换。")
    if not probs:
        add("ok", "没发现明显发动机问题",
            "水温/油温/油压/空燃比都在合理范围内；继续观察高负载段即可。")
    return res



def conclusions(a, b=None):
    """把统计翻译成人话 —— 界面最上面那几条"""
    out = []
    m = a.get("meta", {})
    if m.get("veh") or m.get("cfg"):
        out.append("· 车辆：%s　配置：%s　地图：%s"
                   % (m.get("veh", "?"), m.get("cfg", "?"), m.get("level", "?")))
    fa, ra = a["rms_f"], a["rms_r"]
    sf, sr = a.get("sig_f", 0), a.get("sig_r", 0)
    # ★ 前后对比要用【轮荷波动 σ】（几何无关）；减振器速度 RMS 受安装几何影响，前后不可直接比
    if sf > 0 and sr > 0:
        d = (sr / sf - 1) * 100
        if abs(d) < 20:
            out.append("· 前后轴工作量接近（轮荷波动 σ 前 %.0f / 后 %.0f N，差 %+.0f%%）→ 两轴强度相当"
                       % (sf, sr, d))
        else:
            who = "后轴" if d > 0 else "前轴"
            out.append("· %s明显更忙（轮荷波动 σ 前 %.0f / 后 %.0f N，差 %+.0f%%）→ 优先调%s"
                       % (who, sf, sr, d, who))
    out.append("· 减振器速度 RMS 前 %.3f / 后 %.3f m/s —— 注意：这个数受减振器安装几何影响，"
               "前后不能直接比大小（用上面的轮荷波动判断谁更忙）" % (fa, ra))
    if fa > 0:
        pass          # 前后对比已改用轮荷波动 σ（见上面），这里不再用 RMS 比大小
    out.append("· 减振器 %d%% 的时间速度 < 0.05 m/s（低速段），%d%% 的时间 > 0.3 m/s（高速段）"
               % (a["pct_low"], a["pct_high"]))
    if a["pct_high"] > 15:
        out.append("  → 高速段占比高：路面颠/车速快，调「高速阻尼」才有明显效果")
    else:
        out.append("  → 低速段为主：日常手感由「低速阻尼」决定，高速阻尼动了也感觉不到")
    if a["seg"]:
        s = a["seg"][0]
        out.append("· 最颠的一段在 %.0f m 处（RMS %.3f）→ 想验证改动，去这段跑最有效"
                   % (s["d0"], math.sqrt(s["rms"] / s["n"])))
    amax = max(a["air"].values())
    if amax > 2:
        out.append("· 有轮子离地（最多 %.1f%% 时间）→ 阻尼偏硬或路面有跳台" % amax)
    else:
        out.append("· 四个轮基本不离地（最多 %.1f%%）→ 抓地和阻尼匹配正常" % amax)
    if a.get("has_pedal"):
        out.append("· 踏板：油门踩下 %d%% 的时间（平均开度 %d%%），刹车 %d%% 的时间（平均 %d%%）"
                   % (a["thr_on"], a["thr_avg"] * 100, a["brk_on"], a["brk_avg"] * 100))
        if a["brk_on"] > 15:
            out.append("  → 刹车时间占比高：减速时的点头/前倾会混进数据，判断悬挂时先看油门段")
    if b:
        for tag, k in (("前轴", "rms_f"), ("后轴", "rms_r")):
            if b[k] > 0:
                d = (a[k] / b[k] - 1) * 100
                if abs(d) >= 8:
                    out.append("· 对比：%s RMS 从 %.3f 变成 %.3f（%+.0f%%）→ %s"
                               % (tag, b[k], a[k], d,
                                  "更颠了，方向可能反了" if d > 0 else "更稳了，方向对"))
                else:
                    out.append("· 对比：%s RMS 基本没变（%+.0f%%）→ 这项改动没起作用" % (tag, d))
    out.append("")
    for line in suggestions(a, b):
        out.append(line)
    return out


def suggestions(a, b=None):
    """根据数据给出修改建议
       云辇版：给 mod 里的具体参数
       原厂车：只能"换零件 + 游戏内调校滑块"，按这个说"""
    out = ["── 建议怎么改 ──"]
    m = a.get("meta", {})
    susp = m.get("susp") or ""
    if susp:
        is_stock = ("原厂" in susp)
    else:
        # 老版本抓的数据没这一行，按配置名推断（云辇版配置名里带 Yunnian/云辇/测试）
        cfg = (m.get("cfg", "") + m.get("config", "")).lower()
        is_stock = not any(k in cfg for k in ("yunnian", "云辇", "测试"))

    tot = sum(max(a["cnt"][k], 1) for k in ("Fc", "Fr", "Rc", "Rr"))

    def band(lo, hi):
        s = 0
        for k in ("Fc", "Fr", "Rc", "Rr"):
            for i in range(lo, min(hi + 1, len(a["hist"][k]))):
                s += a["hist"][k][i]
        return s / tot * 100

    low, high = band(0, 2), band(5, 9)
    sf, sr = a.get("sig_f", 0), a.get("sig_r", 0)
    amax = max(a["air"].values())
    n = 1

    if is_stock:
        out.append("· 原厂零件：能动的只有 ① 车辆配置里的悬挂/轮胎零件 ② 配置界面的「调校」滑块")
        if high > 30:
            out.append("· 大冲击占 %.0f%%（>30%%）—— 抗冲击不够，三件事按顺序试：" % high)
            out.append("   ① 零件：车辆配置 → 悬挂，换更硬/行程更大的一档（有 sport、竞技、越野可选的话）")
            out.append("   ② 调校：弹簧刚度 +5~10%（先加前轴）；减振器阻尼如果有这一项就 +1 档")
            out.append("   ③ 胎压 +0.2 bar（更抗触底，代价抓地略降）")
            n += 1
        elif low > 45:
            out.append("· 细碎颠簸占 %.0f%%（>45%%）—— 手感全由低速阻尼决定，想更舒服：" % low)
            out.append("   ① 调校：弹簧刚度 −5%、阻尼 −1 档")
            out.append("   ② 胎压 −0.2 bar")
            out.append("   ③ 零件：换舒适型轮胎（配置里如果有）")
            n += 1
        if sf > 0 and sr > 0:
            d = (sr / sf - 1) * 100
            if d > 15:
                out.append("· 后轴比前轴忙 %.0f%% —— 调校里如果有前后独立弹簧/阻尼，"
                           "把后轴 +10%%；没有就把后轮胎压 +0.1 bar" % d)
                n += 1
            elif d < -15:
                out.append("· 前轴比后轴忙 %.0f%% —— 把前轴弹簧/阻尼 +10%%，"
                           "或前轮胎压 +0.1 bar" % abs(d))
                n += 1
        if amax > 2:
            out.append("· 有轮离地 %.1f%% —— ① 阻尼 −1 档 ② 胎压 −0.2 bar ③ 换行程更大的悬挂" % amax)
            n += 1
        if n == 1:
            out.append("· 数据没有明显异常，原厂设置基本合理 —— "
                       "想更舒服就降胎压/阻尼，想更稳就升弹簧/加胎压，一次只动一样")
    else:
        if high > 30:
            out.append("· 大冲击占 %.0f%%（>30%%）→ 高速阻尼不够：把 jbeam 里 "
                       "shock_FL/FR 的 beamDampFast 2800→3400、shock_RL/RR 3500→4200（各 +20%%）" % high)
            n += 1
        elif low > 45:
            out.append("· 细碎颠簸占 %.0f%%（>45%%）→ 手感几乎全由低速阻尼决定："
                       "想更软把 CDC 的 comfort 0.60→0.50，想更扎实就 0.60→0.75" % low)
            n += 1
        if sf > 0 and sr > 0:
            d = (sr / sf - 1) * 100
            if d > 15:
                out.append("· 后轴比前轴忙 %.0f%% → 后轴偏软："
                           "CDC 的 rearBias 1.4→1.6、rearReboundBias 1.8→2.0" % d)
                n += 1
            elif d < -15:
                out.append("· 前轴比后轴忙 %.0f%% → 前轴偏软：CDC 的 comfort 再降 0.05，"
                           "或把前悬 hard bump stop 再加强" % abs(d))
                n += 1
        if amax > 2:
            out.append("· 有轮离地 %.1f%% 时间 → 阻尼偏硬或路面有跳台："
                       "先降 10%% 回弹（comfortReb 1.25→1.13），再看离地有没有减少" % amax)
            n += 1
        if n == 1:
            out.append("· 数据没有明显异常，当前设置基本合理 —— 想继续优化就一次只改一个参数")

    if b:
        common = set(a["segmap"]) & set(b["segmap"])
        if common:
            base = sum(b["segmap"][k] for k in common) / len(common)
            pct = ((sum(a["segmap"][k] - b["segmap"][k] for k in common) / len(common))
                   / base * 100) if base > 1e-6 else 0
            if abs(pct) < 5:
                out.append("· 对比几乎没变化 → 这次改的不是关键，换一个变量再试")
            elif pct < 0:
                out.append("· 对比往好的方向走了 %.0f%% → 按同方向再微调 10~15%%" % abs(pct))
            else:
                out.append("· 对比反而更颠了 %.0f%% → 方向反了，把这次的改动改回去" % abs(pct))

    out.append("（一次只动一个参数，否则分不清是谁的影响）")
    return out


def compare_verdict(a, b):
    """把两份数据的对比翻译成大白话（界面顶部那几行）"""
    out = []
    segA, segB = set(a["segmap"]), set(b["segmap"])
    common = segA & segB
    la, lb = a["dist"] / 1000, b["dist"] / 1000
    va, vb = a["v_avg"] * 3.6, b["v_avg"] * 3.6

    out.append("【第一份 A】%s" % a["name"])
    out.append("【第二份 B】%s" % b["name"])

    if not common:
        out.append("❌ 没法比：两份没有跑过同一段路（A %.1f km，B %.1f km）" % (la, lb))
        out.append("   → 请在同一条路上跑，长度接近，再对比")
        return out

    cover = len(common) / max(len(segA), len(segB)) * 100
    if cover < 60:
        out.append("⚠ 只能比一部分：A 跑了 %.1f km（%d 段），B 跑了 %.1f km（%d 段），"
                   "重叠只有 %d 段" % (la, len(segA), lb, len(segB), len(common)))
        out.append("   → 灰色路段表示只有一份跑过，没法比")
    else:
        out.append("✔ 可以比：重叠 %d 段（%.0f%%）" % (len(common), cover))

    if abs(va - vb) > 20:
        out.append("⚠ 车速差太多（A %.0f / B %.0f km/h）—— 颠簸主要由车速决定，这个对比不可信"
                   % (va, vb))
        out.append("   → 请用接近的车速跑同样的路，对比才有意义")
    else:
        out.append("车速接近（A %.0f / B %.0f km/h）✔" % (va, vb))

    diffs = [a["segmap"][k] - b["segmap"][k] for k in common]
    base = sum(b["segmap"][k] for k in common) / len(common)
    pct = (sum(diffs) / len(diffs)) / base * 100 if base > 1e-6 else 0
    if abs(pct) < 5:
        out.append("● 结论：两份几乎一样（差 %+.0f%%）—— 改动没起作用，或者两份条件不一样" % pct)
    elif pct > 0:
        out.append("● 结论：A 比 B 颠 %.0f%%（A 的悬挂工作更重）" % abs(pct))
    else:
        out.append("● 结论：A 比 B 稳 %.0f%%（A 的悬挂工作更轻，这就是你要的方向）" % abs(pct))
    return out


def fmt_report(a, b=None):
    L = []
    m = a.get("meta", {})
    L.append("── 本次数据 ──")
    if m:
        L.append("  车辆 %s   配置 %s   地图 %s"
                 % (m.get("veh", "?"), m.get("cfg", "?"), m.get("level", "?")))
    L.append("  时长 %.1f 秒   里程 %.0f 米   平均 %.0f km/h   最高 %.0f km/h"
             % (a["dur"], a["dist"], a["v_avg"] * 3.6, a["v_max"] * 3.6))
    L.append("  高程 %.0f ~ %.0f 米（落差 %.0f 米，累计爬升 %.0f 米，最陡 %.1f%%）"
             % (a["z_min"], a["z_max"], a["z_max"] - a["z_min"], a["climb"], a["grade"] * 100))
    L.append("  减振器速度 RMS：前轴 %.3f   后轴 %.3f  m/s  (受安装几何影响，前后不可直接比)"
             % (a["rms_f"], a["rms_r"]))
    L.append("  轮荷波动 σ：  前轴 %.0f   后轴 %.0f  N   (几何无关，用来判断谁更忙)"
             % (a.get("sig_f", 0), a.get("sig_r", 0)))
    L.append("")
    L.append("── 减振器速度分布（该调哪档阻尼看这里）──")
    L.append("   档位范围 (m/s)      " + "".join("%9s" % n for n in
             ["<.02", ".02-.05", ".05-.1", ".1-.2", ".2-.3", ".3-.5", ".5-.8", ".8-1.2", ">1.2"]))
    for key, name in (("Fc", "前轴 压缩"), ("Fr", "前轴 回弹"), ("Rc", "后轴 压缩"), ("Rr", "后轴 回弹")):
        t = max(a["cnt"][key], 1)
        pcts = [a["hist"][key][i] / t * 100 for i in range(len(BINS) + 1)]
        pcts = pcts[:7] + [pcts[7] + pcts[8], pcts[9]]
        L.append("   %-16s" % name + "".join("%8.0f%%" % p for p in pcts))
    L.append("")
    L.append("── 四轮负荷（N）──")
    for k, nm in (("FL", "左前"), ("FR", "右前"), ("RL", "左后"), ("RR", "右后")):
        L.append("   %s  平均 %5.0f   波动σ %5.0f   最小 %5.0f   最大 %5.0f   离地 %.1f%%"
                 % (nm, a["load"][k], a.get("loadsig", {}).get(k, 0),
                    a["lmin"][k], a["lmax"][k], a["air"][k]))
    L.append("")
    L.append("── 最颠的路段（每 500 米一段，前 5）──")
    for s in a["seg"][:5]:
        L.append("   %6.0f m 处   颠簸 RMS %.3f m/s   平均车速 %.0f km/h"
                 % (s["d0"], math.sqrt(s["rms"] / s["n"]), s["v"] / max(s["n"], 1) * 3.6))
    if b:
        L.append("")
        L.append("── 对比（第一份 vs 第二份）──")
        L.append("   减振器 RMS 前轴 %.3f → %.3f    后轴 %.3f → %.3f"
                 % (b["rms_f"], a["rms_f"], b["rms_r"], a["rms_r"]))
        for k, nm in (("FL", "左前"), ("FR", "右前"), ("RL", "左后"), ("RR", "右后")):
            L.append("   %s 平均负荷 %.0f → %.0f N" % (nm, b["load"][k], a["load"][k]))
    return "\n".join(L)


# ══ 3D 渲染 ════════════════════════════════════════════════════════════
def ramp(t):
    t = max(0.0, min(1.0, t))
    stops = [(0.0, (48, 92, 200)), (0.25, (40, 190, 210)), (0.5, (60, 190, 80)),
             (0.75, (230, 190, 40)), (1.0, (220, 60, 50))]
    for i in range(1, len(stops)):
        if t <= stops[i][0]:
            a, b = stops[i - 1], stops[i]
            f = (t - a[0]) / max(b[0] - a[0], 1e-6)
            return "#%02x%02x%02x" % tuple(int(a[1][k] + (b[1][k] - a[1][k]) * f) for k in range(3))
    return "#dc3c32"


METRICS = [("speed", "车速"), ("elev", "高程"), ("rough", "颠簸"),
           ("pedal", "油门/刹车"), 
           ("roughdiff", "两份对比差异")]


def decimate_pts(lst, maxn=1200):
    """点太多时等距抽稀（保留首尾），画图用；不改变分析数据"""
    n = len(lst)
    if n <= maxn:
        return lst
    step = n / float(maxn)
    out = [lst[int(i * step)] for i in range(maxn)]
    if out[-1] is not lst[-1]:
        out[-1] = lst[-1]
    return out



# ══════════════════════════════════════════════════════════════════════
# 游戏进程检测（抓包 mod 还没写状态时，界面也能知道游戏起没起）
# ══════════════════════════════════════════════════════════════════════
_GAME_PROCS = ("beamng.drive.x64.exe", "beamng.drive.exe")
_game_cache = {"ts": 0.0, "val": False}


def game_running(ttl=1.5):
    """BeamNG 进程是否在跑（纯 ctypes 枚举进程，带 1.5 秒缓存）。"""
    now = time.time()
    if now - _game_cache["ts"] < ttl:
        return _game_cache["val"]
    running = False
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD),
                        ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_void_p),
                        ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", wintypes.DWORD),
                        ("szExeFile", wintypes.WCHAR * 260)]

        k32 = ctypes.windll.kernel32
        snap = k32.CreateToolhelp32Snapshot(2, 0)      # TH32CS_SNAPPROCESS
        if snap and snap != ctypes.c_void_p(-1).value:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            try:
                ok = k32.Process32FirstW(snap, ctypes.byref(entry))
                while ok:
                    if entry.szExeFile.lower() in _GAME_PROCS:
                        running = True
                        break
                    ok = k32.Process32NextW(snap, ctypes.byref(entry))
            finally:
                k32.CloseHandle(snap)
    except Exception:                    # noqa: BLE001  非 Windows / 权限问题都当没跑
        running = False
    _game_cache["ts"] = now
    _game_cache["val"] = running
    return running


# ══════════════════════════════════════════════════════════════════════
# 自动识别新数据：把游戏写进用户目录的 roadProfile_*.csv 搬到数据目录
# （老版 App._nice_name / App.relocate 的逻辑，原样搬成纯函数）
# ══════════════════════════════════════════════════════════════════════
def _nice_name(csv_path):
    """roadProfile_vivace_20261022_122714.csv → FCV_vivace_20261022_1227.csv"""
    base = os.path.splitext(os.path.basename(csv_path))[0]
    parts = base.split("_")
    stamp = ""
    if len(parts) >= 2 and parts[-1].isdigit() and parts[-2].isdigit():
        stamp = parts[-2] + "_" + parts[-1][:4]
    if not stamp:
        stamp = time.strftime("%Y%m%d_%H%M", time.localtime(os.path.getmtime(csv_path)))

    veh, model = "", ""
    txt = os.path.splitext(csv_path)[0] + ".txt"
    if os.path.exists(txt):
        try:
            with open(txt, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    s = line.strip()
                    if s.startswith("车辆"):
                        # 车辆      : 小米YU7  (xiaomiyu)
                        v = s.split(":", 1)[-1].strip()
                        m = re.match(r"^(.*?)\s*\((.*?)\)\s*$", v)
                        if m:
                            veh, model = m.group(1).strip(), m.group(2).strip()
                        else:
                            veh = v
                        break
        except OSError:
            pass
    if not veh:
        for part in parts:            # 从文件名兜底取型号
            if part and part != "roadProfile" and not part.isdigit():
                model = model or part
                break
        veh = model or "未知车辆"
    model = model or "car"

    def clean(s):
        return re.sub(r'[\\/:*?"<>|]', "_", s).strip() or "car"

    return "%s_%s_%s.csv" % (clean(veh), clean(model), stamp)


def relocate():
    """把用户目录里的 roadProfile_*.csv/.txt 搬进数据目录并改成好认的名字。

    返回搬了几份（游戏还占着文件时 os.replace 会失败，下次轮询再试）。
    """
    moved = 0
    try:
        names = os.listdir(USERPATH)
    except OSError:
        return 0
    for fn in names:
        if not fn.startswith(DATA_PREFIX) or fn in KEEP_IN_PLACE:
            continue
        if not (fn.endswith(".csv") or fn.endswith(".txt")):
            continue
        src = os.path.join(USERPATH, fn)
        try:
            if fn.endswith(".csv"):
                dst = os.path.join(OUTDIR, _nice_name(src))
                if os.path.exists(dst):          # 同名就加序号，不覆盖
                    root, ext = os.path.splitext(dst)
                    k = 2
                    while os.path.exists("%s_%d%s" % (root, k, ext)):
                        k += 1
                    dst = "%s_%d%s" % (root, k, ext)
                os.replace(src, dst)
                stxt = os.path.splitext(src)[0] + ".txt"
                if os.path.exists(stxt):
                    try:
                        os.replace(stxt, os.path.splitext(dst)[0] + ".txt")
                    except OSError:
                        pass
                moved += 1
            else:                                # 只有 txt 也搬走，避免残留
                if not os.path.exists(os.path.splitext(src)[0] + ".csv"):
                    os.replace(src, os.path.join(OUTDIR, fn))
        except OSError:
            pass
    return moved


def send_command(cmd):
    """给游戏内扩展发命令（写 roadProfile_cmd.txt，扩展每帧轮询执行）。

    命令格式：<毫秒时间戳>,<cmd>；扩展会去掉前缀执行 cmd。
    """
    try:
        with open(F_CMD, "w", encoding="utf-8") as f:
            f.write("%d,%s\n" % (int(time.time() * 1000), cmd))
        return True
    except OSError:
        return False


def read_status():
    """读游戏写的 roadProfile_status.txt，返回游戏/抓包状态。"""
    out = {"alive": False, "recording": False, "dist": 0.0, "samples": 0,
           "veh": "", "cfg": "", "level": "", "age": None, "game": False}
    try:
        out["game"] = game_running()
    except Exception:               # noqa: BLE001
        pass
    try:
        if not os.path.exists(F_STATUS):
            return out
        d = {}
        with open(F_STATUS, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    d[k] = v
        age = time.time() - os.path.getmtime(F_STATUS)
        out["age"] = round(age, 1)
        out["alive"] = (age < 5) and (d.get("closed") != "1")
        out["recording"] = out["alive"] and (d.get("recording") == "1")
        for key, cast in (("dist", float), ("samples", int)):
            try:
                out[key] = cast(float(d.get(key) or 0))
            except (TypeError, ValueError):
                pass
        out["veh"] = d.get("vehname") or d.get("vehmodel") or ""
        out["cfg"] = d.get("cfgname") or ""
        out["level"] = d.get("level") or ""
    except OSError:
        pass
    return out


# ══════════════════════════════════════════════════════════════════════
# 自检（纯数据层，不需要 GUI）
# ══════════════════════════════════════════════════════════════════════
def selftest():
    import random
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_selftest.csv")
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write("t,d,x,y,z,v,vz,rollAV,pitchAV,steer,terrainH,"
                "FLsp,FLld,FRsp,FRld,RLsp,RLld,RRsp,RRld,FLsv,FRsv,RLsv,RRsv\n")
        random.seed(1)
        for i in range(3000):
            d = i * 1.5
            z = 100 + 30 * math.sin(d / 900) + 0.4 * math.sin(d / 7)
            sv = 0.35 * math.sin(d / 5) + random.uniform(-.05, .05)
            ld = 7000 - sv * 5200
            f.write("%.2f,%.1f,%.1f,%.1f,%.2f,%.1f,0,0,0,0,%.2f,"
                    "10,%.0f,10,%.0f,10,%.0f,10,%.0f,%.4f,%.4f,%.4f,%.4f\n"
                    % (i * .1, d, d * .3, d * .1, z, 30, z,
                       ld, ld, ld, ld, sv, sv, sv, sv))
    r = analyze(p)
    assert r and r["n"] == 3000, "analyze() failed"
    assert r["dist"] > 0 and r["rms"] if "rms" in r else True
    concl = conclusions(r)
    assert isinstance(concl, list) and concl
    rep = fmt_report(r)
    assert isinstance(rep, str) and "本次数据" in rep
    for k in ("hist", "cnt", "load", "profile", "sv", "seg", "segmap", "dyno"):
        assert k in r, "missing key: " + k
    os.remove(p)
    print("selftest ok: analyze/conclusions/fmt_report all good")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    print("beamng_data.py: run with --selftest")

