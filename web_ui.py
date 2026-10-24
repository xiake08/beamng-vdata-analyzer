# -*- coding: utf-8 -*-
"""
车辆数据分析器 —— Web UI 原型（pywebview 版）
================================================
数据引擎在 beamng_data.py（老版 tkinter 界面已于 2026-10-21 删除）。
只做一个页面：① 减振器分布，用 HTML/CSS/JS 复刻 BeamNG 游戏内 UI 的观感
（毛玻璃卡片、大圆角、柔和阴影、淡蓝灰配色、左侧图标导航）。

用法：:

    python web_ui.py                          # 打开 1600x950 窗口（默认取 OUTDIR 里最新的 CSV）
    python web_ui.py --csv 某次抓包.csv        # 指定数据
    python web_ui.py --html preview.html      # 只导出 HTML（不给窗口）
    python web_ui.py --shot shot.png          # 开窗口 -> 自动截图 -> 关闭
    python web_ui.py --shot shot.png --headless   # 用 Edge headless 截 HTML（备用路线）

数据全部来自 beamng_data.analyze()，没有一处写死。
控制台是 GBK：本文件只 print ASCII，绝不输出中文/emoji。
"""
import argparse
import glob
import html as _html
import json
import math
import os
import subprocess
import sys
import threading
import tempfile
import time

# ── 控制台自保：任何非 GBK 字符都不要抛 UnicodeEncodeError ─────────────
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import beamng_data as T  # noqa: E402  （数据引擎，纯 Python）
import webui_parts as PARTS  # noqa: E402  （各页模块，见 webui_parts/SPEC.md）
from webui_parts.common import (  # noqa: E402
    IC, esc, fmt_dist, fmt_dur, head_html, chip, empty_state, legend, WHEEL_COLORS,
)

WINDOW_TITLE = "车辆数据分析器"
WIN_W, WIN_H = 1600, 950

# 三档与减振器速度 bin 的对应关系（BINS = [0.02, 0.05, 0.10, 0.20, 0.30, 0.50, 0.80, 1.20, 2.00]）
BAND_META = [
    # (bin 起, bin 止, 名称, 对应阻尼, 速度区间, 渐变色, 中间色, 光晕)
    (0, 2, "细碎颠簸", "低速阻尼", "&lt; 0.10 m/s", "#4F86B2", "#89BCDF", "rgba(91,143,185,.45)"),
    (3, 4, "常见起伏", "中速阻尼", "0.10 – 0.30 m/s", "#DFA94F", "#F2CE8E", "rgba(223,169,79,.38)"),
    (5, 9, "大冲击", "高速阻尼", "&gt; 0.30 m/s", "#D2685A", "#EE9E8E", "rgba(210,104,90,.34)"),
]

VERDICTS = [
    ("很平顺", "#3E9E7B"),
    ("一般", "#5B8FB9"),
    ("偏颠", "#D9A24A"),
    ("很颠", "#D06A5C"),
]


# ══════════════════════════════════════════════════════════════════════
# 数据
# ══════════════════════════════════════════════════════════════════════
def pick_csv(explicit=None):
    """取 OUTDIR 里 mtime 最新的 CSV（可用 --csv 覆盖）。"""
    if explicit:
        p = os.path.abspath(explicit)
        if not os.path.isfile(p):
            raise SystemExit("CSV not found: %s" % p)
        return p
    files = glob.glob(os.path.join(T.OUTDIR, "*.csv"))
    if not files:
        raise SystemExit("No CSV under OUTDIR: %s" % T.OUTDIR)
    return max(files, key=os.path.getmtime)


def band_pcts(r):
    tot = sum(max(r["cnt"][k], 1) for k in ("Fc", "Fr", "Rc", "Rr")) or 1
    out = []
    for lo, hi, _n, _d, _v, _c1, _c2, _g in BAND_META:
        s = 0
        for k in ("Fc", "Fr", "Rc", "Rr"):
            for i in range(lo, min(hi + 1, len(r["hist"][k]))):
                s += r["hist"][k][i]
        out.append(s / tot * 100.0)
    return out


def suggestions(r, bands, axis_pct, axis_rear, lift_max):
    """照抄原程序里的判断阈值，但只说最要紧的三条。"""
    stock = "原厂" in (r["meta"].get("susp") or "")
    low, high = bands[0], bands[2]
    out = []
    if high > 30:
        out.append({
            "title": "大冲击占 %.0f%% · 高速阻尼不够" % high,
            "text": ("先换更硬/行程更大的悬挂零件，再把弹簧 +5~10%、胎压 +0.2 bar。"
                     if stock else
                     "把 shock_FL/FR 的 beamDampFast 2800→3400、RL/RR 3500→4200（各 +20%）。"),
        })
    elif low > 45:
        out.append({
            "title": "细碎颠簸占 %.0f%% · 低速阻尼主导" % low,
            "text": ("手感几乎全由低速阻尼决定：弹簧 −5%、阻尼 −1 档、胎压 −0.2 bar，再换舒适型轮胎。"
                     if stock else
                     "CDC comfort 0.60→0.50 更软、0.60→0.75 更扎实，先动低速这一档。"),
        })
    if axis_rear:
        out.append({
            "title": "后轴比前轴忙 %.0f%% · 后轴偏软" % axis_pct,
            "text": "后轴弹簧/阻尼 +10%；不能前后独立调，就把后轮胎压 +0.1 bar。",
        })
    elif axis_pct > 8:
        out.append({
            "title": "前轴比后轴忙 %.0f%% · 前轴偏软" % axis_pct,
            "text": "前轴弹簧/阻尼 +10%，或前轮胎压 +0.1 bar，先看 7500 米那一段。",
        })
    if lift_max > 2:
        out.append({
            "title": "有轮离地 %.1f%% · 阻尼或行程偏紧" % lift_max,
            "text": "按顺序试：阻尼 −1 档 → 胎压 −0.2 bar → 换行程更大的悬挂。",
        })
    if not out:
        out.append({
            "title": "没有明显异常",
            "text": "这套设定基本合理：想更舒服就降胎压/阻尼，想更稳就升弹簧/加胎压，一次只动一样。",
        })
    return out[:3]


def build_data(r):
    bands = band_pcts(r)
    rms = (r["rms_f"] + r["rms_r"]) / 2.0
    if rms < 0.15:
        vlevel = 0
    elif rms < 0.28:
        vlevel = 1
    elif rms < 0.45:
        vlevel = 2
    else:
        vlevel = 3
    verdict, vtone = VERDICTS[vlevel]

    sf, sr = r.get("sig_f", 0.0), r.get("sig_r", 0.0)
    d = ((sr / sf) - 1.0) * 100.0 if sf > 1e-6 else 0.0
    axis_pct = abs(d)
    axis_rear = d > 8
    if d > 8:
        who = "后轴比前轴忙 %.0f%%" % axis_pct
    elif d < -8:
        who = "前轴比后轴忙 %.0f%%" % axis_pct
    else:
        who = "前后轴差不多忙"
        axis_pct = 0.0
    front_share = (sf / (sf + sr) * 100.0) if (sf + sr) > 0 else 50.0

    seg = r["seg"][0] if r.get("seg") else None
    worst_d = seg["d0"] if seg else 0.0
    worst_rms = math.sqrt(seg["rms"] / seg["n"]) if (seg and seg["n"]) else 0.0
    worst_pos = (worst_d / r["dist"] * 100.0) if r.get("dist") else 0.0
    worst_pos = min(max(worst_pos, 1.6), 98.4)

    lift_max = max(r.get("air", {}).values()) if r.get("air") else 0.0
    low, mid, high = bands[0], bands[1], bands[2]
    if low >= 45:
        insight = ("<b>%.0f%%</b> 的时间减振器只在 <b>0.10 m/s</b> 以内活动 —— "
                   "手感基本由低速阻尼决定，先调这一档收益最大。" % low)
    elif high >= 30:
        insight = ("<b>%.0f%%</b> 落在高速档 —— 大冲击偏多，阻尼或行程不够用，"
                   "先把高速阻尼加上去。" % high)
    else:
        insight = ("三档分布比较均衡（%.0f / %.0f / %.0f%%）—— 低速和高速都得看，"
                   "按最颠的那一段做取舍。" % (low, mid, high))
    stock = "原厂" in (r["meta"].get("susp") or "")
    veh = " ".join((r["meta"].get("veh") or "—").split())
    cfg = " ".join((r["meta"].get("cfg") or "").split())
    if cfg in ("", "[]", "{}", "None"):
        cfg = "默认配置"
    level = r["meta"].get("level") or "—"

    data = {
        "file": os.path.basename(r["path"]),
        "vehicle": veh,
        "config": cfg,
        "level": level,
        "stock": stock,
        "dist_m": r["dist"],
        "dur_s": r["dur"],
        "points": r["n"],
        "v_avg_kmh": r["v_avg"] * 3.6,
        "v_max_kmh": r["v_max"] * 3.6,
        "rms_f": r["rms_f"],
        "rms_r": r["rms_r"],
        "rms": rms,
        "sig_f": r.get("sig_f", 0.0),
        "sig_r": r.get("sig_r", 0.0),
        "verdict": verdict,
        "verdict_level": vlevel,
        "verdict_tone": vtone,
        "bands": [
            {"name": m[2], "tag": m[3], "range": m[4], "pct": round(p, 2),
             "c1": m[5], "c2": m[6], "glow": m[7]}
            for m, p in zip(BAND_META, bands)
        ],
        "axis_text": who,
        "axis_pct": axis_pct,
        "axis_rear": axis_rear,
        "front_share": front_share,
        "rear_share": 100.0 - front_share,
        "worst_m": worst_d,
        "worst_rms": worst_rms,
        "worst_pos": worst_pos,
        "lift_max": lift_max,
        "insight": insight,
        "file_kb": os.path.getsize(r["path"]) / 1024.0,
    }
    data["tips"] = suggestions(r, bands, axis_pct, axis_rear, lift_max)

    # ── 各页共用的图数据（给前端画图，decimate 过，别把原始波形整包塞进去）──
    prof = T.decimate_pts(r["profile"], 1200) if r.get("profile") else []
    data["profile_pts"] = [[round(p[0], 1), round(p[3], 2), round(p[4] * 3.6, 1),
                            round(p[5], 3), round(p[6], 3)] for p in prof]
    svs = T.decimate_pts(r["sv"], 1200) if r.get("sv") else []
    data["sv_pts"] = [[round(p[0], 1)] + [round(v, 4) for v in p[1:5]] for p in svs]
    segs = []
    for s in sorted(r.get("seg", []), key=lambda q: q["d0"]):
        if s["n"]:
            segs.append({"d0": s["d0"], "n": s["n"],
                         "rms": round(math.sqrt(s["rms"] / s["n"]), 4),
                         "v": round(s["v"] / s["n"] * 3.6, 1)})
    data["segments"] = segs
    data["z_min"], data["z_max"] = r["z_min"], r["z_max"]
    data["climb"], data["grade"] = r["climb"], r["grade"]
    data["pct_low"], data["pct_high"] = r.get("pct_low", 0.0), r.get("pct_high", 0.0)
    data["comp_sign"] = r.get("comp_sign", 1)
    data["has_dyno"] = bool(r.get("dyno"))
    data["has_pedal"] = bool(r.get("has_pedal"))
    # 第①页的「详细分布」：4 组 × 10 桶（前/后 × 压缩/回弹 + 溢出桶）
    data["hist"] = {k: [int(x) for x in r["hist"][k]] for k in ("Fc", "Fr", "Rc", "Rr")}
    data["hist_cnt"] = {k: int(r["cnt"][k]) for k in ("Fc", "Fr", "Rc", "Rr")}
    data["bins"] = list(T.BINS)

    # ── 各页模块自己补数据字段（接口见 webui_parts/SPEC.md）──
    for _mod in PARTS.PAGES:
        try:
            _mod.build(r, data)
        except Exception as _e:  # noqa: BLE001
            data.setdefault("page_errors", []).append("%s: %s" % (getattr(_mod, "KEY", "?"), _e))
    return data


# ══════════════════════════════════════════════════════════════════════
# HTML 片段
# ══════════════════════════════════════════════════════════════════════
# 图标 / esc / 格式化函数统一在 webui_parts.common 里，这里直接用 import 进来的。


def render_chips(d):
    return (
        '<span class="chip">%s%s</span>'
        '<span class="chip">%s%s</span>'
        '<span class="chip live"><span class="dot"></span>已载入 %s 点</span>'
        % (IC["pin"], esc(d["level"]),
           IC["route"], "%s · %s" % (fmt_dist(d["dist_m"]), fmt_dur(d["dur_s"])),
           "{:,}".format(d["points"]))
    )


def render_stats(d):
    lit = d["verdict_level"] + 1
    segs = "".join('<span class="seg%s"></span>' % (" on" if i < lit else "") for i in range(4))
    s1 = """
      <article class="card stat" style="--tone:%s">
        <div class="stat-label">%s这趟路的颠簸程度</div>
        <div class="stat-value tone">%s<small>%.2f m/s</small></div>
        <div class="meter">%s</div>
        <div class="stat-foot">悬挂工作速度 RMS · 越低越平顺</div>
      </article>""" % (d["verdict_tone"], IC["pulse"], esc(d["verdict"]), d["rms"], segs)

    s2 = """
      <article class="card stat">
        <div class="stat-label">%s前后轴忙碌程度</div>
        <div class="stat-value sm">%s</div>
        <div class="balance">
          <span class="front" style="width:%.1f%%"></span>
          <span class="rear" style="width:%.1f%%"></span>
        </div>
        <div class="stat-foot">前轴 %.0f%% · 后轴 %.0f%%（按轮荷标准差 σ 算）</div>
      </article>""" % (IC["swap"], esc(d["axis_text"]),
                       d["front_share"], d["rear_share"],
                       d["front_share"], d["rear_share"])

    worst_val = ('%s<small>米处</small>' % "{:,.0f}".format(d["worst_m"])
                 if d["worst_m"] >= 1 else "起点那段")
    s3 = """
      <article class="card stat">
        <div class="stat-label">%s最颠的一段</div>
        <div class="stat-value">%s</div>
        <div class="track-mini"><span class="mk" style="left:%.2f%%"></span></div>
        <div class="stat-foot">该段 RMS %.2f m/s · 全程 %s</div>
      </article>""" % (IC["pin"], worst_val, d["worst_pos"],
                       d["worst_rms"], fmt_dist(d["dist_m"]))
    return s1 + s2 + s3


def render_bars(d):
    out = []
    for b in d["bands"]:
        out.append("""
      <div class="bar-row">
        <div class="bar-top">
          <div class="bar-title">
            <span class="bar-name">%(name)s</span>
            <span class="bar-range">%(range)s</span>
          </div>
          <span class="bar-tag">%(tag)s</span>
        </div>
        <div class="bar-body">
          <div class="track">
            <div class="fill" data-pct="%(pct).2f" style="--pct:%(pct).2f%%;--c1:%(c1)s;--c2:%(c2)s;--glow:%(glow)s"></div>
          </div>
          <div class="pct"><b>%(round)d</b><i>%%</i></div>
        </div>
      </div>""" % dict(name=esc(b["name"]), range=b["range"], tag=esc(b["tag"]),
                        pct=b["pct"], c1=b["c1"], c2=b["c2"], glow=b["glow"],
                        round=int(round(b["pct"]))))
    return "".join(out)


def render_stack(d):
    return "".join(
        '<span style="width:%.2f%%;background:linear-gradient(90deg,%s,%s)"></span>'
        % (b["pct"], b["c1"], b["c2"]) for b in d["bands"]
    )


def render_tips(d):
    items = []
    for i, t in enumerate(d["tips"], 1):
        items.append(
            '<div class="tip-item"><span class="tip-dot">%d</span><div>'
            '<div class="tip-title">%s</div><div class="tip-text">%s</div></div></div>'
            % (i, esc(t["title"]), esc(t["text"]))
        )
    return "".join(items)


def render_info(d):
    rows = [
        ("车辆", d["vehicle"]),
        ("配置", d["config"]),
        ("地图", d["level"].replace("_", " ")),
        ("里程", fmt_dist(d["dist_m"])),
        ("时长", fmt_dur(d["dur_s"])),
        ("采样", "%s 点 @ 10 Hz" % "{:,}".format(d["points"])),
        ("车速", "均 %.0f · 最高 %.0f km/h" % (d["v_avg_kmh"], d["v_max_kmh"])),
        ("文件", "%.0f KB" % d["file_kb"]),
    ]
    return "".join('<div class="kv-row"><dt>%s</dt><dd>%s</dd></div>' % (k, esc(v)) for k, v in rows)


# ══════════════════════════════════════════════════════════════════════
# 页面模板
# ══════════════════════════════════════════════════════════════════════
TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>减振器分布 · 车辆数据分析器</title>
<script>if(/still/.test(location.hash)){document.documentElement.className='still';}</script>
<style>
:root{
  --blue:#5B8FB9; --blue-2:#8FBEDD; --blue-3:#3E6B92;
  --ink:#1F2E3C; --ink-2:#4B6072; --muted:#8496A7;
  --line:rgba(91,143,185,.14);
  --card:rgba(255,255,255,.72);
  --r:16px;
  --shadow:0 20px 44px -22px rgba(46,76,105,.42), 0 2px 8px rgba(70,100,130,.06);
  --shadow-hover:0 26px 56px -22px rgba(46,76,105,.5), 0 3px 10px rgba(70,100,130,.08);
  --ease:cubic-bezier(.22,1,.36,1);
}
*,*::before,*::after{box-sizing:border-box}
html,body{height:100%;margin:0;overflow:hidden}
body{
  font-family:"Microsoft YaHei UI","Segoe UI",sans-serif;
  color:var(--ink);background:#e9f0f7;
  -webkit-font-smoothing:antialiased;user-select:none;
}
.ic{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:1.7;
  stroke-linecap:round;stroke-linejoin:round}
::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-thumb{background:rgba(91,143,185,.26);border-radius:8px}
::-webkit-scrollbar-track{background:transparent}

/* ── 背景：渐变 + 模糊色块 ───────────────────────────────── */
.bg{position:fixed;inset:0;z-index:0;overflow:hidden;
  background:linear-gradient(158deg,#f7fafd 0%,#eaf1f9 46%,#dfe9f4 100%)}
.blob{position:absolute;border-radius:50%;filter:blur(72px);will-change:transform}
.b1{width:660px;height:660px;left:-180px;top:-230px;
  background:radial-gradient(circle at 38% 38%,rgba(104,156,199,.72),rgba(104,156,199,0) 70%);
  animation:drift1 24s ease-in-out infinite}
.b2{width:600px;height:600px;right:-150px;top:30px;
  background:radial-gradient(circle at 50% 50%,rgba(152,188,220,.66),rgba(152,188,220,0) 70%);
  animation:drift2 28s ease-in-out infinite}
.b3{width:780px;height:620px;left:33%;bottom:-330px;
  background:radial-gradient(circle at 50% 50%,rgba(174,200,224,.8),rgba(174,200,224,0) 70%);
  animation:drift3 32s ease-in-out infinite}
.b4{width:460px;height:460px;left:53%;top:-200px;
  background:radial-gradient(circle at 50% 50%,rgba(124,176,214,.5),rgba(124,176,214,0) 70%);
  animation:drift1 26s ease-in-out infinite reverse}
.veil{position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(180deg,rgba(255,255,255,.34),rgba(255,255,255,0) 42%,rgba(214,230,243,.32))}
@keyframes drift1{0%,100%{transform:translate3d(0,0,0) scale(1)}50%{transform:translate3d(46px,34px,0) scale(1.07)}}
@keyframes drift2{0%,100%{transform:translate3d(0,0,0) scale(1)}50%{transform:translate3d(-40px,28px,0) scale(1.05)}}
@keyframes drift3{0%,100%{transform:translate3d(0,0,0) scale(1)}50%{transform:translate3d(30px,-30px,0) scale(1.04)}}

/* ── 布局 ────────────────────────────────────────────── */
.app{position:relative;z-index:1;display:flex;gap:16px;height:100vh;padding:16px 18px 16px 16px}
.main{flex:1;min-width:0;display:flex;flex-direction:column;gap:16px;min-height:0}

/* ── 左侧导航条 ───────────────────────────────────────── */
/* position+z-index：rail 有 backdrop-filter 会自成层叠上下文，不加这行 .nav 的
   悬浮提示会被后面的卡片（card 也有 backdrop-filter）盖住，只露出一角 */
.rail{position:relative;z-index:5;flex:0 0 76px;width:76px;display:flex;flex-direction:column;align-items:center;gap:2px;
  padding:18px 0 16px;border-radius:22px;
  background:rgba(255,255,255,.58);border:1px solid rgba(255,255,255,.9);
  -webkit-backdrop-filter:blur(24px) saturate(160%);backdrop-filter:blur(24px) saturate(160%);
  box-shadow:0 24px 54px -28px rgba(40,70,100,.55), inset 0 1px 0 rgba(255,255,255,.95)}
.logo{width:42px;height:42px;border-radius:13px;margin-bottom:14px;display:grid;place-items:center;color:#fff;
  background:linear-gradient(150deg,#86B8DC,#4A7398);
  box-shadow:0 12px 22px -10px rgba(74,115,152,.85), inset 0 1px 0 rgba(255,255,255,.45)}
.logo svg{width:23px;height:23px;fill:none;stroke:currentColor;stroke-width:1.9;stroke-linecap:round}
.nav{position:relative;width:48px;height:46px;border:0;border-radius:13px;background:transparent;
  display:grid;place-items:center;color:#6F8497;cursor:pointer;
  transition:background .28s var(--ease),color .28s,transform .28s var(--ease),box-shadow .28s}
.nav .ic{width:22px;height:22px;stroke-width:1.8}
.nav:hover{background:rgba(255,255,255,.92);color:var(--blue-3);transform:translateY(-1px);
  box-shadow:0 10px 20px -12px rgba(50,80,110,.7)}
.nav.active{background:#fff;color:var(--blue);
  box-shadow:0 12px 24px -12px rgba(91,143,185,.8), inset 0 0 0 1px rgba(91,143,185,.1)}
.nav.active::before{content:"";position:absolute;left:-14px;top:50%;transform:translateY(-50%);
  width:3px;height:20px;border-radius:2px;
  background:linear-gradient(180deg,var(--blue-2),var(--blue));
  box-shadow:0 0 12px rgba(91,143,185,.8)}
.nav[data-tip]:hover::after{content:attr(data-tip);position:absolute;left:58px;top:50%;
  transform:translateY(-50%);padding:6px 11px;border-radius:8px;white-space:nowrap;
  background:rgba(31,46,60,.92);color:#fff;font-size:11.5px;letter-spacing:.02em;
  box-shadow:0 10px 24px -8px rgba(20,40,60,.6);z-index:60}
.nav-div{width:26px;height:1px;background:var(--line);margin:9px 0}
.rail .grow{flex:1}

/* ── 页面标题 ─────────────────────────────────────────── */
.head{flex:0 0 auto;display:flex;align-items:flex-end;justify-content:space-between;gap:24px;padding:2px 4px 0}
.crumb{display:flex;align-items:center;gap:8px;font-size:11.8px;color:var(--muted);letter-spacing:.02em}
.crumb i{font-style:normal;opacity:.5}
.crumb b{font-weight:600;color:var(--ink-2);max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
h1{margin:9px 0 7px;display:flex;align-items:center;gap:11px;
  font-size:27px;font-weight:700;letter-spacing:.01em;color:var(--ink);line-height:1.1}
.badge{font-size:11.5px;font-weight:600;letter-spacing:.02em;padding:5px 10px;border-radius:999px;
  color:var(--blue-3);background:rgba(91,143,185,.12);border:1px solid rgba(91,143,185,.18)}
.sub{margin:0;font-size:12.6px;color:var(--ink-2);letter-spacing:.01em}
.sub em{font-style:normal;color:var(--blue-3);font-weight:600}
.head-right{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;padding-bottom:3px}
.chip{display:inline-flex;align-items:center;gap:7px;height:34px;padding:0 13px;border-radius:11px;
  font-size:12.3px;color:var(--ink-2);background:rgba(255,255,255,.66);
  border:1px solid rgba(255,255,255,.9);box-shadow:0 8px 20px -14px rgba(50,80,110,.7);
  -webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px)}
.chip .ic{width:14px;height:14px;color:var(--blue);opacity:.9}
.chip.live{color:#2F6B52;background:rgba(240,250,245,.72)}
.chip .dot{width:6px;height:6px;border-radius:50%;background:#49B07E;
  box-shadow:0 0 0 3px rgba(73,176,126,.16);animation:pulse 2.6s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.45}}

/* ── 卡片 ────────────────────────────────────────────── */
.card{position:relative;border-radius:var(--r);
  background:var(--card);border:1px solid rgba(255,255,255,.86);
  -webkit-backdrop-filter:blur(20px) saturate(165%);backdrop-filter:blur(20px) saturate(165%);
  box-shadow:var(--shadow), inset 0 1px 0 rgba(255,255,255,.9);
  transition:transform .4s var(--ease),box-shadow .4s var(--ease),background .4s}
.card:hover{transform:translateY(-2px);box-shadow:var(--shadow-hover), inset 0 1px 0 rgba(255,255,255,.95);
  background:rgba(255,255,255,.79)}

/* ── 顶部统计 ─────────────────────────────────────────── */
.stats{flex:0 0 auto;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
.stat{display:flex;flex-direction:column;gap:9px;padding:15px 20px 13px;min-height:132px}
.stat-label{display:flex;align-items:center;gap:8px;font-size:11.8px;color:var(--muted);letter-spacing:.05em}
.stat-label .ic{width:15px;height:15px;color:var(--blue);opacity:.85}
.stat-value{display:flex;align-items:baseline;gap:8px;font-size:26px;font-weight:700;letter-spacing:-.01em;
  line-height:1.12;font-variant-numeric:tabular-nums;font-family:"Segoe UI","Microsoft YaHei UI",sans-serif}
.stat-value.sm{font-size:21px;letter-spacing:0;font-family:"Microsoft YaHei UI","Segoe UI",sans-serif}
.stat-value small{font-size:12.5px;font-weight:500;color:var(--muted);letter-spacing:.01em;
  font-family:"Microsoft YaHei UI","Segoe UI",sans-serif}
.stat-value.tone{color:var(--tone)}
.meter{display:flex;gap:5px;height:6px;margin-top:1px}
.meter .seg{flex:1;border-radius:4px;background:rgba(91,143,185,.13)}
.meter .seg.on{background:var(--tone);box-shadow:0 4px 12px -4px var(--tone)}
.balance{display:flex;height:8px;border-radius:999px;overflow:hidden;margin-top:2px;
  background:rgba(91,143,185,.1);box-shadow:inset 0 1px 2px rgba(60,90,120,.12)}
.balance .front{background:linear-gradient(90deg,#5B8FB9,#8FBEDD);transition:width .9s var(--ease)}
.balance .rear{background:rgba(91,143,185,.4);transition:width .9s var(--ease)}
.track-mini{position:relative;height:5px;border-radius:999px;margin-top:5px;
  background:linear-gradient(90deg,rgba(91,143,185,.13),rgba(91,143,185,.26))}
.track-mini .mk{position:absolute;top:50%;transform:translate(-50%,-50%);width:12px;height:12px;
  border-radius:50%;background:#fff;border:3px solid var(--blue);
  box-shadow:0 5px 12px -2px rgba(91,143,185,.75)}
.stat-foot{margin-top:auto;font-size:11.5px;color:var(--muted);letter-spacing:.01em}

/* ── 主区域 ───────────────────────────────────────────── */
.grid{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 388px;gap:16px}

/* 三段占比条 */
.bars-card{display:flex;flex-direction:column;padding:22px 26px 20px;min-height:0}
.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}
.panel-head h2{margin:0;font-size:16.5px;font-weight:700;letter-spacing:.01em;color:var(--ink)}
.panel-head p{margin:5px 0 0;font-size:11.9px;color:var(--muted);letter-spacing:.01em}
.stack-wrap{display:flex;flex-direction:column;align-items:flex-end;gap:7px;padding-top:3px}
.stack{display:flex;gap:3px;width:206px;height:9px}
.stack span{border-radius:999px;transition:width .9s var(--ease);box-shadow:inset 0 1px 0 rgba(255,255,255,.35)}
.stack-cap{font-size:10.8px;color:var(--muted);letter-spacing:.06em}
.bars{flex:1;display:flex;flex-direction:column;justify-content:space-evenly;gap:0;min-height:0;margin:2px 0 0}
.bar-row{padding:16px 18px;border-radius:14px;background:rgba(255,255,255,.5);
  border:1px solid rgba(255,255,255,.7);box-shadow:0 10px 24px -22px rgba(50,80,110,.55);
  transition:background .3s,transform .3s var(--ease),box-shadow .3s}
.bar-row:hover{background:rgba(255,255,255,.78);transform:translateY(-1px);
  box-shadow:0 14px 28px -20px rgba(50,80,110,.6)}
.bar-top{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:11px}
.bar-title{display:flex;align-items:baseline;gap:10px;min-width:0}
.bar-name{font-size:15px;font-weight:600;color:var(--ink);letter-spacing:.01em}
.bar-range{font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums}
.bar-tag{flex:0 0 auto;font-size:11px;font-weight:600;letter-spacing:.03em;padding:3.5px 9px;border-radius:999px;
  color:var(--blue-3);background:rgba(91,143,185,.1);border:1px solid rgba(91,143,185,.1)}
.bar-body{display:flex;align-items:center;gap:20px}
.track{position:relative;flex:1;height:24px;border-radius:999px;background:rgba(91,143,185,.1);
  box-shadow:inset 0 1px 3px rgba(60,90,120,.1)}
.fill{position:relative;height:100%;width:0;border-radius:999px;
  background:linear-gradient(90deg,var(--c1),var(--c2));
  box-shadow:0 10px 22px -10px var(--glow);
  transition:width 1.2s cubic-bezier(.16,1,.3,1)}
.fill::after{content:"";position:absolute;inset:0;border-radius:inherit;
  background:linear-gradient(180deg,rgba(255,255,255,.55),rgba(255,255,255,.06) 58%,rgba(255,255,255,0))}
.pct{flex:0 0 106px;display:flex;align-items:baseline;justify-content:flex-end;gap:2px;
  font-variant-numeric:tabular-nums;font-family:"Segoe UI","Microsoft YaHei UI",sans-serif}
.pct b{font-size:40px;font-weight:700;line-height:1;letter-spacing:-.02em;color:var(--ink)}
.pct i{font-style:normal;font-size:14.5px;font-weight:600;color:var(--muted);margin-left:1px}
.panel-foot{display:flex;align-items:center;justify-content:space-between;gap:20px;
  padding-top:15px;border-top:1px solid var(--line);font-size:11.6px;color:var(--muted)}
.insight{display:flex;align-items:flex-start;gap:11px;margin:12px 0 14px;padding:12px 15px;
  border-radius:13px;font-size:11.9px;line-height:1.62;color:var(--ink-2);
  background:linear-gradient(90deg,rgba(91,143,185,.10),rgba(91,143,185,.035));
  border:1px solid rgba(91,143,185,.12)}
.insight .ic{flex:0 0 18px;width:18px;height:18px;color:var(--blue);margin-top:1px}
.insight b{color:var(--ink);font-weight:600}
.panel-foot .src{max-width:46%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  font-variant-numeric:tabular-nums;opacity:.85}

/* 右栏 */
.side{display:flex;flex-direction:column;justify-content:flex-start;gap:16px;min-height:0;overflow:auto;padding-right:2px}
.side .card{flex:0 0 auto;padding:17px 20px 15px}
.side .card:last-child{flex:1 0 auto}
.mini-chip{font-size:10.8px;font-weight:600;color:var(--blue-3);padding:4px 9px;border-radius:999px;
  background:rgba(91,143,185,.1);border:1px solid rgba(91,143,185,.12);white-space:nowrap}
.tips-list{margin-top:6px}
.tip-item{display:flex;gap:11px;padding:9px 0;border-bottom:1px dashed var(--line)}
.tip-item:last-child{border-bottom:0;padding-bottom:2px}
.tip-dot{flex:0 0 24px;height:24px;border-radius:8px;display:grid;place-items:center;
  font-size:11.5px;font-weight:700;color:var(--blue-3);background:rgba(91,143,185,.12);
  font-variant-numeric:tabular-nums}
.tip-title{font-size:12.6px;font-weight:600;color:var(--ink);margin-bottom:4px;line-height:1.35}
.tip-text{font-size:11.6px;line-height:1.62;color:var(--ink-2)}
.kv{margin:10px 0 0}
.kv-row{display:flex;align-items:baseline;justify-content:space-between;gap:14px;
  padding:6.5px 0;border-bottom:1px dashed var(--line);font-size:12px}
.kv-row:last-child{border-bottom:0;padding-bottom:0}
.kv-row dt{color:var(--muted);flex:0 0 auto;letter-spacing:.03em}
.kv-row dd{margin:0;color:var(--ink);font-weight:500;text-align:right;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-variant-numeric:tabular-nums}

/* toast */
#toast{position:fixed;left:50%;bottom:30px;z-index:99;transform:translate(-50%,14px);opacity:0;
  pointer-events:none;padding:10px 18px;border-radius:12px;font-size:12.3px;color:#fff;
  background:rgba(31,46,60,.9);box-shadow:0 18px 44px -16px rgba(20,40,60,.65);
  -webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);
  transition:opacity .35s var(--ease),transform .35s var(--ease)}
#toast.show{opacity:1;transform:translate(-50%,0)}

/* 入场动画：backwards 让动画结束后样式回到常规，hover 才生效 */
@keyframes rise{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
.rail{animation:rise .7s .02s var(--ease) backwards}
.head{animation:rise .7s .08s var(--ease) backwards}
.stat:nth-child(1){animation:rise .7s .13s var(--ease) backwards}
.stat:nth-child(2){animation:rise .7s .18s var(--ease) backwards}
.stat:nth-child(3){animation:rise .7s .23s var(--ease) backwards}
.bars-card{animation:rise .7s .26s var(--ease) backwards}
.side .card:nth-child(1){animation:rise .7s .3s var(--ease) backwards}
.side .card:nth-child(2){animation:rise .7s .34s var(--ease) backwards}

@media (max-width:1240px){
  .grid{grid-template-columns:minmax(0,1fr)}
  .side{flex-direction:row;overflow:visible}
  .side .card{flex:1}
  .head-right .chip:nth-child(2){display:none}
}
/* 小窗口（含 pywebview 最小尺寸 1120x720）：整页允许纵向滚动，别把内容压没 */
@media (max-width:1240px),(max-height:820px){
  html,body{overflow-y:auto;overflow-x:hidden}
  .app{height:auto;min-height:100vh}
  .main{overflow:visible}
  .page{flex:0 0 auto}
  .page-body{flex:0 0 auto}
  .grid{flex:0 0 auto;min-height:0}
  .bars-card{min-height:640px}
  .chart-card{min-height:460px}
  .cmp-result{grid-template-columns:minmax(0,1fr);grid-template-rows:auto}
  .cmp-card{min-height:260px}
}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
  .fill{width:var(--pct)}
}
/* 截图/无动画模式：url 末尾加 #still */
html.still *{animation:none!important;transition:none!important}
html.still .fill{width:var(--pct)}

/* ── 多页框架 ─────────────────────────────────────────── */
[hidden]{display:none!important}
.page{display:none;flex-direction:column;gap:16px;flex:1;min-height:0}
.page.active{display:flex;animation:pagein .42s var(--ease)}
@keyframes pagein{from{opacity:0;transform:translateY(9px)}to{opacity:1;transform:translateY(0)}}
.page-body{flex:1;min-height:0;display:flex;flex-direction:column;gap:16px}
html.still .page.active{animation:none}

/* ── 通用卡片 / 图表 / 图例 / 空状态（各页共用）──────── */
.page-card{display:flex;flex-direction:column;padding:18px 22px;min-height:0}
.chart-card{display:flex;flex-direction:column;padding:18px 22px;min-height:0}
.chart-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:8px}
.chart-head h2{margin:0;font-size:16.5px;font-weight:700;letter-spacing:.01em;color:var(--ink)}
.chart-head p{margin:5px 0 0;font-size:11.9px;color:var(--muted);letter-spacing:.01em}
.chart{position:relative;width:100%;flex:1;min-height:180px}
.ck-canvas{display:block;cursor:crosshair}
.ck-canvas.ck-dragging{cursor:grabbing}
#chart-tip{position:fixed;z-index:120;display:none;pointer-events:none;
  background:rgba(31,46,60,.94);color:#fff;border-radius:10px;padding:8px 11px;
  font-size:12px;line-height:1.7;letter-spacing:.01em;
  box-shadow:0 14px 34px -12px rgba(20,40,60,.7);
  -webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px)}
#chart-tip .ck-x{color:#9fc0da;margin-bottom:2px}
#chart-tip .ck-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}
.legend{display:flex;flex-wrap:wrap;gap:15px;font-size:11.8px;color:var(--ink-2)}
.legend .lg{display:inline-flex;align-items:center;gap:6px}
.legend .lg i{width:16px;height:3px;border-radius:2px;display:inline-block}
.empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;
  min-height:280px;color:var(--muted);text-align:center;padding:30px}
.empty-ic .ic{width:40px;height:40px;stroke-width:1.2;color:var(--blue-2)}
.empty-title{font-size:15px;font-weight:600;color:var(--ink-2)}
.empty-text{font-size:12.5px;line-height:1.7;max-width:430px}
.hint{display:flex;align-items:center;gap:7px;font-size:11.5px;color:var(--muted)}
.hint .ic{width:13px;height:13px;color:var(--blue);opacity:.8}

/* ── 换数据按钮 + 弹层 ─────────────────────────────────── */
.chip-btn{cursor:pointer;border:1px solid rgba(91,143,185,.22);font-family:inherit;
  transition:background .2s,transform .2s var(--ease)}
.chip-btn:hover{background:#fff;transform:translateY(-1px)}
.play-btn{color:var(--blue-3);background:rgba(91,143,185,.13);border-color:rgba(91,143,185,.28)}
.play-btn:hover{background:rgba(91,143,185,.22)}
.live-chip{cursor:default;font-variant-numeric:tabular-nums}
.live-chip.live-rec{color:#2E8B6A;background:rgba(62,158,123,.14);border-color:rgba(62,158,123,.3);font-weight:600}
.live-chip.live-idle{color:var(--muted);background:rgba(91,143,185,.06)}
.live-chip.live-wait{color:#8A6A2F;background:rgba(217,162,74,.16);border-color:rgba(217,162,74,.34)}
.play-btn .ic{width:13px;height:13px;color:var(--blue-3)}
.modal{position:fixed;inset:0;z-index:200;display:flex;align-items:center;justify-content:center;
  background:rgba(24,38,52,.34);-webkit-backdrop-filter:blur(5px);backdrop-filter:blur(5px)}
.modal-card{width:min(660px,86vw);max-height:78vh;display:flex;flex-direction:column;
  background:rgba(248,251,255,.98);border-radius:18px;border:1px solid rgba(255,255,255,.9);
  box-shadow:0 34px 90px -34px rgba(20,40,60,.65);overflow:hidden}
.modal-head{display:flex;align-items:center;justify-content:space-between;padding:16px 20px 10px}
.modal-head h3{margin:0;font-size:16px;font-weight:700;letter-spacing:.01em}
.modal-x{width:30px;height:30px;border:0;border-radius:9px;cursor:pointer;font-size:16px;
  color:var(--ink-2);background:rgba(91,143,185,.12);font-family:inherit}
.modal-x:hover{background:rgba(91,143,185,.2)}
.modal-body{display:flex;flex-direction:column;gap:12px;padding:0 20px 18px;min-height:0}
.modal-list{display:flex;flex-direction:column;gap:6px;overflow:auto;max-height:54vh;padding-right:4px}
.data-item{display:flex;align-items:center;gap:8px;padding:9px 11px 9px 13px;
  border:1px solid rgba(91,143,185,.16);border-radius:11px;background:rgba(255,255,255,.8);
  font-family:inherit;text-align:left;transition:background .2s,border-color .2s}
.data-item:hover{background:#fff;border-color:rgba(91,143,185,.42)}
.data-item.cur{border-color:rgba(91,143,185,.55);background:rgba(91,143,185,.09)}
.data-open{flex:1;min-width:0;display:flex;flex-direction:column;align-items:flex-start;gap:3px;
  border:0;background:transparent;padding:0;font-family:inherit;text-align:left;cursor:pointer}
.data-open .fname{font-size:12.8px;font-weight:600;color:var(--ink)}
.data-open .fmeta{font-size:11px;color:var(--muted)}
.data-del{flex:0 0 auto;width:29px;height:29px;border:0;border-radius:9px;cursor:pointer;
  color:var(--muted);background:rgba(91,143,185,.08);font-family:inherit;font-size:14px;line-height:1;
  transition:color .2s,background .2s}
.data-del:hover{color:#c0503f;background:rgba(208,106,92,.16)}
.data-item.confirm{flex-direction:column;align-items:stretch;gap:8px;
  border-color:rgba(208,106,92,.42);background:rgba(208,106,92,.06)}
.confirm-row{display:flex;align-items:center;gap:10px;justify-content:space-between}
.confirm-txt{font-size:12.2px;color:var(--ink-2);line-height:1.5}
.confirm-btns{display:flex;gap:6px;flex:0 0 auto}
.confirm-btns button{height:27px;padding:0 11px;border:0;border-radius:8px;cursor:pointer;
  font-family:inherit;font-size:11.8px;font-weight:600}
.confirm-yes{color:#fff;background:#c0503f}
.confirm-yes:hover{background:#a94334}
.confirm-no{color:var(--ink-2);background:rgba(91,143,185,.12)}
.confirm-no:hover{background:rgba(91,143,185,.2)}
.modal-foot{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.modal-foot .hint{margin:0}
.modal-foot button{height:34px;padding:0 16px;border:0;border-radius:10px;cursor:pointer;
  font-family:inherit;font-size:12.3px;font-weight:600;color:#fff;
  background:linear-gradient(150deg,#7FB2D6,#4A7398)}
.modal-foot button:hover{transform:translateY(-1px)}

/* ── 第①页：详细分布（4 组 × 10 桶）──────────────────── */
.hist-detail{flex:0 0 auto;margin-top:10px;padding-top:12px;border-top:1px solid var(--line)}
.hd-head{display:flex;align-items:baseline;gap:10px;margin-bottom:8px}
.hd-title{font-size:13px;font-weight:600;color:var(--ink-2);letter-spacing:.02em}
.hd-note{font-size:10.8px;color:var(--muted)}
.hd-axis{margin-left:auto;font-size:10px;color:#a3aebd;letter-spacing:.2em}
.hd-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px}
.hd-group{display:flex;flex-direction:column;gap:5px;min-width:0}
.hd-bars{display:flex;align-items:flex-end;gap:2px;height:64px;
  border-bottom:1px solid rgba(91,143,185,.28)}
.hd-bar{flex:1;min-height:1px;border-radius:3px 3px 0 0;
  background:linear-gradient(180deg,var(--c1),var(--c2));transition:opacity .2s}
.hd-bar:hover{opacity:.72}
.hd-label{display:flex;align-items:center;gap:6px;font-size:10.6px;color:var(--muted);white-space:nowrap}
.hd-label i{width:9px;height:9px;border-radius:2px;display:inline-block}
__PAGE_CSS__
</style>
</head>
<body>
<div class="bg">
  <span class="blob b1"></span><span class="blob b2"></span>
  <span class="blob b3"></span><span class="blob b4"></span>
  <span class="veil"></span>
</div>

<div class="app">
  <aside class="rail">
    <div class="logo" title="车辆数据分析器">
      <svg viewBox="0 0 24 24"><path d="M4 14c2.6 0 2.6-4.2 5.2-4.2S11.8 14 14.4 14s2.6-4.2 5.2-4.2"/></svg>
    </div>
    __NAV__
    <span class="nav-div"></span>
    <button class="nav" data-tip="设置" data-page="settings">__ICON_SLIDERS__</button>
    <span class="grow"></span>
    <button class="nav" data-tip="使用说明" data-page="help">__ICON_HELP__</button>
  </aside>

  <main class="main" id="main">
__PAGES__
  </main>
</div>

<div id="toast"></div>

<div id="data-modal" class="modal" hidden>
  <div class="modal-card">
    <div class="modal-head">
      <h3>换一份数据</h3>
      <button class="modal-x" id="data-close" title="关闭">×</button>
    </div>
    <div class="modal-body">
      <div class="modal-list" id="data-list"></div>
      <div class="modal-foot">
        <button id="data-browse">选择 CSV 文件…</button>
        <button id="data-export" title="让游戏把当前抓包导出成 CSV（游戏内面板导出没反应时用这个）">⤓ 让游戏导出当前抓包</button>
        <span class="hint" id="data-path-hint"></span>
      </div>
    </div>
  </div>
</div>
<noscript><style>.fill{width:var(--pct)}</style></noscript>
<script>
const DATA = __DATA_JSON__;
__CHARTKIT_JS__
__PAGE_JS__
(function () {
  var rows = Array.prototype.slice.call(document.querySelectorAll('.bar-row'));
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var still = document.documentElement.classList.contains('still');

  function easeOut(t) { return 1 - Math.pow(1 - t, 3); }

  function growRow(row, i) {
    var fill = row.querySelector('.fill');
    var num = row.querySelector('.pct b');
    var pct = parseFloat(fill.dataset.pct) || 0;
    var dur = 1200;
    setTimeout(function () {
      fill.style.width = pct.toFixed(2) + '%';
      if (!num) return;
      var t0 = performance.now();
      function step(now) {
        var t = Math.min(1, (now - t0) / dur);
        num.textContent = Math.round(pct * easeOut(t));
        if (t < 1) requestAnimationFrame(step);
        else num.textContent = Math.round(pct);
      }
      requestAnimationFrame(step);
    }, 170 + i * 130);
  }

  if (still) {
    rows.forEach(function (row) {
      var f = row.querySelector('.fill');
      f.style.width = (parseFloat(f.dataset.pct) || 0).toFixed(2) + '%';
    });
  } else {
    rows.forEach(function (row) {
      var num = row.querySelector('.pct b');
      if (num) num.textContent = '0';
    });
    if (reduce) {
      rows.forEach(function (row) {
        var f = row.querySelector('.fill');
        f.style.transition = 'none';
        f.style.width = (parseFloat(f.dataset.pct) || 0).toFixed(2) + '%';
        var n = row.querySelector('.pct b');
        if (n) n.textContent = Math.round(parseFloat(f.dataset.pct) || 0);
      });
    } else {
      requestAnimationFrame(function () {
        rows.forEach(growRow);
      });
    }
  }

})();

/* ── 页面切换框架 ─────────────────────────────────────── */
(function () {
  var pages = Array.prototype.slice.call(document.querySelectorAll('.page'));
  var navs = Array.prototype.slice.call(document.querySelectorAll('.nav[data-page]'));
  var inited = {};
  var toastEl = document.getElementById('toast');

  function toast(msg) {
    if (!toastEl) return;
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    clearTimeout(toastEl._tm);
    toastEl._tm = setTimeout(function () { toastEl.classList.remove('show'); }, 2400);
  }
  window.__toast = toast;

  function initPage(key, page) {
    var init = window.PAGE_INIT && window.PAGE_INIT[key];
    if (typeof init !== 'function') return;
    try {
      init(page, DATA);
    } catch (e) {
      console.error('[page init failed]', key, e);
    }
  }

  function show(key, opts) {
    var page = null;
    pages.forEach(function (p) { if (p.dataset.page === key) page = p; });
    if (!page) { toast('这一页还没做'); return; }
    pages.forEach(function (p) { p.classList.toggle('active', p === page); });
    navs.forEach(function (n) { n.classList.toggle('active', n.dataset.page === key); });
    document.title = (page.dataset.title || '车辆数据分析器') + ' · 车辆数据分析器';
    var _tip = document.getElementById('chart-tip');
    if (_tip) _tip.style.display = 'none';
    if (!inited[key]) { inited[key] = true; initPage(key, page); }
    if (!opts || opts.push !== false) {
      try { history.replaceState(null, '', '#' + key); } catch (e) { /* file:// 下可能失败，忽略 */ }
    }
    if (window.pywebview && window.pywebview.api && window.pywebview.api.set_page) {
      try { window.pywebview.api.set_page(key); } catch (e) { /* ignore */ }
    }
    window.dispatchEvent(new Event('page:shown'));
  }
  window.showPage = show;

  navs.forEach(function (btn) {
    btn.addEventListener('click', function () { show(btn.dataset.page); });
  });
  Array.prototype.forEach.call(document.querySelectorAll('.nav:not([data-page])'), function (btn) {
    btn.addEventListener('click', function () {
      toast('「' + (btn.dataset.tip || '') + '」页面还没做');
    });
  });

  var initial = (location.hash || '').replace('#', '');
  var ok = pages.some(function (p) { return p.dataset.page === initial; });
  show(ok ? initial : '__ACTIVE_PAGE__', { push: false });
})();

/* ── 换数据弹层 ─────────────────────────────────────── */
(function () {
  var modal = document.getElementById('data-modal');
  var listEl = document.getElementById('data-list');
  var pathHint = document.getElementById('data-path-hint');
  if (!modal) return;

  function bridgeReady() {
    return !!(window.pywebview && window.pywebview.api && window.pywebview.api.open_csv);
  }
  function toast(msg) { if (window.__toast) window.__toast(msg); }
  function close() { modal.hidden = true; }

  function open() {
    var _tip = document.getElementById('chart-tip');
    if (_tip) _tip.style.display = 'none';
    var items = DATA.csv_list || [];
    var cur = DATA.file || '';
    listEl.innerHTML = items.length ? items.map(function (it) {
      var cls = it.name === cur ? 'data-item cur' : 'data-item';
      var when = '';
      try { when = new Date(it.mtime * 1000).toLocaleString(); } catch (e) { when = ''; }
      var p = String(it.path).replace(/"/g, '&quot;');
      var nm = String(it.name).replace(/"/g, '&quot;');
      return '<div class="' + cls + '">' +
        '<button class="data-open" data-path="' + p + '">' +
        '<span class="fname">' + it.name + '</span>' +
        '<span class="fmeta">' + it.kb + ' KB · ' + when + '</span></button>' +
        '<button class="data-del" data-path="' + p + '" data-name="' + nm + '" ' +
        'title="删除这份抓包（连同同名 .txt 摘要）">✕</button></div>';
    }).join('') : '<div class="empty-text">数据目录里没有 CSV 文件</div>';
    modal.hidden = false;
  }

  // ── 每 3 秒问一次：新数据 / 游戏状态 ──────────────────────
  function liveChip() {
    var wrap = document.querySelector('.head-right');
    if (!wrap) return null;
    var el = document.getElementById('live-status');
    if (!el) {
      el = document.createElement('span');
      el.id = 'live-status';
      el.className = 'chip live-chip live-idle';
      el.textContent = '游戏没开';
      var anchor = wrap.querySelector('#launch-game');
      wrap.insertBefore(el, anchor || wrap.firstChild);
    }
    return el;
  }

  function updateLive(status) {
    var el = liveChip();
    if (!el || !status) return;
    el.classList.remove('live-rec', 'live-idle');
    if (!status.alive) {
      el.classList.add('live-idle');
      var km = (status.dist / 1000).toFixed(2) + ' km';
      if (status.game) {
        el.classList.add('live-wait');
        el.textContent = status.samples
          ? ('游戏在跑 · 等待抓包数据（上次 ' + km + ' / ' + status.samples + ' 点）')
          : '游戏在跑 · 等待进入地图';
      } else {
        el.textContent = status.samples ? ('游戏没开 · 上次 ' + km + ' / ' + status.samples + ' 点')
                                        : '游戏没开';
      }
      return;
    }
    if (status.recording) {
      el.classList.add('live-rec');
      el.textContent = '● 正在记录 ' + (status.dist / 1000).toFixed(2) + ' km / ' + status.samples + ' 点';
    } else {
      el.textContent = '游戏在跑 · 抓包已停（' + (status.samples || 0) + ' 点）';
    }
  }

  function pollLive() {
    if (!bridgeReady()) return;
    window.pywebview.api.poll().then(function (res) {
      if (!res) return;
      updateLive(res.status);
      if (res.moved) {
        toast('已从游戏目录导入 ' + res.moved + ' 份新抓包');
      }
      if (res.auto_loaded) {
        toast('检测到新数据「' + res.auto_name + '」，正在自动读取…');
      } else if (res.new_available) {
        toast('检测到新数据「' + res.newest_name + '」，点右上角「换数据」打开');
      }
    }).catch(function () {});
  }
  setTimeout(pollLive, 1200);
  setInterval(pollLive, 3000);

  function launchGame(mode) {
    if (!bridgeReady()) { toast('静态预览不能启动游戏，请用真窗口'); return; }
    mode = mode || 'steam';
    toast(mode === 'direct' ? '正在直接启动游戏（非 Steam）…' : '正在通过 Steam 启动游戏…');
    window.pywebview.api.launch_game(mode).then(function (res) {
      if (!res || !res.ok) toast('启动失败：' + ((res && res.message) || '未知错误'));
      else toast(res.message);
    }).catch(function (err) { toast('启动失败：' + err); });
  }

  function confirmDelete(btn) {
    var row = btn.closest('.data-item');
    if (!row) return;
    var path = btn.getAttribute('data-path');
    var name = btn.getAttribute('data-name') || '';
    row.classList.add('confirm');
    row.innerHTML =
      '<div class="confirm-row"><div class="confirm-txt">删除「' + name +
      '」？会一起删掉同名 .txt 摘要，删了找不回来。</div>' +
      '<div class="confirm-btns">' +
      '<button class="confirm-no" type="button">取消</button>' +
      '<button class="confirm-yes" type="button" data-path="' + path + '">确认删除</button>' +
      '</div></div>';
  }

  function doDelete(path) {
    if (!bridgeReady()) { toast('静态预览不能删文件，请用真窗口'); return; }
    window.pywebview.api.delete_csv(path).then(function (res) {
      if (!res || !res.ok) {
        toast('删除失败：' + ((res && res.error) || '未知错误'));
        open();
        return;
      }
      toast('已删除 ' + (res.deleted || []).join('、'));
      if (res.was_current && res.next) {
        window.pywebview.api.open_csv(res.next);
        return;
      }
      if (res.was_current) toast('已删除当前这份，数据目录里没有别的 CSV 了');
      window.pywebview.api.list_csvs().then(function (list) {
        DATA.csv_list = list || [];
        open();
      }).catch(function () { open(); });
    }).catch(function (err) { toast('删除失败：' + err); });
  }

  document.addEventListener('click', function (e) {
    if (e.target.closest('#launch-game-direct')) { launchGame('direct'); return; }
    if (e.target.closest('#launch-game')) { launchGame('steam'); return; }
    if (e.target.closest('#open-data')) { open(); return; }
    if (e.target.closest('#data-close') || e.target === modal) { close(); return; }
    var openBtn = e.target.closest('.data-open');
    if (openBtn) {
      var path = openBtn.getAttribute('data-path');
      close();
      if (!bridgeReady()) { toast('静态预览不能换数据，请用真窗口'); return; }
      toast('正在读取 ' + openBtn.querySelector('.fname').textContent + ' …');
      window.pywebview.api.open_csv(path).then(function (res) {
        if (!res || !res.ok) toast('读取失败：' + ((res && res.error) || '未知错误'));
      }).catch(function (err) { toast('读取失败：' + err); });
      return;
    }
    var delBtn = e.target.closest('.data-del');
    if (delBtn) {
      confirmDelete(delBtn);
      return;
    }
    var yes = e.target.closest('.confirm-yes');
    if (yes) { doDelete(yes.getAttribute('data-path')); return; }
    if (e.target.closest('.confirm-no')) { open(); return; }
    if (e.target.closest('#data-export')) {
      if (!bridgeReady()) { toast('真窗口里才能让游戏导出'); return; }
      toast('已向游戏发送导出命令…');
      window.pywebview.api.export_game_data().then(function (r) {
        if (!r || !r.ok) { toast('发送失败：' + ((r && r.error) || '未知错误')); return; }
        toast(r.message || '已发送，几秒后自动导入');
        setTimeout(pollLive, 2500);
        setTimeout(pollLive, 6000);
      }).catch(function (err) { toast('发送失败：' + err); });
      return;
    }
    if (e.target.closest('#data-browse')) {
      if (!bridgeReady()) { toast('静态预览不能选文件，请用真窗口'); return; }
      window.pywebview.api.pick_csv_file().then(function (res) {
        if (res && res.cancelled) return;
        if (!res || !res.ok) toast('打开失败：' + ((res && res.error) || '未知错误'));
      }).catch(function (err) { toast('打开失败：' + err); });
    }
  });

  if (!bridgeReady()) {
    pathHint.textContent = '静态预览：选文件/换数据要在真窗口里操作';
  } else {
    pathHint.textContent = '也可以直接选数据目录外的 CSV';
  }
  window.__openDataModal = open;
})();
</script>
</body>
</html>
"""


# ── 页面组装 ─────────────────────────────────────────────────────────
HIST_DETAIL_GROUPS = [
    ("Fc", "前轴压缩", "#3F719B", "#7FB2D6"),
    ("Fr", "前轴回弹", "#7FB2D6", "#BBD9ED"),
    ("Rc", "后轴压缩", "#C99535", "#E7C172"),
    ("Rr", "后轴回弹", "#E7C172", "#F4DDA8"),
]


def render_hist_detail(d):
    """第①页底部的「详细分布」：前/后 × 压缩/回弹 四组速度桶柱状。"""
    hist = d.get("hist") or {}
    cnt = d.get("hist_cnt") or {}
    bins = d.get("bins") or []
    if not hist or not bins:
        return ""
    group_pct, vmax = {}, 0.0
    for key, _label, _c1, _c2 in HIST_DETAIL_GROUPS:
        n = max(cnt.get(key, 0), 1)
        group_pct[key] = [v / float(n) * 100.0 for v in hist.get(key, [])]
        vmax = max([vmax] + group_pct[key])
    if vmax <= 0:
        return ""
    edges = [0.0] + list(bins) + [None]

    def rng(i):
        lo, hi = edges[i], edges[i + 1]
        if hi is None:
            return "&gt; %.2f m/s" % lo
        return "%.2f – %.2f m/s" % (lo, hi)

    groups_html = []
    for key, label, c1, c2 in HIST_DETAIL_GROUPS:
        bars = []
        for i, p in enumerate(group_pct[key]):
            h = max(p / vmax * 100.0, 0.9)
            bars.append(
                '<span class="hd-bar" style="height:%.2f%%;--c1:%s;--c2:%s" '
                'title="%s · %s · %.1f%%（%d/%d）"></span>'
                % (h, c1, c2, label, rng(i), p, hist[key][i], cnt.get(key, 0)))
        groups_html.append(
            '<div class="hd-group"><div class="hd-bars">%s</div>'
            '<div class="hd-label"><i style="background:%s"></i>%s</div></div>'
            % ("".join(bars), c1, label))
    return """
        <div class="hist-detail">
          <div class="hd-head">
            <span class="hd-title">详细分布</span>
            <span class="hd-note">四组 × 9 个速度桶 · 想深挖阻尼就再看这一块</span>
            <span class="hd-axis">← 慢　快 →</span>
          </div>
          <div class="hd-grid">%s</div>
        </div>""" % "".join(groups_html)


def render_hist_section(d, active):
    """第①页：减振器分布（原有内容，搬进多页框架）。"""
    stem = os.path.splitext(d["file"])[0]
    badge = "原厂悬挂" if d["stock"] else "改装悬挂"
    head = head_html(
        stem, d["file"], "减振器分布", badge,
        "这一页看什么：悬挂主要在应付哪一类路面 —— 细碎、常见，还是大冲击。",
        render_chips(d))
    body = f"""
    <section class="stats">{render_stats(d)}</section>
    <section class="grid">
      <article class="card bars-card">
        <div class="panel-head">
          <div>
            <h2>颠簸构成</h2>
            <p>三个区间加起来 100% · 按四角减振器工作速度统计</p>
          </div>
          <div class="stack-wrap">
            <div class="stack">{render_stack(d)}</div>
            <div class="stack-cap">三档合计 100%</div>
          </div>
        </div>
        <div class="bars">{render_bars(d)}</div>
        {render_hist_detail(d)}
        <div class="insight">{IC["info"]}<div>{d["insight"]}</div></div>
        <div class="panel-foot">
          <span>哪条长，就说明悬挂主要在应付哪类路面。</span>
          <span class="src" title="{esc(d['file'])}">{esc(d['file'])}</span>
        </div>
      </article>

      <aside class="side">
        <article class="card">
          <div class="panel-head">
            <div>
              <h2>调校建议</h2>
              <p>按这一份数据自动生成</p>
            </div>
            <span class="mini-chip">{esc(badge)}</span>
          </div>
          <div class="tips-list">{render_tips(d)}</div>
        </article>

        <article class="card">
          <div class="panel-head">
            <div>
              <h2>这份数据</h2>
              <p>BeamNG 抓包 · 10 Hz</p>
            </div>
          </div>
          <dl class="kv">{render_info(d)}</dl>
        </article>
      </aside>
    </section>"""
    cls = "page active" if active == "hist" else "page"
    return ('<section class="%s" data-page="hist" data-title="减振器分布">\n%s%s\n</section>'
            % (cls, head, body))


def render_nav(active):
    items = [("hist", "bars", "减振器分布")]
    items += [(m.KEY, m.ICON, m.LABEL) for m in PARTS.PAGES
              if not getattr(m, "UTILITY", False)]
    out = []
    for key, icon, label in items:
        out.append('<button class="nav" data-page="%s" data-tip="%s">%s</button>'
                   % (key, esc(label), IC.get(icon, "")))
    return "".join(out)


def render_part_section(mod, d, active):
    try:
        html = mod.render(d)
    except Exception as e:          # noqa: BLE001  单页炸了不能让整个程序打不开
        html = ('<section class="page" data-page="%s" data-title="%s">%s</section>'
                % (getattr(mod, "KEY", "?"), esc(getattr(mod, "TITLE", "?")),
                   empty_state("info", "这一页加载失败", "%s: %s" % (getattr(mod, "KEY", "?"), e))))
    if active == getattr(mod, "KEY", None):
        html = html.replace('class="page"', 'class="page active"', 1)
    return html


def _read_chartkit():
    path = os.path.join(HERE, "webui_parts", "chartkit.js")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:            # noqa: BLE001
        return "/* ChartKit 没找到: %s */" % e


def render_html(data, active_page="hist"):
    pages = [render_hist_section(data, active_page)]
    for mod in PARTS.PAGES:
        pages.append(render_part_section(mod, data, active_page))
    page_css = "\n".join(getattr(m, "CSS", "") or "" for m in PARTS.PAGES)
    page_js = "\n".join(getattr(m, "JS", "") or "" for m in PARTS.PAGES)
    reps = {
        "__NAV__": render_nav(active_page),
        "__ICON_SLIDERS__": IC["sliders"],
        "__ICON_HELP__": IC["help"],
        "__PAGES__": "\n".join(pages),
        "__PAGE_CSS__": page_css,
        "__PAGE_JS__": page_js,
        "__CHARTKIT_JS__": _read_chartkit(),
        "__ACTIVE_PAGE__": active_page,
        "__DATA_JSON__": json.dumps(data, ensure_ascii=False).replace("<", "\\u003c"),
    }
    out = TEMPLATE
    for k, v in reps.items():
        out = out.replace(k, v)
    return out


def load_page(csv_path, active_page="hist", compare_a=None, compare_b=None):
    """读一份 CSV → 页面数据 + 完整 HTML（主程序 / 换数据 / 设置页保存后重载 都走这里）。"""
    r = T.analyze(csv_path)
    if not r:
        raise RuntimeError("analyze() returned nothing (too few rows): %s" % os.path.basename(csv_path))
    data = build_data(r)
    data["csv_list"] = list_csvs()
    if compare_a and compare_b:
        seed = compare_pair(compare_a, compare_b)
        if seed.get("ok"):
            data["compare_seed"] = seed
    return r, data, render_html(data, active_page=active_page)


# ══════════════════════════════════════════════════════════════════════
# 截图
# ══════════════════════════════════════════════════════════════════════
def _find_edge():
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if os.path.isfile(p):
            return p
    return None


def edge_screenshot(html_path, out_png, w=WIN_W, h=WIN_H):
    """用 Edge headless 截 HTML —— 不依赖窗口，像素最稳。"""
    edge = _find_edge()
    if not edge:
        return False, "edge not found"
    url = ("file:///" + os.path.abspath(html_path).replace("\\", "/").replace(" ", "%20")
           + "#still")
    # ★ 每个进程/每次调用用独立 profile，否则多人同时截图会互相覆盖、截到别人的页面
    profile = os.path.join(tempfile.gettempdir(),
                           "dsh_edge_shot_%d_%d" % (os.getpid(), int(time.time() * 1000)))
    os.makedirs(profile, exist_ok=True)
    out_abs = os.path.abspath(out_png)
    if os.path.exists(out_abs):
        try:
            os.remove(out_abs)
        except OSError:
            pass
    cmd = [edge, "--headless=new", "--disable-gpu", "--hide-scrollbars",
           "--no-first-run", "--no-default-browser-check",
           "--force-device-scale-factor=1",
           "--window-size=%d,%d" % (w, h),
           "--virtual-time-budget=5000",
           "--run-all-compositor-stages-before-draw",
           "--user-data-dir=" + profile,
           "--screenshot=" + out_abs, url]
    try:
        subprocess.run(cmd, timeout=120, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, creationflags=0x08000000)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    return (os.path.isfile(out_abs) and os.path.getsize(out_abs) > 2000), out_abs


def _own_windows():
    """枚举本进程的可见顶层窗口，按面积从大到小（避开 FindWindow 的中文标题坑）。"""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    pid = os.getpid()
    found = []
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _lp):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            rc = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rc))
            w, h = rc.right - rc.left, rc.bottom - rc.top
            if w > 500 and h > 400:
                found.append((w * h, hwnd))
        return True

    user32.EnumWindows(proto(cb), 0)
    found.sort(key=lambda t: -t[0])
    return [hwnd for _a, hwnd in found]


def _dpi_scale():
    """pywebview 会把进程设成 DPI-aware：这时窗口坐标已经是物理像素，不能再乘缩放。"""
    import ctypes
    try:
        aware = ctypes.c_int()
        ctypes.windll.shcore.GetProcessDpiAwareness(None, ctypes.byref(aware))
        if aware.value != 0:
            return 1.0
    except Exception:
        pass
    try:
        return ctypes.windll.user32.GetDpiForSystem() / 96.0
    except Exception:
        return 1.0


def capture_window(out_png):
    """抓当前进程最大的那个窗口的客户区。"""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    wins = _own_windows()
    if not wins:
        return False, "no visible window"
    hwnd = wins[0]
    try:
        user32.ShowWindow(hwnd, 9)                      # SW_RESTORE
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)  # TOPMOST
        user32.SetForegroundWindow(hwnd)
        user32.SetCursorPos(2, 2)                       # 把鼠标移开，别让 hover 出现在截图里
    except Exception:
        pass
    time.sleep(0.9)

    rc = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))

    scale = _dpi_scale()
    box = (int(pt.x * scale), int(pt.y * scale),
           int((pt.x + rc.right) * scale), int((pt.y + rc.bottom) * scale))
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(bbox=box, all_screens=True)
    except Exception as e:
        return False, "grab failed: %s" % e

    if img.width < 300 or img.height < 200:
        return False, "bad size %dx%d" % (img.size)
    lo, hi = img.convert("L").getextrema()
    if hi - lo < 12:                                     # 全黑/全白 = 没抓到内容
        return False, "blank capture"
    # 桌面截图偶尔会带进任务栏/黑边（桌面上有别的窗口或远程会话），挡掉这种脏图
    probe = img.convert("L").resize((160, 90))
    raw = probe.tobytes()
    dark = sum(1 for v in raw if v < 14) / float(len(raw))
    if dark > 0.02:
        return False, "dirty capture (%.0f%% black)" % (dark * 100)
    out_abs = os.path.abspath(out_png)
    img.save(out_abs)
    return True, "%dx%d" % (img.width, img.height)


# ══════════════════════════════════════════════════════════════════════
# pywebview
# ══════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════
# 两份对比（「两份对比」页 + JS API 共用）
# ══════════════════════════════════════════════════════════════════════
def list_csvs():
    """数据目录里所有 CSV，按时间新的在前。"""
    files = glob.glob(os.path.join(T.OUTDIR, "*.csv"))
    items = []
    for p in files:
        try:
            st = os.stat(p)
        except OSError:
            continue
        items.append({"path": p, "name": os.path.basename(p),
                      "mtime": st.st_mtime, "kb": round(st.st_size / 1024.0, 1)})
    items.sort(key=lambda x: -x["mtime"])
    return items


def compare_pair(path_a, path_b):
    """分析两份 CSV，返回对比用的紧凑数据；不碰 UI。"""
    try:
        a, b = T.analyze(path_a), T.analyze(path_b)
    except Exception as e:          # noqa: BLE001
        return {"ok": False, "error": "%s" % e}
    if not a or not b:
        return {"ok": False, "error": "analyze() returned nothing (数据点太少)"}
    da, db = build_data(a), build_data(b)
    keep = ("file", "vehicle", "config", "level", "dist_m", "dur_s", "points",
            "rms", "rms_f", "rms_r", "sig_f", "sig_r", "v_avg_kmh", "v_max_kmh",
            "verdict", "verdict_level", "verdict_tone", "bands",
            "axis_text", "axis_pct", "front_share", "rear_share",
            "worst_m", "worst_rms", "worst_pos", "lift_max", "insight", "stock")
    slim = {name: {k: x[k] for k in keep if k in x}
            for name, x in (("a", da), ("b", db))}
    return {
        "ok": True,
        "a": slim["a"],
        "b": slim["b"],
        "verdict": T.compare_verdict(a, b),
        "suggest": T.suggestions(a, b)[:3],
    }


class Api:
    """给 JS 留的接口：window.pywebview.api.* （JS 里 await pywebview.api.xxx()）"""

    def __init__(self, data, csv_path=None, active_page="hist"):
        self._data = data
        self._win = None
        self._csv_path = csv_path
        self._active_page = active_page
        self._newest = None        # (绝对路径, mtime, 文件名) —— 上次看到的最新一份
        self._notified = set()     # 已经提示过的新文件名

    def _marker(self):
        try:
            files = list_csvs()
        except Exception:               # noqa: BLE001
            files = []
        if not files:
            return None
        f = files[0]
        return (os.path.abspath(f["path"]), f["mtime"], f["name"])

    def attach(self, win, csv_path=None, active_page="hist"):
        self._win = win
        if csv_path:
            self._csv_path = csv_path
        self._active_page = active_page
        self._newest = self._marker()

    def get_data(self):
        return self._data

    def _reload_csv(self, path):
        """Python 侧整页重载（自动读取新数据用，不走 JS 回调，避免页面刷新丢回调）。"""
        try:
            r, data, html = load_page(path, active_page=self._active_page)
        except Exception:               # noqa: BLE001
            return
        self._data = data
        self._csv_path = os.path.abspath(path)
        if self._win is not None:
            try:
                self._win.load_html(html)
            except Exception:           # noqa: BLE001
                pass

    def poll(self):
        """界面每 3 秒问一次：有没有新抓的数据 / 游戏在不在跑。

        - 先把游戏写进用户目录的 roadProfile_*.csv 搬进数据目录（老版 relocate）
        - 返回游戏状态（给页头实时 chip 用）
        - 如果最新一份变了：正在看最新那份就返回 auto_path（JS 自动读取）；
          在看历史数据就只提示（new_available）
        """
        moved = 0
        try:
            moved = T.relocate()
        except Exception:               # noqa: BLE001
            pass
        try:
            status = T.read_status()
        except Exception:               # noqa: BLE001
            status = {}
        marker = self._marker()
        auto_path = auto_name = newest_name = None
        new_available = False
        if marker is not None:
            if self._newest is None:
                self._newest = marker
            elif marker != self._newest:
                prev_path = self._newest[0]
                self._newest = marker
                newest_name = marker[2]
                cur = os.path.abspath(self._csv_path) if self._csv_path else ""
                viewing_latest = (not cur) or cur == prev_path
                quiet = self._active_page in ("settings", "help")
                if viewing_latest and not quiet:
                    auto_name = marker[2]
                    self._notified.add(marker[2])
                    # 延迟 0.5 秒再重载：先让这次 poll 的返回值回到 JS
                    threading.Timer(0.5, self._reload_csv, args=(marker[0],)).start()
                elif marker[2] not in self._notified:
                    self._notified.add(marker[2])
                    new_available = True
        return {"ok": True, "moved": moved, "status": status,
                "auto_loaded": bool(auto_name), "auto_name": auto_name,
                "new_available": new_available, "newest_name": newest_name}

    def set_page(self, key):
        """JS 切页时同步一下，换数据 / 保存设置后还能停在同一页。"""
        if isinstance(key, str) and key:
            self._active_page = key
        return True

    # ── 换数据 ──────────────────────────────────────────────
    def open_csv(self, path):
        """切到另一份 CSV：重新分析 + 整页重载（保留当前页签）。"""
        path = os.path.abspath(str(path or ""))
        if not os.path.isfile(path) or not path.lower().endswith(".csv"):
            return {"ok": False, "error": "不是有效的 CSV 文件"}
        try:
            r, data, html = load_page(path, active_page=self._active_page)
        except Exception as e:          # noqa: BLE001
            return {"ok": False, "error": "%s" % e}
        self._data = data
        self._csv_path = path
        if self._win is not None:
            self._win.load_html(html)
        return {"ok": True, "file": data["file"]}

    # ── 真实地图截图（游戏里 Esc→地图 的俯视图）──────────────
    def pick_mapshot(self):
        """选一张游戏地图截图：压成 webp、先存一份，返回 data URI + 默认校准范围。"""
        import base64
        import io as _io

        import webview
        from PIL import Image
        if self._win is None:
            return {"ok": False, "error": "窗口还没准备好"}
        start = os.path.join(T.USERPATH or "", "screenshots")
        if not os.path.isdir(start):
            start = T.USERPATH or os.path.dirname(T.CFG_FILE)
        try:
            res = self._win.create_file_dialog(
                webview.OPEN_DIALOG, directory=start, allow_multiple=False,
                file_types=("图片 (*.png;*.jpg;*.jpeg;*.webp)", "所有文件 (*.*)"))
        except Exception as e:          # noqa: BLE001
            return {"ok": False, "error": "%s" % e}
        if not res:
            return {"ok": False, "cancelled": True}
        path = res[0] if isinstance(res, (list, tuple)) else res
        try:
            img = Image.open(path).convert("RGB")
            sc = min(1.0, 1600.0 / max(img.size))
            if sc < 1.0:
                img = img.resize((max(2, int(img.size[0] * sc)),
                                  max(2, int(img.size[1] * sc))), Image.LANCZOS)
            buf = _io.BytesIO()
            img.save(buf, "WEBP", quality=86, method=4)
            raw = buf.getvalue()
        except Exception as e:          # noqa: BLE001
            return {"ok": False, "error": "读图失败：%s" % e}
        level = str((self._data or {}).get("level") or "")
        bounds = [0.0, 0.0, 1000.0, 1000.0]
        try:
            import level_map as _lm
            tb = _lm.terrain_bounds(level)
            if tb:
                bounds = tb
            _lm.save_user_shot(level, raw, bounds[0], bounds[1], bounds[2], bounds[3])
            shot = _lm.load_user_shot(level)
            if shot:
                bounds = [shot["x0"], shot["y0"], shot["x1"], shot["y1"]]
        except Exception:               # noqa: BLE001
            pass
        return {"ok": True, "level": level, "w": img.size[0], "h": img.size[1],
                "img": "data:image/webp;base64," + base64.b64encode(raw).decode("ascii"),
                "calib": {"x0": bounds[0], "y0": bounds[1], "x1": bounds[2], "y1": bounds[3]}}

    def save_mapshot(self, level, x0, y0, x1, y1):
        """保存校准范围（截图在导入时已经存好）。"""
        try:
            import level_map as _lm
            lvl = level or str((self._data or {}).get("level") or "")
            ok = _lm.set_calibration(lvl, x0, y0, x1, y1)
            if not ok:
                return {"ok": False, "error": "还没有导入过地图截图"}
            return {"ok": True}
        except Exception as e:          # noqa: BLE001
            return {"ok": False, "error": "%s" % e}

    def delete_csv(self, path):
        """删除数据目录里的一份抓包（CSV + 同名 .txt 摘要）。

        只允许删 OUTDIR 里的文件，防止误删别处的东西；删的是当前正在看的那份时，
        返回 next（下一份最新的 CSV），JS 会自己切过去。
        """
        path = os.path.abspath(str(path or ""))
        outdir = os.path.abspath(T.OUTDIR)
        if not path.lower().endswith(".csv"):
            return {"ok": False, "error": "只能删除 CSV 抓包文件"}
        if os.path.dirname(path).lower() != outdir.lower():
            return {"ok": False, "error": "只能删除数据目录里的文件"}
        if not os.path.isfile(path):
            return {"ok": False, "error": "文件不存在（可能已经被删了）"}
        deleted = []
        try:
            os.remove(path)
            deleted.append(os.path.basename(path))
            txt = os.path.splitext(path)[0] + ".txt"
            if os.path.exists(txt):
                os.remove(txt)
                deleted.append(os.path.basename(txt))
        except OSError as e:
            return {"ok": False, "error": "%s" % e}
        self._newest = self._marker()       # 别让轮询把"文件被删"误判成新数据
        self._notified = set()
        cur = os.path.abspath(self._csv_path) if self._csv_path else ""
        was_current = (cur == path)
        next_csv = None
        if was_current:
            files = list_csvs()
            if files:
                next_csv = os.path.abspath(files[0]["path"])
        return {"ok": True, "deleted": deleted, "was_current": was_current,
                "next": next_csv}

    def pick_csv_file(self):
        """弹系统文件对话框选 CSV。"""
        import webview
        if self._win is None:
            return {"ok": False, "error": "窗口还没准备好"}
        try:
            res = self._win.create_file_dialog(
                webview.OPEN_DIALOG, directory=T.OUTDIR, allow_multiple=False,
                file_types=("CSV 抓包数据 (*.csv)", "所有文件 (*.*)"))
        except Exception as e:          # noqa: BLE001
            return {"ok": False, "error": "%s" % e}
        if not res:
            return {"ok": False, "cancelled": True}
        return self.open_csv(res[0] if isinstance(res, (list, tuple)) else res)

    # ── 路径设置 / 一键安装 ─────────────────────────────────
    def config_info(self):
        info = {"userpath": T.USERPATH, "game_exe": T.GAME_EXE, "outdir": T.OUTDIR,
                "cfg_file": T.CFG_FILE, "launcher": T.LAUNCHER}
        try:
            jobs = {
                "lua": os.path.join(T.USERPATH, "lua", "ge", "extensions", "roadProfile.lua"),
                "script": os.path.join(T.USERPATH, "scripts", "roadProfile", "modScript.lua"),
                "zip": os.path.join(T.USERPATH, "mods", "roadProfileUI.zip"),
            }
            info["installed"] = {k: os.path.isfile(p) for k, p in jobs.items()}
        except Exception:               # noqa: BLE001
            info["installed"] = {}
        return info

    def autodetect_paths(self):
        try:
            game = T._autodetect_game_exe()
            return {"ok": True, "userpath": T._autodetect_userpath(),
                    "game_exe": game, "launcher": T._derive_launcher(game)}
        except Exception as e:          # noqa: BLE001
            return {"ok": False, "error": "%s" % e}

    def pick_folder(self):
        import webview
        try:
            res = self._win.create_file_dialog(webview.FOLDER_DIALOG)
        except Exception as e:          # noqa: BLE001
            return {"ok": False, "error": "%s" % e}
        if not res:
            return {"ok": False, "cancelled": True}
        return {"ok": True, "path": res[0] if isinstance(res, (list, tuple)) else res}

    def pick_exe(self):
        import webview
        try:
            res = self._win.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False,
                                               file_types=("可执行文件 (*.exe)",))
        except Exception as e:          # noqa: BLE001
            return {"ok": False, "error": "%s" % e}
        if not res:
            return {"ok": False, "cancelled": True}
        return {"ok": True, "path": res[0] if isinstance(res, (list, tuple)) else res}

    def save_config(self, userpath, game_exe="", outdir="", launcher=""):
        """写回 config.json，同步更新 beamng_data 的全局路径，然后整页重载。"""
        import json
        userpath = (userpath or "").strip()
        game_exe = (game_exe or "").strip()
        outdir = (outdir or "").strip()
        launcher = (launcher or "").strip()
        if not userpath or not os.path.isdir(userpath):
            return {"ok": False, "error": "用户目录不存在：%s" % userpath}
        outdir = os.path.abspath(outdir) if outdir else T.OUTDIR
        try:
            os.makedirs(outdir, exist_ok=True)
            cfg = {"userpath": userpath, "game_exe": game_exe, "outdir": outdir}
            if launcher:
                cfg["launcher"] = launcher
            with open(T.CFG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:          # noqa: BLE001
            return {"ok": False, "error": "%s" % e}
        T.USERPATH = userpath
        T.GAME_EXE = game_exe
        T.OUTDIR = outdir
        T.LAUNCHER = launcher or T._derive_launcher(game_exe)
        T.IPC_DIR = userpath
        T.F_STATUS = os.path.join(userpath, "roadProfile_status.txt")
        T.F_CMD = os.path.join(userpath, "roadProfile_cmd.txt")
        try:
            T.F_LATEST = os.path.join(outdir, "roadProfile_latest.csv")
        except Exception:               # noqa: BLE001
            pass
        # 当前这份 CSV 如果不在新数据目录里也还能用（绝对路径）
        try:
            csv_path = self._csv_path or pick_csv(None)
            r, data, html = load_page(csv_path, active_page="settings")
            self._data = data
            self._csv_path = csv_path
            if self._win is not None:
                self._win.load_html(html)
        except Exception as e:          # noqa: BLE001
            return {"ok": True, "warning": "已保存，但界面重载失败：%s" % e}
        return {"ok": True, "cfg_file": T.CFG_FILE}

    def install_mod(self):
        """把抓包扩展 / 自动加载脚本 / 面板 mod 装进游戏用户目录。"""
        try:
            n, msgs = T.install_to_game(T.USERPATH)
        except Exception as e:          # noqa: BLE001
            return {"ok": False, "error": "%s" % e}
        return {"ok": n > 0, "done": n, "msgs": msgs, "userpath": T.USERPATH}

    def list_csvs(self):
        return list_csvs()

    def export_game_data(self):
        """给游戏内扩展发 dump 命令（写 cmd 文件），让它把当前抓包导出成 CSV。"""
        try:
            if not os.path.isdir(T.USERPATH):
                return {"ok": False, "error": "游戏用户目录不存在：%s" % T.USERPATH}
            ok = T.send_command("dump")
            if not ok:
                return {"ok": False, "error": "写命令文件失败：%s" % T.F_CMD}
            return {"ok": True, "message": "已让游戏导出当前抓包，几秒后自动导入"}
        except Exception as e:          # noqa: BLE001
            return {"ok": False, "error": "%s" % e}

    def launch_game(self, mode="steam"):
        """启动游戏：mode=steam 走 Steam 协议；mode=direct 直接用设置里的非 Steam 路径。"""
        try:
            ok, msg = T.launch_game(mode)
            return {"ok": ok, "message": msg}
        except Exception as e:          # noqa: BLE001
            return {"ok": False, "message": "启动失败：%s" % e}

    def open_folder(self, path):
        """在资源管理器里打开目录（设置页的按钮用）。"""
        try:
            if path and os.path.isdir(path):
                os.startfile(path)      # noqa: S606  Windows 专用
                return True
        except Exception:               # noqa: BLE001
            pass
        return False

    def compare_pair(self, path_a, path_b):
        return compare_pair(path_a, path_b)


def run_window(page, data, shot_path=None, csv_path=None, active_page="hist"):
    import webview

    api = Api(data, csv_path=csv_path, active_page=active_page)
    win = webview.create_window(
        WINDOW_TITLE, html=page, width=WIN_W, height=WIN_H,
        min_size=(1120, 720), background_color="#EEF3F9", js_api=api,
    )
    api.attach(win, csv_path=csv_path, active_page=active_page)

    if not shot_path:
        webview.start()
        return True

    result = {"ok": False}

    def worker():
        time.sleep(3.0)
        try:
            print("viewport: %s" % win.evaluate_js("window.innerWidth + 'x' + window.innerHeight"))
        except Exception:
            pass
        try:
            win.evaluate_js("(function(){var t=document.getElementById('toast');"
                            "if(t)t.classList.remove('show');})()")
        except Exception:
            pass
        try:
            ok, info = capture_window(shot_path)
            result["ok"] = ok
            print("capture: %s (%s)" % ("ok" if ok else "failed", info))
        except Exception as e:          # noqa: BLE001
            print("capture error: %s" % e)
        try:
            win.destroy()
        except Exception:
            pass

    webview.start(worker)
    return result["ok"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="BeamNG-style Web UI (multi-page vehicle data analyzer)")
    ap.add_argument("--csv", help="path of a roadProfile CSV (default: newest in OUTDIR)")
    ap.add_argument("--page", default="hist",
                    help="start page: hist/profile/dyno/wheels/wave/pedals/compare")
    ap.add_argument("--html", help="export the generated HTML to this path and exit")
    ap.add_argument("--shot", help="open the window, capture it, save PNG here, then close")
    ap.add_argument("--headless", action="store_true", help="screenshot via Edge headless instead of the window")
    ap.add_argument("--compare-a", help="[compare page] CSV path A (pre-computed demo pair)")
    ap.add_argument("--compare-b", help="[compare page] CSV path B (pre-computed demo pair)")
    args = ap.parse_args(argv)

    try:
        csv_path = pick_csv(args.csv)
    except SystemExit as _e:
        _msg = str(_e)
        if not (args.html or args.shot):
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    None,
                    "没找到抓包数据（*.csv）。\n\n"
                    "程序会在下面这个目录里找：\n%s\n\n"
                    "解决办法：\n"
                    "1. 把抓包导出的 CSV 放进上面这个目录；\n"
                    "2. 或者到「设置」里把「抓包输出目录」改成放 CSV 的文件夹；\n"
                    "3. 安装包正常安装时会自带一份示例数据，可以直接先看界面。\n\n"
                    "（改动路径后重启程序生效）" % T.OUTDIR,
                    "车辆数据分析器 - 没有找到数据", 0x40)
            except Exception:  # noqa: BLE001
                pass
        print(_msg)
        return 1
    print("csv: %s" % os.path.basename(csv_path))

    valid_pages = ["hist"] + [m.KEY for m in PARTS.PAGES]
    active = args.page if args.page in valid_pages else "hist"
    if args.page not in valid_pages:
        print("page '%s' not registered yet, fallback to hist (have: %s)"
              % (args.page, ", ".join(valid_pages)))

    r, data, page = load_page(csv_path, active_page=active,
                              compare_a=args.compare_a, compare_b=args.compare_b)
    if "compare_seed" in data:
        print("compare seed: %d verdict lines" % len(data["compare_seed"].get("verdict") or []))
    print("page: %s" % active)
    print("bands: %.1f / %.1f / %.1f  |  rms %.3f  |  %s"
          % (data["bands"][0]["pct"], data["bands"][1]["pct"], data["bands"][2]["pct"],
             data["rms"], data["verdict"].encode("ascii", "replace").decode("ascii")))

    # 只导 HTML
    if args.html:
        out = os.path.abspath(args.html)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(page)
        print("html: %s" % out)
        if not args.shot:
            return 0

    # 只截图（headless 路线，不打开窗口）
    if args.shot and args.headless:
        fd, tmp = tempfile.mkstemp(prefix="beamng_ui_", suffix=".html")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(page)
        try:
            ok, info = edge_screenshot(tmp, args.shot)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        print("shot: %s (%s)" % (os.path.abspath(args.shot), info))
        if not ok:
            raise SystemExit("headless screenshot failed")
        return 0

    # 正常开窗口
    ok = run_window(page, data, args.shot, csv_path=csv_path, active_page=active)
    if args.shot:
        if ok:
            print("shot: %s" % os.path.abspath(args.shot))
            return 0
        # 窗口截图失败 -> 自动退到 Edge headless
        print("fallback: edge headless")
        fd, tmp = tempfile.mkstemp(prefix="beamng_ui_", suffix=".html")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(page)
        try:
            ok2, info = edge_screenshot(tmp, args.shot)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        print("shot: %s (%s)" % (os.path.abspath(args.shot), info))
        if not ok2:
            raise SystemExit("screenshot failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
