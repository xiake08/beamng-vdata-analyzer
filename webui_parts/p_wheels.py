# -*- coding: utf-8 -*-
"""四轮载荷页 —— 俯视四轮示意图 + 配重 / 载荷范围 / 滑移 / 离地 / 四轮明细表

数据口径（和老 tkinter 版 _draw_wheels / _draw_balance_block 一致）：
- ``load``       四轮平均载荷 N
- ``loadsig``    轮荷标准差 σ（几何无关，前后轴谁更忙只看它，不看减振器 RMS）
- ``lmin/lmax``  全程载荷范围 N；``air`` 离地采样占比 %；``slip_pct`` >0 打滑、<0 抱死
- ``wb_balance`` 前后 / 左右 / 对角配重 %；左右差 = |left-50|*2，>5% 提示
"""

import math

from .common import IC, chip, empty_state, esc, fmt_dist, fmt_dur, head_html

KEY = "wheels"
LABEL = "四轮载荷"          # 左侧导航上的文字（尽量 ≤4 字）
ICON = "car"                # common.IC 里的图标 key
TITLE = "四轮载荷"          # 页面大标题
BADGE = ""                  # 标题旁小标签（这里按数据动态给「原厂/改装悬挂」）
SUB = "这一页看什么：四个轮子各扛多少、前后左右配重差多少，左右差超 5% 就该查。"
ORDER = 4

# 老程序里对应这一页的代码：
#   老 tkinter 版 _draw_wheels / _draw_balance_block（已删除）：这里的布局比它更全

TAGS = ("FL", "FR", "RL", "RR")
CN = {"FL": "前左", "FR": "前右", "RL": "后左", "RR": "后右"}
AXIS = {"FL": "front", "FR": "front", "RL": "rear", "RR": "rear"}
SIDE = {"FL": "left", "FR": "right", "RL": "left", "RR": "right"}

LOAD_LIGHT = (0xBE, 0xDA, 0xED)   # 载荷轻 -> 浅
LOAD_DEEP = (0x2F, 0x5C, 0x82)    # 载荷重 -> 深
AXIS_COLOR = {"front": "#5B8FB9", "rear": "#D9A24A"}

_ICON_CHECK = '<svg class="ic" viewBox="0 0 24 24"><path d="M5 12.6l4.4 4.4L19 7.4"/></svg>'
_ICON_WARN = ('<svg class="ic" viewBox="0 0 24 24"><path d="M12 4.2 21 20H3z"/>'
              '<path d="M12 9.8v4.2"/><circle cx="12" cy="17" r=".85"/></svg>')


# ══════════════════════════════════════════════════════════════════════
# 小工具
# ══════════════════════════════════════════════════════════════════════
def _num(v):
    """整数千分位；None / 非法 -> —。"""
    if v is None:
        return "—"
    try:
        return "{:,.0f}".format(float(v))
    except (TypeError, ValueError):
        return "—"


def _one(v):
    if v is None:
        return "—"
    try:
        return "%.1f" % float(v)
    except (TypeError, ValueError):
        return "—"


def _signed(v, dec=1):
    """带符号数字：+3.1 / −15.2（用排版减号）。"""
    if v is None:
        return "—"
    try:
        s = "%+.*f" % (dec, float(v))
    except (TypeError, ValueError):
        return "—"
    return s.replace("-", "−")


def _pick(src, tag):
    """从 {tag: value} 里取 float，取不到返回 None。"""
    try:
        return float((src or {}).get(tag))
    except (TypeError, ValueError):
        return None


def _mix(c1, c2, t):
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return "#%02X%02X%02X" % tuple(
        int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


def _ink(hex_color):
    """深色底用白字、浅色底用深字。"""
    try:
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return "#1F2E3C"
    return "#FFFFFF" if (0.299 * r + 0.587 * g + 0.114 * b) < 150 else "#1F2E3C"


def _nice_up(v):
    """把量程圆整到好看的上界：19747 -> 20000。"""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 1.0
    if v <= 0:
        return 1.0
    e = 10.0 ** math.floor(math.log10(v))
    m = v / e
    for step in (1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0):
        if m <= step + 1e-9:
            return float(step * e)
    return 10.0 * e


# ══════════════════════════════════════════════════════════════════════
# build：analyze() -> 本页数据
# ══════════════════════════════════════════════════════════════════════
def build(r, d):
    """把四轮相关的原始字段整理成页面直接可用的结构（全部 JSON 可序列化）。"""
    wh = r.get("wheels") or {}
    load_map = r.get("load") or {}
    pct_map = r.get("load_pct") or {}
    sig_map = r.get("loadsig") or {}
    lmin_map = r.get("lmin") or {}
    lmax_map = r.get("lmax") or {}
    air_map = r.get("air") or {}
    slip_map = r.get("slip_pct") or {}

    rows = []
    for tag in TAGS:
        raw = wh.get(tag) or {}
        if tag not in wh:
            continue
        ld = _pick(load_map, tag)
        if ld is None:
            try:
                ld = float(raw.get("ld"))
            except (TypeError, ValueError):
                continue
        sig = _pick(sig_map, tag)
        lmin = _pick(lmin_map, tag)
        lmax = _pick(lmax_map, tag)
        lmin = ld if lmin is None else min(lmin, ld)
        lmax = ld if lmax is None else max(lmax, ld)
        try:
            ld_max = float(raw.get("ld_max"))
        except (TypeError, ValueError):
            ld_max = lmax
        try:
            sp = float(raw.get("sp"))
        except (TypeError, ValueError):
            sp = 0.0
        rows.append({
            "tag": tag,
            "cn": CN[tag],
            "axis": AXIS[tag],
            "side": SIDE[tag],
            "ld": round(ld, 1),
            "ld_max": round(ld_max, 1),
            "sp": round(sp, 3),
            "pct": round(_pick(pct_map, tag) or 0.0, 2),
            "sig": round(sig or 0.0, 1),
            "lmin": round(lmin, 1),
            "lmax": round(lmax, 1),
            "air": round(_pick(air_map, tag) or 0.0, 2),
            "slip": round(_pick(slip_map, tag) or 0.0, 2),
        })

    # 颜色：在四轮自身的 min~max 之间拉伸，让载荷差在图上看得出来
    vals = [x["ld"] for x in rows]
    lo, hi = (min(vals), max(vals)) if vals else (0.0, 1.0)
    for x in rows:
        t = (x["ld"] - lo) / (hi - lo) if hi > lo else 0.5
        x["fill"] = _mix(LOAD_LIGHT, LOAD_DEEP, t)
        x["ink"] = _ink(x["fill"])
        x["pct_dev"] = round(x["pct"] - 25.0, 2)

    total = sum(x["ld"] for x in rows) or 0.0
    d["wheel_rows"] = rows
    d["wheels_ok"] = bool(rows)
    d["wheel_total"] = round(total, 1)
    d["wheel_load_lo"] = round(lo, 1) if rows else 0.0
    d["wheel_load_hi"] = round(hi, 1) if rows else 0.0
    d["wheel_scale"] = _nice_up(max([x["lmax"] for x in rows] or [0.0]))
    d["mass"] = round(float(r.get("mass") or 0.0), 1)

    # ── 轴荷 / 侧荷合计（图上左右两个面板用）──
    def _sum(which, key):
        return sum(x["ld"] for x in rows if x[key] == which)

    front_n, rear_n = _sum("front", "axis"), _sum("rear", "axis")
    left_n, right_n = _sum("left", "side"), _sum("right", "side")
    denom = (front_n + rear_n) or 1.0
    side_den = (left_n + right_n) or 1.0
    d["axle"] = {
        "front_n": round(front_n, 1), "rear_n": round(rear_n, 1),
        "left_n": round(left_n, 1), "right_n": round(right_n, 1),
        "front_pct": round(front_n / denom * 100.0, 2),
        "rear_pct": round(rear_n / denom * 100.0, 2),
        "left_pct": round(left_n / side_den * 100.0, 2),
        "right_pct": round(right_n / side_den * 100.0, 2),
    }

    # ── 配重（wb_balance），左右差 = |left-50|*2 ──
    bal = r.get("wb_balance") or {}
    front = _pick(bal, "front")
    left = _pick(bal, "left")
    cross = _pick(bal, "cross")
    if front is None:
        front = d["axle"]["front_pct"]
    if left is None:
        left = d["axle"]["left_pct"]
    if cross is None:
        fl = next((x["ld"] for x in rows if x["tag"] == "FL"), 0.0)
        rr = next((x["ld"] for x in rows if x["tag"] == "RR"), 0.0)
        cross = (fl + rr) / total * 100.0 if total else 50.0
    lr_diff = abs(left - 50.0) * 2.0
    d["wb"] = {
        "front": round(front, 2), "rear": round(100.0 - front, 2),
        "left": round(left, 2), "right": round(100.0 - left, 2),
        "cross": round(cross, 2),
        "lr_diff": round(lr_diff, 2),
        "lr_ok": lr_diff <= 5.0,
        "front_diff": round(abs(front - 50.0) * 2.0, 2),
        "cross_dev": round(cross - 50.0, 2),
        "cross_ok": abs(cross - 50.0) <= 2.0,
    }

    # ── σ：前后轴对比 + 最忙 / 最稳的轮子 ──
    sig_f = float(r.get("sig_f") or 0.0)
    sig_r = float(r.get("sig_r") or 0.0)
    f_rows = [x for x in rows if x["axis"] == "front"]
    r_rows = [x for x in rows if x["axis"] == "rear"]
    if (not sig_f) and f_rows:
        sig_f = sum(x["sig"] for x in f_rows) / len(f_rows)
    if (not sig_r) and r_rows:
        sig_r = sum(x["sig"] for x in r_rows) / len(r_rows)
    busiest = max(rows, key=lambda x: x["sig"]) if rows else None
    steadiest = min(rows, key=lambda x: x["sig"]) if rows else None
    d["sig_info"] = {
        "f": round(sig_f, 1),
        "r": round(sig_r, 1),
        "max": round(busiest["sig"], 1) if busiest else 0.0,
        "max_tag": busiest["tag"] if busiest else "—",
        "max_cn": busiest["cn"] if busiest else "—",
        "min": round(steadiest["sig"], 1) if steadiest else 0.0,
        "min_tag": steadiest["tag"] if steadiest else "—",
        "min_cn": steadiest["cn"] if steadiest else "—",
        "axis_pct": round((sig_r / sig_f - 1.0) * 100.0, 1) if sig_f > 1e-6 else 0.0,
    }
    return d


# ══════════════════════════════════════════════════════════════════════
# 页头
# ══════════════════════════════════════════════════════════════════════
def _head(d):
    badge = "原厂悬挂" if d.get("stock") else "改装悬挂"
    level = (d.get("level") or "—").replace("_", " ")
    chips = (
        chip("pin", level)
        + chip("route", "%s · %s" % (fmt_dist(d.get("dist_m") or 0.0),
                                     fmt_dur(d.get("dur_s") or 0.0)))
    )
    if d.get("wheels_ok") and (d.get("mass") or 0) > 0:
        chips += chip("gauge", "总重 ≈ %s kg" % _num(d.get("mass")))
    return head_html(d.get("file", ""), d.get("file", ""), TITLE, badge, SUB, chips)


# ══════════════════════════════════════════════════════════════════════
# ① 俯视示意图（SVG）
# ══════════════════════════════════════════════════════════════════════
def _car_svg(d):
    rows = d.get("wheel_rows") or []
    by = {x["tag"]: x for x in rows}
    axle = d.get("axle") or {}
    sig = d.get("sig_info") or {}
    lo = d.get("wheel_load_lo") or 0.0
    hi = d.get("wheel_load_hi") or 0.0
    pos = {"FL": (402, 124), "FR": (598, 124), "RL": (402, 288), "RR": (598, 288)}

    p = []
    a = p.append
    a('<svg class="car-svg" viewBox="0 0 1000 380" preserveAspectRatio="xMidYMid meet" '
      'role="img" aria-label="四轮载荷俯视示意图">')
    a('<defs>'
      '<linearGradient id="pw-body" x1="0" y1="0" x2="0" y2="1">'
      '<stop offset="0" stop-color="#F4FAFE"/><stop offset="1" stop-color="#D8EAF8"/></linearGradient>'
      '<linearGradient id="pw-glass" x1="0" y1="0" x2="0" y2="1">'
      '<stop offset="0" stop-color="#BFDAEE"/><stop offset="1" stop-color="#E2F0FA"/></linearGradient>'
      '<linearGradient id="pw-scale" x1="0" y1="0" x2="1" y2="0">'
      '<stop offset="0" stop-color="#BEDAED"/><stop offset="1" stop-color="#2F5C82"/></linearGradient>'
      '<filter id="pw-drop" x="-50%" y="-50%" width="200%" height="200%">'
      '<feDropShadow dx="0" dy="3" stdDeviation="3.4" flood-color="#2E4C69" flood-opacity=".2"/>'
      '</filter>'
      '<filter id="pw-soft" x="-30%" y="-25%" width="160%" height="160%">'
      '<feDropShadow dx="0" dy="7" stdDeviation="9" flood-color="#2E4C69" flood-opacity=".12"/>'
      '</filter>'
      '</defs>')

    # ── 车身（俯视轮廓：车头朝上）──
    a('<rect x="436" y="42" width="128" height="304" rx="38" ry="54" '
      'fill="url(#pw-body)" stroke="#AFCEE6" stroke-width="1.6" filter="url(#pw-soft)"/>')
    a('<rect x="444" y="58" width="18" height="7" rx="3.5" fill="#EDF6FC" stroke="#C9DEEE" stroke-width="1"/>')
    a('<rect x="538" y="58" width="18" height="7" rx="3.5" fill="#EDF6FC" stroke="#C9DEEE" stroke-width="1"/>')
    a('<path d="M472,70 V112 M528,70 V112" stroke="rgba(91,143,185,.18)" stroke-width="1"/>')
    a('<path d="M446,112 Q500,104 554,112 L548,148 Q500,155 452,148 Z" fill="url(#pw-glass)"/>')
    a('<rect x="438" y="158" width="13" height="96" rx="6" fill="url(#pw-glass)" opacity=".85"/>')
    a('<rect x="549" y="158" width="13" height="96" rx="6" fill="url(#pw-glass)" opacity=".85"/>')
    a('<rect x="454" y="152" width="92" height="108" rx="20" fill="#EDF6FD" opacity=".92" '
      'stroke="#CFE2F1" stroke-width="1"/>')
    a('<rect x="464" y="176" width="26" height="34" rx="9" fill="#CFE4F3" stroke="#BBD6E9" stroke-width="1"/>')
    a('<rect x="510" y="176" width="26" height="34" rx="9" fill="#CFE4F3" stroke="#BBD6E9" stroke-width="1"/>')
    a('<rect x="472" y="228" width="56" height="22" rx="8" fill="#D8EAF7" stroke="#C2DAEB" stroke-width="1"/>')
    a('<path d="M452,266 Q500,259 548,266 L554,300 Q500,308 446,300 Z" fill="url(#pw-glass)"/>')
    a('<path d="M452,317 Q500,322 548,317" fill="none" stroke="rgba(91,143,185,.2)" stroke-width="1"/>')
    a('<rect x="454" y="320" width="18" height="7" rx="3.5" fill="#F0E0D9" stroke="#DEBFB3" stroke-width="1"/>')
    a('<rect x="528" y="320" width="18" height="7" rx="3.5" fill="#F0E0D9" stroke="#DEBFB3" stroke-width="1"/>')
    a('<path d="M500,50 L506,60 L494,60 Z" fill="#A9C6DC"/>')
    a('<text x="512" y="60" class="caxl" style="font-size:9.5px">车头</text>')

    # ── 左右括号 + 引线：把「左侧合计 / 右侧合计」和两个轮子连起来 ──
    a('<path d="M344,124 H358 M344,124 V288 M344,288 H358" fill="none" '
      'stroke="#A9C6DC" stroke-width="1.4" stroke-dasharray="5 5"/>')
    a('<path d="M656,124 H642 M656,124 V288 M656,288 H642" fill="none" '
      'stroke="#C9B392" stroke-width="1.4" stroke-dasharray="5 5"/>')
    a('<path d="M252,206 H344" fill="none" stroke="#C4D8E6" stroke-width="1.2" stroke-dasharray="3 4"/>')
    a('<path d="M656,206 H748" fill="none" stroke="#D8C7AB" stroke-width="1.2" stroke-dasharray="3 4"/>')

    # ── 四个轮位 ──
    for tag in TAGS:
        cx, cy = pos[tag]
        x = by.get(tag)
        fill = x["fill"] if x else "#EEF4F9"
        ink = x["ink"] if x else "#8496A7"
        if x and x["air"] >= 0.5:
            a('<circle cx="%d" cy="%d" r="52" fill="none" stroke="#D9A24A" stroke-width="2" '
              'stroke-dasharray="5 5" opacity=".8"/>' % (cx, cy))
        a('<circle cx="%d" cy="%d" r="44" fill="%s" stroke="#FFFFFF" stroke-width="3" '
          'filter="url(#pw-drop)"/>' % (cx, cy, fill))
        a('<text x="%d" y="%d" text-anchor="middle" class="cwn">%s '
          '<tspan class="cwt">%s</tspan></text>' % (cx, cy - 56, CN[tag], tag))
        if x:
            if x["air"] >= 0.5:
                air_ink = "#F3CF8C" if ink == "#FFFFFF" else "#A96F12"
                a('<text x="%d" y="%d" text-anchor="middle" class="cair" fill="%s">离地 %.1f%%</text>'
                  % (cx, cy - 17, air_ink, x["air"]))
            a('<text x="%d" y="%d" text-anchor="middle" class="cwl" fill="%s">%s</text>'
              % (cx, cy + 3, ink, _num(x["ld"])))
            a('<text x="%d" y="%d" text-anchor="middle" class="cws" fill="%s" opacity=".88">'
              'N · %.1f%%</text>' % (cx, cy + 19, ink, x["pct"]))
            a('<text x="%d" y="%d" text-anchor="middle" class="cws" fill="%s" opacity=".88">'
              'σ %s</text>' % (cx, cy + 35, ink, _num(x["sig"])))
        else:
            a('<text x="%d" y="%d" text-anchor="middle" class="cws" fill="%s">无数据</text>'
              % (cx, cy + 5, ink))

    # ── 左上：颜色图例（深 = 载荷大）──
    a('<text x="24" y="26" class="caxl">圆圈颜色 = 平均载荷（越深越重）</text>')
    a('<rect x="24" y="34" width="220" height="8" rx="4" fill="url(#pw-scale)"/>')
    a('<text x="24" y="58" class="caxl">%s N</text>' % _num(lo))
    a('<text x="244" y="58" text-anchor="end" class="caxl">%s N</text>' % _num(hi))

    # ── 右上：σ 前后轴对比 ──
    a('<text x="976" y="26" text-anchor="end" class="caxl">最忙的轮子（σ 最大）</text>')
    a('<text x="976" y="47" text-anchor="end" class="caxv2">%s %s · σ %s N</text>'
      % (esc(sig.get("max_cn", "—")), esc(sig.get("max_tag", "—")), _num(sig.get("max"))))
    a('<text x="976" y="67" text-anchor="end" class="caxl">前轴 σ %s · 后轴 σ %s N</text>'
      % (_num(sig.get("f")), _num(sig.get("r"))))

    # ── 上/下：前后轴合计 ──
    a('<text x="500" y="24" text-anchor="middle" class="caxl">前轴合计 '
      '<tspan class="caxv">%s N</tspan><tspan class="caxl"> · 占 %.1f%%</tspan></text>'
      % (_num(axle.get("front_n")), axle.get("front_pct", 0.0)))
    a('<path d="M500,30 V40" fill="none" stroke="#B9D3E6" stroke-width="1.2" stroke-dasharray="3 3"/>')
    a('<path d="M500,350 V359" fill="none" stroke="#B9D3E6" stroke-width="1.2" stroke-dasharray="3 3"/>')
    a('<text x="500" y="371" text-anchor="middle" class="caxl">后轴合计 '
      '<tspan class="caxv">%s N</tspan><tspan class="caxl"> · 占 %.1f%%</tspan></text>'
      % (_num(axle.get("rear_n")), axle.get("rear_pct", 0.0)))

    # ── 左面板：左侧合计 ──
    left_pct = axle.get("left_pct", 0.0)
    a('<text x="24" y="180" class="caxl">左侧合计</text>')
    a('<text x="24" y="207" class="caxbig">%s<tspan class="caxu"> N</tspan></text>'
      % _num(axle.get("left_n")))
    a('<text x="24" y="224" class="caxl">占整车 %.1f%%</text>' % left_pct)
    a('<rect x="24" y="232" width="220" height="7" rx="3.5" fill="rgba(91,143,185,.12)"/>')
    a('<rect x="24" y="232" width="%.1f" height="7" rx="3.5" fill="#5B8FB9"/>'
      % (220.0 * left_pct / 100.0))

    # ── 右面板：右侧合计（镜像）──
    right_pct = axle.get("right_pct", 0.0)
    a('<text x="976" y="180" text-anchor="end" class="caxl">右侧合计</text>')
    a('<text x="976" y="207" text-anchor="end" class="caxbig">%s<tspan class="caxu"> N</tspan></text>'
      % _num(axle.get("right_n")))
    a('<text x="976" y="224" text-anchor="end" class="caxl">占整车 %.1f%%</text>' % right_pct)
    a('<rect x="756" y="232" width="220" height="7" rx="3.5" fill="rgba(91,143,185,.12)"/>')
    a('<rect x="%.1f" y="232" width="%.1f" height="7" rx="3.5" fill="#D9A24A"/>'
      % (976.0 - 220.0 * right_pct / 100.0, 220.0 * right_pct / 100.0))

    a('</svg>')
    return "".join(p)


# ══════════════════════════════════════════════════════════════════════
# ② 每轮载荷范围（lmin -> lmax，圆点=均值；离地 / 滑移）
# ══════════════════════════════════════════════════════════════════════
def _air_chip(v):
    on = (v or 0.0) >= 0.5
    return '<span class="wr-chip %s">离地 %s%%</span>' % (
        "air-on" if on else "air-off", _one(v))


def _slip_chip(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        v = 0.0
    if v > 0.8:
        cls, label = "slip-spin", "打滑"
    elif v < -0.8:
        cls, label = "slip-lock", "抱死"
    else:
        cls, label = "slip-ok", "滑移"
    return '<span class="wr-chip %s">%s %s%%</span>' % (cls, label, _signed(v))


def _range_rows(d):
    rows = d.get("wheel_rows") or []
    scale = float(d.get("wheel_scale") or 1.0) or 1.0
    out = []
    for x in rows:
        left = min(max(x["lmin"] / scale * 100.0, 0.0), 100.0)
        width = (x["lmax"] - x["lmin"]) / scale * 100.0
        width = min(max(width, 0.8), 100.0 - left)
        avg = min(max(x["ld"] / scale * 100.0, 0.0), 100.0)
        out.append(
            '<div class="wr-row" style="--wc:%(fill)s">'
            '<div class="wr-id"><span class="wr-dot" style="background:%(fill)s"></span>'
            '<div><b>%(cn)s</b><i>%(tag)s</i></div></div>'
            '<div class="wr-main">'
            '<div class="wr-line"><span class="wr-mean">%(ld)s<em>N 均值</em></span>'
            '<span class="wr-range">%(lo)s – %(hi)s N</span></div>'
            '<div class="wr-track"><span class="wr-span" style="left:%(left).2f%%;width:%(w).2f%%"></span>'
            '<span class="wr-avg" style="left:%(avg).2f%%"></span></div>'
            '</div>'
            '<div class="wr-meta">%(air)s%(slip)s</div>'
            '</div>'
            % {"fill": x["fill"], "cn": x["cn"], "tag": x["tag"], "ld": _num(x["ld"]),
               "lo": _num(x["lmin"]), "hi": _num(x["lmax"]), "left": left, "w": width,
               "avg": avg, "air": _air_chip(x["air"]), "slip": _slip_chip(x["slip"])}
        )
    return "".join(out)


# ══════════════════════════════════════════════════════════════════════
# ③ 右栏：配重 / 汇总 / 四轮明细表
# ══════════════════════════════════════════════════════════════════════
def _balance_card(d):
    wb = d.get("wb") or {}
    front, rear = wb.get("front", 50.0), wb.get("rear", 50.0)
    left, right = wb.get("left", 50.0), wb.get("right", 50.0)
    lr_diff = wb.get("lr_diff", 0.0)
    lr_ok = bool(wb.get("lr_ok", True))
    cross = wb.get("cross", 50.0)
    cross_dev = wb.get("cross_dev", 0.0)
    cross_ok = bool(wb.get("cross_ok", True))

    icon = _ICON_CHECK if lr_ok else _ICON_WARN
    if lr_ok:
        note = "左右差 <b>%.1f%%</b> · 正常，左右基本平衡" % lr_diff
    else:
        note = "左右差 <b>%.1f%%</b> · 偏了，先查胎压和配重（超过 5%%）" % lr_diff
    if cross_ok:
        cross_txt = "理想 50%% · 偏差 %.1f%%，弯道左右手感一致" % cross_dev
    else:
        cross_txt = "理想 50%% · 偏差 +%.1f%%，弯道左右会不一致，先查配重" % cross_dev

    return (
        '<article class="card w-bal">'
        '<div class="panel-head"><div><h2>配重</h2>'
        '<p>按四轮平均载荷算的整车平衡</p></div>'
        '<span class="mini-chip">理想 50 / 50</span></div>'
        '<div class="bal-rows">'
        '<div class="bal-row">'
        '<div class="bal-top"><span>前后配重</span>'
        '<span><b>%.1f%%</b> 前 · <b>%.1f%%</b> 后</span></div>'
        '<div class="bal-bar"><span style="width:%.2f%%;background:linear-gradient(90deg,#7FB3D5,#5B8FB9)"></span>'
        '<span style="width:%.2f%%;background:linear-gradient(90deg,#9FCFBA,#4E9E7B)"></span></div>'
        '</div>'
        '<div class="bal-row">'
        '<div class="bal-top"><span>左右配重</span>'
        '<span><b>%.1f%%</b> 左 · <b>%.1f%%</b> 右</span></div>'
        '<div class="bal-bar"><span style="width:%.2f%%;background:linear-gradient(90deg,#7FB3D5,#5B8FB9)"></span>'
        '<span style="width:%.2f%%;background:linear-gradient(90deg,#E8C88A,#D9A24A)"></span></div>'
        '</div>'
        '</div>'
        '<div class="lr-note %s">%s<div>%s</div></div>'
        '<div class="cross-line"><span>对角配重</span><b>%.1f%%</b></div>'
        '<div class="cross-hint%s">%s</div>'
        '</article>'
        % (front, rear, front, rear, left, right, left, right,
           "ok" if lr_ok else "bad", icon, note, cross,
           "" if cross_ok else " warn", cross_txt)
    )


def _sig_rows(d):
    rows = d.get("wheel_rows") or []
    mx = max([x["sig"] for x in rows] or [1.0]) or 1.0
    out = []
    for x in rows:
        w = max(x["sig"] / mx * 100.0, 2.0)
        out.append('<div class="sig-row"><span class="sig-tag">%s</span>'
                   '<span class="sig-track"><i style="width:%.1f%%;background:%s"></i></span>'
                   '<span class="sig-val">%s</span></div>'
                   % (x["tag"], w, AXIS_COLOR[x["axis"]], _num(x["sig"])))
    return "".join(out)


def _summary_card(d):
    sig = d.get("sig_info") or {}
    busiest = "%s %s · σ %s N" % (esc(sig.get("max_cn", "—")),
                                  esc(sig.get("max_tag", "—")), _num(sig.get("max")))
    return (
        '<article class="card w-sum">'
        '<div class="panel-head"><div><h2>汇总</h2>'
        '<p>整车重量与轮荷波动</p></div>'
        '<span class="mini-chip">σ 看前后轴</span></div>'
        '<dl class="kv">'
        '<div class="kv-row"><dt>整车质量</dt><dd>≈ %s kg</dd></div>'
        '<div class="kv-row"><dt>最忙的轮子</dt><dd>%s</dd></div>'
        '</dl>'
        '<div class="sig-head"><span>四轮轮荷 σ</span>'
        '<span>前轴 <b>%s</b> · 后轴 <b>%s</b> N</span></div>'
        '<div class="sig-rows">%s</div>'
        '<p class="sig-note">%s<span>σ 是轮荷标准差，只跟轮子负载波动有关、<b>与安装几何无关</b>；'
        '前后轴谁更忙只看 σ，减振器速度 RMS 前后不能直接比。</span></p>'
        '</article>'
        % (_num(d.get("mass")), busiest, _num(sig.get("f")), _num(sig.get("r")),
           _sig_rows(d), IC["info"])
    )


def _table_card(d):
    rows = d.get("wheel_rows") or []
    body = []
    for x in rows:
        slip = float(x["slip"])
        cls = "slip-spin" if slip > 0.8 else ("slip-lock" if slip < -0.8 else "slip-ok")
        air_cls = "air-hi" if (x["air"] or 0.0) >= 0.5 else ""
        body.append(
            '<tr><td><i class="wdot" style="background:%s"></i>%s <em>%s</em></td>'
            '<td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
            '<td class="%s">%s%%</td><td class="%s">%.1f%%</td></tr>'
            % (x["fill"], x["cn"], x["tag"], _num(x["ld"]), _num(x["lmin"]),
               _num(x["lmax"]), _num(x["sig"]), cls, _signed(x["slip"]),
               air_cls, x["air"])
        )
    return (
        '<article class="card w-table">'
        '<div class="panel-head"><div><h2>四轮明细</h2>'
        '<p>均值 / 最小 / 最大 / σ / 滑移 / 离地</p></div></div>'
        '<table class="wt"><colgroup>'
        '<col style="width:17%%"><col style="width:14%%"><col style="width:14%%">'
        '<col style="width:15%%"><col style="width:13%%"><col style="width:14%%">'
        '<col style="width:13%%"></colgroup>'
        '<thead><tr><th>轮位</th><th>均值</th><th>最小</th><th>最大</th>'
        '<th>σ</th><th>滑移</th><th>离地</th></tr></thead>'
        '<tbody>%s</tbody></table>'
        '<p class="wt-foot">载荷单位 N，滑移 / 离地单位 %% · 滑移 &gt;0 打滑、&lt;0 抱死</p>'
        '</article>' % "".join(body)
    )


# ══════════════════════════════════════════════════════════════════════
# render
# ══════════════════════════════════════════════════════════════════════
def _empty_page(d):
    body = ('<section class="page-body"><article class="card page-card" style="flex:1">%s'
            '</article></section>'
            % empty_state("car", "这份数据没有四轮载荷",
                          "CSV 里没有轮荷列（FLld / FRld / RLld / RRld），或者采样点太少。"
                          "换一份用新版抓包的文件再看。"))
    return ('<section class="page" data-page="wheels" data-title="四轮载荷">\n%s%s\n</section>'
            % (_head(d), body))


def render(d):
    """返回完整的一页：<section class="page" data-page="wheels"> ... </section>。"""
    if not d.get("wheels_ok") or not d.get("wheel_rows"):
        return _empty_page(d)

    body = (
        '<section class="page-body">'
        '<section class="w-grid">'
        '<div class="w-left">'
        '<article class="card w-car">'
        '<div class="panel-head"><div><h2>四轮载荷分布</h2>'
        '<p>俯视示意 · 圆圈颜色越深 = 平均载荷越大 · 轮内依次是 均值 N / 占整车比 / 轮荷 σ</p></div>'
        '<span class="mini-chip">四轮合计 %s N</span></div>'
        '<div class="w-svg-wrap">%s</div>'
        '</article>'
        '<article class="card w-detail">'
        '<div class="panel-head"><div><h2>每轮载荷范围</h2>'
        '<p>条形 = 全程最小 → 最大载荷 · 圆点 = 平均载荷</p></div>'
        '<span class="mini-chip">量程 0 – %s N</span></div>'
        '<div class="wr-list">%s</div>'
        '<div class="wr-foot">%s<span>离地 = 轮荷低于触地阈值的采样占比</span></div>'
        '</article>'
        '</div>'
        '<aside class="w-side">%s%s%s</aside>'
        '</section>'
        '</section>'
        % (_num(d.get("wheel_total")), _car_svg(d), _num(d.get("wheel_scale")),
           _range_rows(d), IC["info"], _balance_card(d), _summary_card(d), _table_card(d))
    )
    return ('<section class="page" data-page="wheels" data-title="四轮载荷">\n%s%s\n</section>'
            % (_head(d), body))


# ══════════════════════════════════════════════════════════════════════
# 本页 CSS / JS
# ══════════════════════════════════════════════════════════════════════
CSS = r"""
/* ══ 四轮载荷页 ══════════════════════════════════════════════════════ */
.w-grid{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 388px;gap:16px}
.w-left{display:flex;flex-direction:column;gap:16px;min-height:0}
.w-car,.w-detail{display:flex;flex-direction:column;padding:16px 20px 14px;min-height:0}
.w-car{flex:1.18}
.w-detail{flex:1}
.w-svg-wrap{position:relative;flex:1;min-height:0;margin-top:2px}
.car-svg{position:absolute;inset:0;width:100%;height:100%;display:block}
.car-svg text{font-family:"Microsoft YaHei UI","Segoe UI",sans-serif}
.cwn{font-size:12px;font-weight:600;fill:#4B6072}
.cwt{font-size:10px;font-weight:500;fill:#8496A7;letter-spacing:.05em}
.cwl{font-size:19px;font-weight:700;letter-spacing:-.01em;font-variant-numeric:tabular-nums}
.cws{font-size:10.2px;font-weight:500;letter-spacing:.01em;font-variant-numeric:tabular-nums}
.caxl{font-size:10.8px;fill:#8496A7;letter-spacing:.02em}
.caxv{font-size:14px;font-weight:700;fill:#1F2E3C;font-variant-numeric:tabular-nums}
.caxv2{font-size:12.5px;font-weight:700;fill:#3E6B92;font-variant-numeric:tabular-nums}
.caxbig{font-size:23px;font-weight:700;fill:#1F2E3C;letter-spacing:-.01em;font-variant-numeric:tabular-nums}
.caxu{font-size:11px;font-weight:600;fill:#8496A7}
.cair{font-size:10.5px;font-weight:600;fill:#B67C22}

/* ── 每轮范围 ── */
.wr-list{flex:1;min-height:0;display:flex;flex-direction:column;justify-content:space-between;gap:6px;margin-top:8px}
.wr-row{display:flex;align-items:center;gap:14px;padding:7px 12px 7px 9px;border-radius:12px;
  background:rgba(255,255,255,.44);border:1px solid rgba(255,255,255,.66);
  transition:background .3s var(--ease),transform .3s var(--ease)}
.wr-row:hover{background:rgba(255,255,255,.76);transform:translateY(-1px)}
.wr-id{flex:0 0 58px;display:flex;align-items:center;gap:8px}
.wr-dot{flex:0 0 10px;width:10px;height:10px;border-radius:50%;
  box-shadow:0 0 0 3px rgba(91,143,185,.12)}
.wr-id b{display:block;font-size:12.4px;font-weight:600;color:var(--ink);line-height:1.15}
.wr-id i{font-style:normal;font-size:9.4px;letter-spacing:.07em;color:var(--muted)}
.wr-main{flex:1;min-width:0}
.wr-line{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:6px}
.wr-mean{font-size:13.4px;font-weight:700;color:var(--ink);font-variant-numeric:tabular-nums}
.wr-mean em{font-style:normal;font-size:10px;font-weight:500;color:var(--muted);margin-left:3px}
.wr-range{font-size:10.5px;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.wr-track{position:relative;height:9px;border-radius:999px;background:rgba(91,143,185,.10);
  box-shadow:inset 0 1px 2px rgba(60,90,120,.10)}
.wr-span{position:absolute;top:0;bottom:0;border-radius:999px;background:var(--wc);
  box-shadow:0 4px 10px -4px var(--wc)}
.wr-span::after{content:"";position:absolute;inset:0;border-radius:inherit;
  background:linear-gradient(180deg,rgba(255,255,255,.5),rgba(255,255,255,0) 72%)}
.wr-avg{position:absolute;top:50%;width:11px;height:11px;border-radius:50%;background:#fff;
  border:2.5px solid var(--wc);transform:translate(-50%,-50%);
  box-shadow:0 2px 7px -1px rgba(46,76,105,.45)}
.wr-meta{flex:0 0 122px;display:flex;flex-direction:column;align-items:flex-end;gap:4px}
.wr-chip{display:inline-flex;align-items:center;font-size:10.4px;font-weight:600;
  padding:3px 8px;border-radius:999px;white-space:nowrap;letter-spacing:.01em;
  font-variant-numeric:tabular-nums}
.wr-chip.air-on{color:#A96F12;background:rgba(217,162,74,.14);border:1px solid rgba(217,162,74,.3)}
.wr-chip.air-off{color:var(--muted);background:rgba(91,143,185,.07);border:1px solid transparent}
.wr-chip.slip-spin{color:#A96F12;background:rgba(217,162,74,.13);border:1px solid rgba(217,162,74,.26)}
.wr-chip.slip-lock{color:#A8422F;background:rgba(192,86,74,.11);border:1px solid rgba(192,86,74,.24)}
.wr-chip.slip-ok{color:#2F6B52;background:rgba(62,158,123,.11);border:1px solid rgba(62,158,123,.2)}
.wr-foot{display:flex;align-items:center;gap:7px;margin-top:8px;padding-top:8px;
  border-top:1px dashed var(--line);font-size:10.6px;color:var(--muted)}
.wr-foot .ic{width:13px;height:13px;flex:0 0 13px;color:var(--blue);opacity:.8}

/* ── 右栏 ── */
.w-side{display:flex;flex-direction:column;gap:16px;min-height:0;overflow:hidden}
.w-side>.card{flex:0 0 auto;min-height:0;display:flex;flex-direction:column;padding:16px 20px 14px}
.w-side>.w-table{flex:1 1 auto}

/* 配重 */
.bal-rows{margin-top:13px;display:flex;flex-direction:column;gap:14px}
.bal-top{display:flex;align-items:baseline;justify-content:space-between;gap:10px;
  margin-bottom:6px;font-size:11.3px;color:var(--muted);letter-spacing:.02em}
.bal-top b{color:var(--ink);font-weight:700;font-variant-numeric:tabular-nums;font-size:12.4px}
.bal-bar{display:flex;height:9px;border-radius:999px;overflow:hidden;
  background:rgba(91,143,185,.10);box-shadow:inset 0 1px 2px rgba(60,90,120,.12)}
.bal-bar span{display:block;height:100%}
.lr-note{display:flex;align-items:flex-start;gap:8px;margin-top:15px;padding:8px 11px;
  border-radius:11px;font-size:11.2px;line-height:1.5}
.lr-note .ic{flex:0 0 15px;width:15px;height:15px;margin-top:1px}
.lr-note.ok{color:#2F6B52;background:rgba(62,158,123,.10);border:1px solid rgba(62,158,123,.18)}
.lr-note.bad{color:#A8422F;background:rgba(192,86,74,.11);border:1px solid rgba(192,86,74,.28)}
.lr-note b{font-weight:700;font-variant-numeric:tabular-nums}
.cross-line{display:flex;align-items:baseline;justify-content:space-between;gap:10px;
  margin-top:12px;font-size:11.3px;color:var(--muted)}
.cross-line b{color:var(--ink);font-weight:700;font-size:13px;font-variant-numeric:tabular-nums}
.cross-hint{margin-top:3px;font-size:10.4px;color:var(--muted)}
.cross-hint.warn{color:#A8422F;font-weight:600}

/* 汇总 */
.w-sum .kv{margin:8px 0 0}
.sig-head{display:flex;align-items:baseline;justify-content:space-between;gap:8px;
  margin:13px 0 8px;font-size:10.9px;color:var(--muted)}
.sig-head b{color:var(--ink-2);font-weight:700;font-variant-numeric:tabular-nums}
.sig-rows{display:flex;flex-direction:column;gap:6px}
.sig-row{display:flex;align-items:center;gap:9px}
.sig-tag{flex:0 0 20px;font-size:10px;font-weight:700;color:var(--muted);letter-spacing:.04em}
.sig-track{flex:1;height:6px;border-radius:999px;background:rgba(91,143,185,.09);overflow:hidden}
.sig-track i{display:block;height:100%;border-radius:999px}
.sig-val{flex:0 0 42px;text-align:right;font-size:10.8px;font-weight:600;color:var(--ink-2);
  font-variant-numeric:tabular-nums}
.sig-note{display:flex;align-items:flex-start;gap:8px;margin:auto 0 0;padding-top:11px;
  border-top:1px dashed var(--line);font-size:10.5px;line-height:1.55;color:var(--muted)}
.sig-note .ic{flex:0 0 14px;width:14px;height:14px;margin-top:1px;color:var(--blue);opacity:.85}
.sig-note b{color:var(--ink-2);font-weight:600}

/* 四轮明细表 */
.wt{width:100%;border-collapse:collapse;table-layout:fixed;margin-top:9px;
  font-variant-numeric:tabular-nums}
.wt th{font-size:9.7px;font-weight:600;color:var(--muted);letter-spacing:.02em;
  text-align:right;padding:0 0 6px;white-space:nowrap}
.wt th:first-child{text-align:left}
.wt td{font-size:10.9px;color:var(--ink-2);text-align:right;padding:6.5px 0;
  border-top:1px dashed var(--line);white-space:nowrap}
.wt tbody tr:first-child td{border-top:1px solid var(--line)}
.wt td:first-child{text-align:left;color:var(--ink);font-weight:600}
.wt .wdot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px;
  vertical-align:1px}
.wt td em{font-style:normal;color:var(--muted);font-size:9px;letter-spacing:.05em;margin-left:2px}
.wt .slip-spin{color:#A96F12;font-weight:600}
.wt .slip-lock{color:#A8422F;font-weight:600}
.wt .slip-ok{color:#2F6B52;font-weight:600}
.wt .air-hi{color:#A96F12;font-weight:600}
.wt-foot{margin:auto 0 0;padding-top:10px;border-top:1px dashed var(--line);
  font-size:10.2px;line-height:1.5;color:var(--muted)}

/* 入场动画 */
.w-car{animation:rise .7s .22s var(--ease) backwards}
.w-detail{animation:rise .7s .3s var(--ease) backwards}
.w-side .card:nth-child(1){animation:rise .7s .26s var(--ease) backwards}
.w-side .card:nth-child(2){animation:rise .7s .3s var(--ease) backwards}
.w-side .card:nth-child(3){animation:rise .7s .34s var(--ease) backwards}

@media (max-width:1240px){
  /* 窄屏：整页可滚动，左栏两张卡纵向排，右栏三张卡改成一行 */
  .page[data-page="wheels"]{overflow-y:auto;overflow-x:hidden;gap:14px}
  .page[data-page="wheels"] .page-body{flex:0 0 auto;min-height:0}
  .w-grid{display:flex;flex-direction:column;flex:0 0 auto;height:auto;gap:14px}
  .w-left{flex:0 0 auto}
  .w-car{flex:0 0 auto;min-height:440px}
  .w-detail{flex:0 0 auto;min-height:340px}
  .w-side{flex:0 0 auto;flex-direction:row;flex-wrap:wrap;overflow:visible}
  .w-side>.card{flex:1 1 300px}
}
@media (max-width:760px){
  .w-side{flex-direction:column}
  .w-car{min-height:380px}
}
"""

JS = r"""
// 四轮载荷页：静态示意图，条形位置都由服务端算好，这里只留一个钩子
window.PAGE_INIT = window.PAGE_INIT || {};
window.PAGE_INIT.wheels = function (root, DATA) {
  if (root) root.classList.add('w-ready');
};
"""
