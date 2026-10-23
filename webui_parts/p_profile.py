# -*- coding: utf-8 -*-
"""赛道剖面页 —— 高程剖面 + 车速（右轴）+ 分段颠簸；滚轮缩放 / 拖拽平移 / 双击复位

数据口径全部来自 analyze()（经 web_ui.build_data 注入的 d）：
  d["profile_pts"]  [里程, 高程 z, 车速 km/h, 油门, 刹车]
  d["segments"]     每 500 m 一段：{d0, n, rms, v}
  d["z_min/z_max"] / d["climb"] / d["grade"] / 均速 / 最高速 / 时长
本页只在 build() 里补「画图用」的派生字段（段条、峰值位置、采样间距），
不改任何公共字段、不写死数据数字。
"""

from .common import (
    IC, chip, empty_state, esc, fmt_dist, fmt_dur, head_html, legend,
)

KEY = "profile"
LABEL = "赛道剖面"          # 左侧导航上的文字（尽量 ≤4 字）
ICON = "route"            # common.IC 里的图标 key
TITLE = "赛道剖面"          # 页面大标题
BADGE = ""          # 标题旁小标签，可留空
SUB = "这一页看什么：路面高低起伏、坡度和车速，以及哪一段最颠。"              # 标题下一行说明（"这一页看什么：..."）
ORDER = 2

# 老程序里对应这一页的代码：
#   老 tkinter 版 _draw_profile（已删除）：高程 + 车速两条带、缩放平移复位；这里的交互比它更全

# 分段颠簸的色阶端点：蓝 → 黄 → 红（和首页三档配色同一套颜色）
_RAMP = ((0.0, (79, 134, 178)), (0.5, (223, 169, 79)), (1.0, (210, 104, 90)))
_BLUE = "#5B8FB9"
_WARM = "#D9A24A"


# ══════════════════════════════════════════════════════════════════════
# 小工具
# ══════════════════════════════════════════════════════════════════════
def _f1(v):
    return "—" if v is None else "%.1f" % float(v)


def _f0(v):
    return "—" if v is None else "%.0f" % float(v)


def _f2(v):
    return "—" if v is None else "%.2f" % float(v)


def _pct(v):
    return "—" if v is None else "%.1f %%" % (float(v) * 100.0)


def _mix(c1, c2, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


def _ramp(t):
    """0=蓝 0.5=黄 1=红，返回 #RRGGBB。"""
    try:
        t = max(0.0, min(1.0, float(t)))
    except (TypeError, ValueError):
        t = 0.0
    mid, rmid = _RAMP[1][0], _RAMP[1][1]
    if t <= mid:
        c = _mix(_RAMP[0][1], rmid, t / mid if mid else 0.0)
    else:
        c = _mix(rmid, _RAMP[2][1], (t - mid) / (1.0 - mid))
    return "#%02X%02X%02X" % c


def _chips(d, dist, dur, points):
    level = " ".join(str(d.get("level") or "—").replace("_", " ").split()) or "—"
    return (
        chip("pin", level)
        + chip("route", "%s · %s" % (fmt_dist(dist), fmt_dur(dur)))
        + '<span class="chip live"><span class="dot"></span>已载入 %s 点</span>'
        % "{:,}".format(points)
    )


# ══════════════════════════════════════════════════════════════════════
# 数据
# ══════════════════════════════════════════════════════════════════════
def build(r, d):
    """analyze() 结果 r -> 往共享数据 d 里补本页字段（必须是 JSON 能序列化的）。"""
    pts = d.get("profile_pts") or []
    try:
        dist = float(d.get("dist_m") or 0.0)
    except (TypeError, ValueError):
        dist = 0.0

    # ── 分段颠簸：把 analyze() 的 segments 变成能直接画的条 ──────────
    bars = []
    segs = d.get("segments") or []
    if segs:
        try:
            rmax = max(float(s.get("rms") or 0.0) for s in segs)
        except (TypeError, ValueError):
            rmax = 0.0
        rmax = rmax if rmax > 0 else 1.0
        try:
            worst_m = float(d.get("worst_m") or 0.0)
        except (TypeError, ValueError):
            worst_m = 0.0
        for i, s in enumerate(segs):
            try:
                d0 = float(s.get("d0") or 0.0)
                rms = float(s.get("rms") or 0.0)
                v = float(s.get("v") or 0.0)
                n = int(s.get("n") or 0)
            except (TypeError, ValueError):
                continue
            if i + 1 < len(segs):
                try:
                    d1 = float(segs[i + 1].get("d0") or d0)
                except (TypeError, ValueError):
                    d1 = d0
            else:
                d1 = dist if dist > d0 else d0
            bars.append({
                "i": i,
                "d0": round(d0, 1),
                "d1": round(d1, 1),
                "rms": round(rms, 4),
                "v": round(v, 1),
                "n": n,
                "ratio": round(min(1.0, rms / rmax), 4),
                "worst": abs(d0 - worst_m) < 0.5,
            })
    # 兜底：analyze() 的 worst_m 对不上任何段时，取 RMS 最大的那段
    if bars and not any(b["worst"] for b in bars):
        max(bars, key=lambda b: b["rms"])["worst"] = True
    d["prof_bars"] = bars

    # ── 峰值位置（图表下方标注：最高点 / 最低点 / 最高车速在哪）─────
    peaks = {}
    try:
        good = [p for p in pts if len(p) > 2 and all(
            isinstance(x, (int, float)) for x in (p[0], p[1], p[2]))]
    except TypeError:
        good = []
    if good:
        zpk = max(good, key=lambda p: p[1])
        zlo = min(good, key=lambda p: p[1])
        vpk = max(good, key=lambda p: p[2])
        peaks = {
            "z_max": round(float(zpk[1]), 2), "z_max_at": round(float(zpk[0]), 0),
            "z_min": round(float(zlo[1]), 2), "z_min_at": round(float(zlo[0]), 0),
            "v_max": round(float(vpk[2]), 1), "v_max_at": round(float(vpk[0]), 0),
        }
    d["prof_peaks"] = peaks

    # ── 最陡坡度位置（只有和 analyze() 的 grade 对得上时才标，避免抽稀误差）
    grade_at = None
    try:
        gm = 0.0
        gat = 0.0
        prev = None
        for p in good:
            if prev is not None:
                dd = float(p[0]) - float(prev[0])
                dz = float(p[1]) - float(prev[1])
                if dd > 0.5:
                    gg = abs(dz) / dd
                    if gg > gm:
                        gm, gat = gg, (float(p[0]) + float(prev[0])) / 2.0
            prev = p
        rep = d.get("grade")
        if rep and gm > 0 and abs(gm - float(rep)) <= max(0.005, 0.02 * float(rep)):
            grade_at = round(gat, 0)
    except (TypeError, ValueError, ZeroDivisionError):
        grade_at = None
    d["prof_grade_at"] = grade_at

    # ── 平均采样间距（说明坡度分辨率用）─────────────────────────────
    d["prof_spacing"] = (
        round(dist / (len(pts) - 1), 2) if len(pts) > 1 and dist > 0 else 0.0
    )
    return d


# ══════════════════════════════════════════════════════════════════════
# 片段
# ══════════════════════════════════════════════════════════════════════
def _chart_card(d, pts):
    pk = d.get("prof_peaks") or {}
    head = (
        '<div class="chart-head">'
        '<div><h2>路面剖面</h2>'
        '<p>高程 z 随里程起伏，车速叠在右轴（虚线）· 悬停看具体数值</p></div>'
        '<div class="chart-tools">%s'
        '<button class="chart-reset" type="button" title="双击图表也能复位">复位</button>'
        '</div></div>'
    ) % legend([("高程 (m)", _BLUE, False), ("车速 (km/h)", _WARM, True)])

    if pts:
        chart = '<div class="chart" id="chart-profile"></div>'
        hint = ('<span class="hint">%s滚轮缩放 · 拖拽平移 · 双击复位</span>' % IC["info"])
        if pk:
            foot = (
                '<div class="chart-foot">%s'
                '<span class="chart-peaks">'
                '<span>最高点 <b>%s m</b> @ %s m</span><i>·</i>'
                '<span>最低点 <b>%s m</b> @ %s m</span><i>·</i>'
                '<span>最高车速 <b>%s km/h</b> @ %s m</span>'
                '</span></div>'
            ) % (hint,
                 _f1(pk.get("z_max")), _f0(pk.get("z_max_at")),
                 _f1(pk.get("z_min")), _f0(pk.get("z_min_at")),
                 _f1(pk.get("v_max")), _f0(pk.get("v_max_at")))
        else:
            foot = '<div class="chart-foot">%s</div>' % hint
    else:
        chart = empty_state("route", "没有剖面数据",
                            "这份 CSV 里没有可用的高程 / 车速剖面点，换个抓包文件再看。")
        foot = ""

    return '<article class="card chart-card prof-chart">%s%s%s</article>' % (
        head, chart, foot)


def _seg_rows(bars):
    rows = []
    for b in bars:
        label = "%s – %s m" % (_f0(b["d0"]), _f0(b["d1"]))
        c = _ramp(b["ratio"])
        width = max(3.0, b["ratio"] * 100.0)
        tag = '<span class="seg-tag">最颠</span>' if b["worst"] else ""
        rows.append((
            '<div class="seg-row%s">'
            '<div class="seg-main">'
            '<div class="seg-top"><span class="seg-name">%s</span>%s'
            '<span class="seg-speed">均速 %s km/h</span></div>'
            '<div class="seg-track"><i class="seg-fill" '
            'style="width:%.1f%%;background:linear-gradient(90deg,%s,%s)"></i></div>'
            '</div>'
            '<div class="seg-val"><b>%s</b><small>m/s</small></div>'
            '</div>'
        ) % (" worst" if b["worst"] else "", esc(label), tag,
             _f0(b["v"]), width, _BLUE, c, _f2(b["rms"])))
    return "".join(rows)


def _seg_card(d):
    bars = d.get("prof_bars") or []
    head = (
        '<div class="panel-head">'
        '<div><h2>分段颠簸</h2>'
        '<p>每 500 m 一段 · 条长 = 该段 RMS ÷ 最颠段 RMS，颜色越暖越颠</p></div>'
        '<div class="seg-legend"><span>平顺</span><i class="ramp"></i><span>颠簸</span></div>'
        '</div>'
    )
    if bars:
        body = '<div class="seg-list">%s</div>' % _seg_rows(bars)
    else:
        body = empty_state("wave", "没有分段数据",
                           "里程太短、还凑不满一段，或 CSV 里没有减振器速度列。")
    return '<article class="card chart-card prof-seg">%s%s</article>' % (head, body)


def _stat_card(d, dist, dur, points):
    zmin, zmax = d.get("z_min"), d.get("z_max")
    climb, grade = d.get("climb"), d.get("grade")
    vavg, vmax = d.get("v_avg_kmh"), d.get("v_max_kmh")
    zrange = ("%s – %s m" % (_f1(zmin), _f1(zmax))
              if (zmin is not None and zmax is not None) else "—")
    rows = [
        ("高程范围", zrange),
        ("累计爬升", "%s m" % _f1(climb) if climb is not None else "—"),
        ("最大坡度", _pct(grade)),
        ("均速", "%s km/h" % _f1(vavg) if vavg is not None else "—"),
        ("最高车速", "%s km/h" % _f1(vmax) if vmax is not None else "—"),
        ("时长", fmt_dur(dur)),
    ]
    kv = "".join(
        '<div class="kv-row"><dt>%s</dt><dd>%s</dd></div>' % (esc(k), esc(v))
        for k, v in rows
    )
    return (
        '<article class="card">'
        '<div class="panel-head"><div><h2>概况</h2>'
        '<p>全程 %s · %s 点 @ 10 Hz</p></div>'
        '<span class="mini-chip">10 Hz</span></div>'
        '<dl class="kv">%s</dl>'
        '</article>'
    ) % (esc(fmt_dist(dist)), "{:,}".format(points), kv)


def _worst_card(d, bars, dist):
    worst = None
    for b in bars:
        if b["worst"]:
            worst = b
            break
    if not worst:
        return (
            '<article class="card">'
            '<div class="panel-head"><div><h2>最颠的一段</h2>'
            '<p>四角减振器工作速度 RMS</p></div></div>'
            '%s</article>'
        ) % empty_state("pin", "没有分段数据", "这份数据没有足够长的里程来分段统计。")
    seg_tag = "起点段" if worst["d0"] < 1 else "第 %d 段" % (worst["i"] + 1)
    try:
        pos = float(d.get("worst_pos") or 0.0)
    except (TypeError, ValueError):
        pos = 0.0
    pos = min(max(pos, 1.6), 98.4)
    return (
        '<article class="card">'
        '<div class="panel-head"><div><h2>最颠的一段</h2>'
        '<p>RMS 最高的一段 · 每 500 m 统计</p></div>'
        '<span class="mini-chip">%s</span></div>'
        '<div class="worst-big">%s – %s m</div>'
        '<div class="track-mini"><span class="mk" style="left:%.2f%%"></span></div>'
        '<div class="worst-meta">该段 RMS <b>%s m/s</b> · 均速 <b>%s km/h</b></div>'
        '<div class="worst-foot">全程 %s · 这一段最颠</div>'
        '</article>'
    ) % (esc(seg_tag), _f0(worst["d0"]), _f0(worst["d1"]), pos,
         _f2(worst["rms"]), _f0(worst["v"]), esc(fmt_dist(dist)))


def _note_card(d, dist, points):
    climb, grade = d.get("climb"), d.get("grade")
    zmin, zmax = d.get("z_min"), d.get("z_max")
    spacing = d.get("prof_spacing") or 0.0
    grade_at = d.get("prof_grade_at")
    items = []
    if grade is not None:
        if float(grade) < 0.002:
            items.append("最大坡度 <b>%s</b>：这一段基本是平路，高程只在采集噪声范围内变化。"
                         % _pct(grade))
        else:
            where = ("最陡处在 <b>%s m</b> 附近：" % _f0(grade_at)) if grade_at is not None else "全程最大："
            items.append(
                "最大坡度 = 相邻采样点高差 ÷ 里程差。%s<b>%s</b>，相当于每 100 m "
                "抬升 <b>%s m</b>。" % (where, _pct(grade), _f1(float(grade) * 100.0)))
    if climb is not None and zmin is not None and zmax is not None:
        drop = float(zmax) - float(zmin)
        if climb > drop + 0.3:
            tail = ("<b>%s m</b> 比高程落差 <b>%s m</b> 大，说明中间有明显起伏，"
                    "不是一路单调上下坡。" % (_f1(climb), _f1(drop)))
        elif climb < drop - 0.3:
            tail = ("<b>%s m</b> 小于高程落差 <b>%s m</b>，说明整体以下坡为主。" %
                    (_f1(climb), _f1(drop)))
        else:
            tail = ("<b>%s m</b> 和高程落差 <b>%s m</b> 接近，基本是一路抬升。" %
                    (_f1(climb), _f1(drop)))
        items.append("累计爬升只累计上坡、不扣下坡：" + tail)
    if spacing > 0:
        items.append("平均每 <b>%s m</b> 一个采样点，最大坡度受采样间距限制，"
                     "不等于每个位置都这么陡。" % _f1(spacing))
    if grade is not None:
        items.append("坡度是相邻采样点之间的平均值，短距离尖峰会摊平；想确认某一段陡不陡，"
                     "把剖面图放大到那 100 m 看曲线。")
    if not items:
        items.append("这份数据缺高程 / 坡度字段，所以这一页只能看车速。")
    lis = "".join("<li>%s</li>" % t for t in items)
    return (
        '<article class="card prof-note">'
        '<div class="panel-head"><div><h2>坡度怎么读</h2>'
        '<p>和首页同一套 analyze() 口径 · 坡度与爬升怎么算</p></div></div>'
        '<ul class="note-list">%s</ul>'
        '<div class="note-foot">10 Hz · %s 点 · 全程 %s</div>'
        '</article>'
    ) % (lis, "{:,}".format(points), esc(fmt_dist(dist)))


# ══════════════════════════════════════════════════════════════════════
# 页面
# ══════════════════════════════════════════════════════════════════════
def render(d):
    """返回完整的一页：<section class="page" data-page="profile"> ... </section>。"""
    pts = d.get("profile_pts") or []
    bars = d.get("prof_bars") or []
    try:
        dist = float(d.get("dist_m") or 0.0)
    except (TypeError, ValueError):
        dist = 0.0
    try:
        dur = float(d.get("dur_s") or 0.0)
    except (TypeError, ValueError):
        dur = 0.0
    points = int(d.get("points") or 0)
    file_name = d.get("file") or "—"
    stem = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
    badge = "原厂悬挂" if d.get("stock") else "改装悬挂"

    head = head_html(stem, file_name, TITLE, badge, SUB,
                     _chips(d, dist, dur, points))
    body = (
        '<section class="page-body">'
        '<section class="grid">'
        '<div class="prof-left">%s%s</div>'
        '<aside class="side">%s%s%s</aside>'
        '</section>'
        '</section>'
    ) % (
        _chart_card(d, pts),
        _seg_card(d),
        _stat_card(d, dist, dur, points),
        _worst_card(d, bars, dist),
        _note_card(d, dist, points),
    )
    return (
        '<section class="page" data-page="profile" data-title="%s">\n%s%s\n</section>'
    ) % (esc(TITLE), head, body)


CSS = """/* ═══ 赛道剖面页 ═══════════════════════════════════════════════ */
.page[data-page="profile"] .prof-left{display:flex;flex-direction:column;gap:16px;min-height:0}
.page[data-page="profile"] .prof-chart{flex:1;min-height:0}
.page[data-page="profile"] .chart-head h2{margin:0;font-size:16.5px;font-weight:700;
  letter-spacing:.01em;color:var(--ink)}
.page[data-page="profile"] .chart-head p{margin:5px 0 0;font-size:11.9px;color:var(--muted);
  letter-spacing:.01em}
.page[data-page="profile"] .chart-tools{display:flex;align-items:center;gap:16px;
  flex-wrap:wrap;justify-content:flex-end;padding-top:2px}
.page[data-page="profile"] .chart-tools .legend{gap:13px}
.page[data-page="profile"] .chart-reset{height:28px;padding:0 13px;border-radius:9px;
  border:1px solid rgba(91,143,185,.24);background:rgba(255,255,255,.74);color:var(--blue-3);
  font-family:inherit;font-size:11.5px;font-weight:600;letter-spacing:.02em;cursor:pointer;
  box-shadow:0 7px 16px -12px rgba(50,80,110,.85);
  transition:background .25s,transform .25s var(--ease),box-shadow .25s}
.page[data-page="profile"] .chart-reset:hover{background:#fff;transform:translateY(-1px);
  box-shadow:0 10px 20px -12px rgba(50,80,110,.9)}
.page[data-page="profile"] .chart-foot{display:flex;align-items:center;justify-content:space-between;
  gap:16px;margin-top:9px;font-size:11.5px;color:var(--muted)}
.page[data-page="profile"] .chart-peaks{display:flex;align-items:baseline;gap:9px;
  font-variant-numeric:tabular-nums;color:var(--ink-2);white-space:nowrap}
.page[data-page="profile"] .chart-peaks b{color:var(--ink);font-weight:600}
.page[data-page="profile"] .chart-peaks i{font-style:normal;color:var(--muted);opacity:.55}

/* 分段颠簸 */
.page[data-page="profile"] .prof-seg{flex:0 0 auto}
.page[data-page="profile"] .seg-legend{display:flex;align-items:center;gap:8px;padding-top:3px;
  font-size:10.8px;color:var(--muted);letter-spacing:.05em;white-space:nowrap}
.page[data-page="profile"] .seg-legend .ramp{width:78px;height:7px;border-radius:999px;
  background:linear-gradient(90deg,#4F86B2,#DFA94F,#D2685A);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.45),0 5px 12px -7px rgba(91,143,185,.9)}
.page[data-page="profile"] .seg-list{display:flex;flex-direction:column;gap:8px;margin-top:11px;
  max-height:212px;overflow:auto;padding-right:2px}
.page[data-page="profile"] .seg-row{display:grid;grid-template-columns:minmax(0,1fr) 96px;
  align-items:center;gap:16px;padding:9px 14px 10px;border-radius:12px;
  background:rgba(255,255,255,.5);border:1px solid rgba(255,255,255,.72);
  transition:background .3s,transform .3s var(--ease),box-shadow .3s}
.page[data-page="profile"] .seg-row:hover{background:rgba(255,255,255,.82);transform:translateY(-1px);
  box-shadow:0 14px 28px -24px rgba(50,80,110,.7)}
.page[data-page="profile"] .seg-row.worst{background:rgba(255,255,255,.8);
  border-color:rgba(210,104,90,.26);box-shadow:0 16px 32px -26px rgba(210,104,90,.8)}
.page[data-page="profile"] .seg-top{display:flex;align-items:center;gap:9px;margin-bottom:8px}
.page[data-page="profile"] .seg-name{font-size:12.6px;font-weight:600;color:var(--ink);
  font-variant-numeric:tabular-nums;white-space:nowrap}
.page[data-page="profile"] .seg-tag{font-size:9.8px;font-weight:700;letter-spacing:.04em;
  padding:2px 7px 2.5px;border-radius:999px;color:#A94A3C;background:rgba(210,104,90,.13);
  border:1px solid rgba(210,104,90,.22)}
.page[data-page="profile"] .seg-speed{margin-left:auto;padding-left:10px;font-size:10.8px;
  color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums}
.page[data-page="profile"] .seg-track{height:16px;border-radius:999px;background:rgba(91,143,185,.1);
  box-shadow:inset 0 1px 3px rgba(60,90,120,.12);overflow:hidden}
.page[data-page="profile"] .seg-fill{display:block;height:100%;border-radius:999px;
  transform-origin:left center;box-shadow:inset 0 1px 0 rgba(255,255,255,.35)}
.page[data-page="profile"].active .seg-fill{animation:profSeg .95s var(--ease) backwards}
.page[data-page="profile"] .seg-val{display:flex;align-items:baseline;justify-content:flex-end;
  gap:4px;font-variant-numeric:tabular-nums;
  font-family:"Segoe UI","Microsoft YaHei UI",sans-serif}
.page[data-page="profile"] .seg-val b{font-size:21px;font-weight:700;letter-spacing:-.01em;
  color:var(--ink);line-height:1}
.page[data-page="profile"] .seg-row.worst .seg-val b{color:#B8503F}
.page[data-page="profile"] .seg-val small{font-size:10.5px;color:var(--muted);
  font-family:"Microsoft YaHei UI","Segoe UI",sans-serif}
@keyframes profSeg{from{transform:scaleX(0)}to{transform:scaleX(1)}}

/* 右栏 */
.page[data-page="profile"] .side .card{display:flex;flex-direction:column}
.page[data-page="profile"] .side .card:last-child{flex:1 0 auto}
.page[data-page="profile"] .worst-big{display:flex;align-items:baseline;gap:7px;margin:8px 0 2px;
  font-size:26px;font-weight:700;letter-spacing:-.01em;color:var(--ink);
  font-variant-numeric:tabular-nums;font-family:"Segoe UI","Microsoft YaHei UI",sans-serif}
.page[data-page="profile"] .worst-big small{font-size:12px;font-weight:500;color:var(--muted);
  font-family:"Microsoft YaHei UI","Segoe UI",sans-serif}
.page[data-page="profile"] .worst-meta{margin-top:9px;font-size:11.7px;line-height:1.7;color:var(--ink-2)}
.page[data-page="profile"] .worst-meta b{color:var(--ink);font-weight:600;
  font-variant-numeric:tabular-nums}
.page[data-page="profile"] .worst-foot{margin-top:auto;padding-top:11px;font-size:10.9px;
  color:var(--muted);letter-spacing:.02em}
.page[data-page="profile"] .note-list{list-style:none;margin:11px 0 0;padding:0;
  display:flex;flex-direction:column;gap:11px}
.page[data-page="profile"] .note-list li{position:relative;padding-left:13px;font-size:11.7px;
  line-height:1.68;color:var(--ink-2)}
.page[data-page="profile"] .note-list li::before{content:"";position:absolute;left:0;top:8px;
  width:5px;height:5px;border-radius:50%;background:var(--blue-2);
  box-shadow:0 0 0 2px rgba(143,190,221,.18)}
.page[data-page="profile"] .note-list b{color:var(--ink);font-weight:600;
  font-variant-numeric:tabular-nums}
.page[data-page="profile"] .note-foot{margin-top:auto;padding-top:11px;border-top:1px dashed var(--line);
  font-size:10.9px;color:var(--muted);letter-spacing:.03em}
.page[data-page="profile"] .empty{min-height:0;padding:14px 10px}
.page[data-page="profile"] .prof-chart .empty{min-height:190px}

@media (max-width:1240px){
  /* 窄屏：两栏改一栏，整页允许纵向滚动，避免卡片被压扁后内容互相重叠 */
  .page[data-page="profile"]{overflow-y:auto;padding-right:2px}
  .page[data-page="profile"] .page-body{flex:0 0 auto}
  .page[data-page="profile"] .grid{flex:0 0 auto}
  .page[data-page="profile"] .prof-left{flex:0 0 auto;min-height:0}
  .page[data-page="profile"] .prof-chart{flex:0 0 auto;min-height:360px}
  .page[data-page="profile"] .side{overflow:visible}
  .page[data-page="profile"] .side .card,
  .page[data-page="profile"] .side .card:last-child{flex:1 1 0;min-width:0}
  .page[data-page="profile"] .worst-foot,
  .page[data-page="profile"] .note-foot{margin-top:10px}
  .page[data-page="profile"] .chart-peaks{display:none}
}
"""

JS = """// 赛道剖面页脚本：显示这一页时调用一次
window.PAGE_INIT = window.PAGE_INIT || {};
window.PAGE_INIT.profile = function (root, DATA) {
  var el = root.querySelector('#chart-profile');
  if (!el || !window.ChartKit) return;
  var pts = DATA.profile_pts || [];
  var zs = [], vs = [];
  for (var i = 0; i < pts.length; i++) {
    var p = pts[i];
    if (!p || !isFinite(p[0]) || !isFinite(p[1])) continue;
    zs.push([p[0], p[1]]);
    if (isFinite(p[2])) vs.push([p[0], p[2]]);
  }
  if (!zs.length) return;
  var chart = ChartKit.mount(el, {
    series: [
      {name: '高程', color: '#5B8FB9', data: zs, fill: true,
       fillTop: 'rgba(91,143,185,.30)', fillBottom: 'rgba(91,143,185,0)', width: 2},
      {name: '车速', color: '#D9A24A', data: vs, axis: 'y2', width: 1.6, dash: true}
    ],
    x:  {label: '里程 (m)', fmt: function (v) { return v.toFixed(0) + ' m'; }},
    y1: {label: '高程 (m)'},
    y2: {label: '车速 (km/h)'}
  });
  if (!chart) return;
  root._profileChart = chart;
  var btn = root.querySelector('.chart-reset');
  if (btn) btn.addEventListener('click', function () { chart.reset(); });
};
"""
