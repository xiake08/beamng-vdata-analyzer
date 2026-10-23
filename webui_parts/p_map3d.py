# -*- coding: utf-8 -*-
"""3D 赛道页 —— 用 profile 的 x/y/z 画可旋转的 3D 路线轨迹（纯 2D canvas 手写投影）

数据（analyze()["profile"] = (d, x, y, z, v_m/s, thr, brk, gm)）在 build() 里：
  · T.decimate_pts(..., 900) 抽稀（和画图逻辑同一个抽稀函数，不改变分析数据）
  · x / y 居中、z 相对最低点，塞进 d["map3d"] = [[x, y, z, v_kmh, thr, brk, d], ...]
  · 逐点的 500 m 段 RMS 塞进 d["map3d_rough"]（颠簸上色用，口径 = analyze()["segmap"]）
  · 自动起伏倍数（和旧版 Render3D.auto_zscale 同一条公式）
前端口径：左键拖拽旋转（yaw + pitch）、滚轮缩放（光标为锚点）、双击/按钮复位、
右键或 Shift+拖拽平移；地面网格、按指标上色的轨迹、每 N 点一条垂直帘幕、悬停最近点。
不用 three.js / 不发网络请求；只改这个文件，接口约定见 SPEC.md；Python 里不 print 中文。
"""

import math

from .common import (
    IC, chip, empty_state, esc, fmt_dist, fmt_dur, head_html,
)

KEY = "map3d"
LABEL = "3D 赛道"
ICON = "map3d"
TITLE = "3D 赛道"
BADGE = ""
SUB = "这一页看什么：把整条路线按真实 x/y/z 立起来转着看，颜色可以按高程 / 车速 / 颠簸 / 踏板切。"
ORDER = 8

_SEG_LEN = 500.0          # 颠簸分段长度（m），和 analyze() 的 SEG_LEN 一致
_MAX_PTS = 900            # 画 3D 用的抽稀点数上限
_ZSCALE_CAP = 15.0        # 起伏倍数的上限（旧版 Render3D.auto_zscale 也是 15）

# 指标按钮：(key, 显示名)
_METRICS = (("elev", "高程"), ("speed", "车速"), ("rough", "颠簸"), ("pedal", "踏板"))

# 5 段色阶（和旧版 ramp() 的色板一致）：蓝 → 青 → 绿 → 黄 → 红
_RAMP = ((0.0, (48, 92, 200)), (0.25, (40, 190, 210)), (0.5, (60, 190, 80)),
         (0.75, (230, 190, 40)), (1.0, (220, 60, 50)))
_ELEV_GRADIENT = ("linear-gradient(90deg,#305CC8 0%,#28BED2 25%,#3CBE50 50%,"
                  "#E6BE28 75%,#DC3C32 100%)")


# ══════════════════════════════════════════════════════════════════════
# 小工具
# ══════════════════════════════════════════════════════════════════════
def _num(v, default=0.0):
    """任何输入 -> 有限浮点数（JSON 里不能出现 NaN / inf）。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def _decimate(lst, maxn=_MAX_PTS):
    """本地兜底抽稀（优先用 beamng_data.decimate_pts）。"""
    n = len(lst)
    if n <= maxn:
        return list(lst)
    step = n / float(maxn)
    out = [lst[int(i * step)] for i in range(maxn)]
    if out and out[-1] is not lst[-1]:
        out[-1] = lst[-1]
    return out


def _fmt_int(v):
    try:
        return "{:,}".format(int(round(float(v))))
    except (TypeError, ValueError):
        return "—"


def _curtain_step(n):
    """帘幕线间隔（和前端 CURTAIN_STEP 同一公式，控制在 60~75 条左右）。"""
    return max(3, int(round(n / 70.0)))


# ══════════════════════════════════════════════════════════════════════
# 数据
# ══════════════════════════════════════════════════════════════════════
def build(r, d):
    """analyze() 结果 r -> 往共享数据 d 里补本页字段（必须是 JSON 能序列化的）。"""
    try:
        import beamng_data as T               # 数据引擎（纯 Python）
        decimate = T.decimate_pts
        seg_len = _num(getattr(T, "SEG_LEN", _SEG_LEN), _SEG_LEN) or _SEG_LEN
        if seg_len <= 0:
            seg_len = _SEG_LEN
    except Exception:                          # noqa: BLE001  单页不能拖垮整个程序
        decimate = _decimate
        seg_len = _SEG_LEN

    # ── 原始 profile -> 干净的点列表 (d, x, y, z, v_m/s, thr, brk) ──
    raw = []
    for p in (r.get("profile") or []):
        try:
            raw.append((_num(p[0]), _num(p[1]), _num(p[2]), _num(p[3]),
                        _num(p[4]),
                        _num(p[5]) if len(p) > 5 else 0.0,
                        _num(p[6]) if len(p) > 6 else 0.0))
        except (TypeError, IndexError, KeyError):
            continue
    if len(raw) < 2:
        d["map3d"] = []
        d["map3d_rough"] = []
        d["map3d_n"] = 0
        return d

    xs = [p[1] for p in raw]
    ys = [p[2] for p in raw]
    zs = [p[3] for p in raw]
    # 老 CSV 没有 x / y 列时 analyze() 会全给 0 —— 没有横向轨迹，3D 画不出东西
    if (max(xs) - min(xs)) < 0.5 and (max(ys) - min(ys)) < 0.5:
        d["map3d"] = []
        d["map3d_rough"] = []
        d["map3d_n"] = 0
        return d

    # ── 坐标相对化 / 居中（旧版 _setup 也是这么做的）──────────────
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    cz = min(zs)
    # 起伏倍数：落差 ≈ 水平跨度的 18%（旧版 Render3D.auto_zscale 同口径，上限 15）
    horiz = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    zspan = max(max(zs) - min(zs), 1e-6)
    zscale = max(1.0, min(_ZSCALE_CAP, horiz * 0.18 / zspan))

    # ── 500 m 分段 RMS（颠簸指标；analyze() 的 segmap 是 {段号: RMS}）──
    segmap = {}
    try:
        seg_items = list((r.get("segmap") or {}).items())
    except AttributeError:
        seg_items = []
    for k, v in seg_items:
        try:
            kk = int(float(k))
            vv = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(vv):
            segmap[kk] = vv

    # ── 抽稀后塞给前端（坐标相对化，v 换成 km/h）──────────────────
    sample = decimate(raw, _MAX_PTS) if len(raw) > _MAX_PTS else list(raw)
    out, rough = [], []
    for dd, x, y, z, v, thr, brk in sample:
        out.append([round(x - cx, 2), round(y - cy, 2), round(z - cz, 3),
                    round(v * 3.6, 1),
                    round(min(1.0, max(0.0, thr)), 3),
                    round(min(1.0, max(0.0, brk)), 3),
                    round(dd, 1)])
        rough.append(round(segmap.get(int(dd / seg_len), 0.0), 4))

    # ── 概览卡用的几个位置（最高 / 最低 / 最陡 / 最颠段）──────────
    zmax_pt = max(raw, key=lambda p: p[3])
    zmin_pt = min(raw, key=lambda p: p[3])

    grade_at = None
    gm, gat, prev = 0.0, 0.0, None
    for p in raw:
        if prev is not None:
            dd = p[0] - prev[0]
            dz = abs(p[3] - prev[3])
            if dd > 0.5:
                g = dz / dd
                if g > gm:
                    gm, gat = g, (p[0] + prev[0]) / 2.0
        prev = p
    rep_grade = _num(d.get("grade"))
    if rep_grade > 0 and gm > 0 and abs(gm - rep_grade) <= max(0.005, rep_grade * 0.02):
        grade_at = round(gat)

    worst_m = _num(d.get("worst_m"))
    worst_rms = _num(d.get("worst_rms"))
    seg0 = math.floor(worst_m / seg_len) * seg_len
    if worst_rms <= 1e-9 and segmap:                   # 兜底：取 RMS 最大的段
        k = max(segmap, key=lambda kk: segmap[kk])
        seg0 = k * seg_len
        worst_rms = segmap[k]
    dist_m = _num(d.get("dist_m"))
    seg1 = seg0 + seg_len
    if dist_m > seg0:
        seg1 = min(seg1, dist_m)

    d["map3d"] = out
    d["map3d_rough"] = rough

    d["map3d_n"] = len(out)
    d["map3d_z0"] = round(cz, 3)
    d["map3d_zscale"] = round(zscale, 1)
    d["map3d_z_max_at"] = round(zmax_pt[0])
    d["map3d_z_min_at"] = round(zmin_pt[0])
    d["map3d_grade_at"] = grade_at
    d["map3d_worst"] = {
        "d0": round(seg0, 1),
        "d1": round(seg1, 1),
        "rms": round(worst_rms, 3),
    }
    return d


# ══════════════════════════════════════════════════════════════════════
# 页头
# ══════════════════════════════════════════════════════════════════════
def _head(d):
    file_name = str(d.get("file") or "—")
    stem = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
    level = " ".join(str(d.get("level") or "—").replace("_", " ").split()) or "—"
    points = int(_num(d.get("points")) or _num(d.get("map3d_n")))
    chips = (chip("pin", level)
             + chip("route", fmt_dist(_num(d.get("dist_m"))))
             + chip("pulse", "%s 点" % _fmt_int(points)))
    return head_html(stem, file_name, TITLE, BADGE, SUB, chips)


# ══════════════════════════════════════════════════════════════════════
# 左栏：3D 画布卡
# ══════════════════════════════════════════════════════════════════════
def _map_card(d):
    pts = d.get("map3d") or []
    z0 = _num(d.get("map3d_z0"))
    zscale = _num(d.get("map3d_zscale"), 1.0) or 1.0
    zscale_txt = ("%.1f" % zscale).rstrip("0").rstrip(".")
    zs = [p[2] + z0 for p in pts if len(p) > 2] or [0.0]
    zlo, zhi = min(zs), max(zs)
    step = _curtain_step(len(pts))

    tag = "高程 ×%s · 地面网格 = 世界 x/y 平面" % zscale_txt
    btns = "".join(
        '<button type="button" class="m3d-btn%s" data-metric="%s">%s</button>'
        % (" active" if i == 0 else "", key, name)
        for i, (key, name) in enumerate(_METRICS)
    )
    return f"""
      <article class="card chart-card m3d-card">
        <div class="chart-head m3d-head">
          <div>
            <h2>路线 3D</h2>
            <p>整条路按 x/y/z 立起来 · 左键拖拽旋转 · 滚轮缩放 · 右键/Shift 拖拽平移 · 双击复位</p>
          </div>
          <div class="m3d-switch" id="m3d-switch" role="group" aria-label="轨迹上色指标">{btns}</div>
        </div>
        <div class="m3d-legend">
          <div class="m3d-scale">
            <span class="m3d-scale-name" id="m3d-mname">高程 (m)</span>
            <span class="m3d-scale-val lo" id="m3d-lo">{zlo:.1f} m</span>
            <span class="m3d-ramp" id="m3d-ramp" style="background:{_ELEV_GRADIENT}"></span>
            <span class="m3d-scale-val hi" id="m3d-hi">{zhi:.1f} m</span>
          </div>
          <div class="m3d-tools">
            <span class="m3d-hint">{IC["info"]}<span>悬停最近点看里程和数值</span></span>
            <button class="m3d-reset" id="m3d-reset" type="button" title="双击画布也能复位">复位视角</button>
          </div>
        </div>
        <div class="m3d-stage" id="m3d-stage">
          <canvas id="m3d-base"></canvas>
          <canvas id="m3d-over"></canvas>
          <div class="m3d-tip" id="m3d-tip"></div>
          <span class="m3d-tag">{tag}</span>
        </div>
        <div class="m3d-foot">
          <span class="m3d-foot-l" id="m3d-foot-l"><i class="m3d-dot start"></i>起点<i class="m3d-dot end"></i>终点 · 帘幕线每 {step} 个采样点垂到地面</span>
          <span class="m3d-foot-r" id="m3d-foot-r">轨迹按「高程」上色 · 共 {_fmt_int(len(pts))} 个采样点</span>
        </div>
      </article>"""


# ══════════════════════════════════════════════════════════════════════
# 右栏：概览 / 操作 / 口径
# ══════════════════════════════════════════════════════════════════════
def _overview_card(d):
    zmin = _num(d.get("z_min"))
    zmax = _num(d.get("z_max"))
    climb = _num(d.get("climb"))
    grade = _num(d.get("grade"))
    dist_m = _num(d.get("dist_m"))
    grade_pct = grade * 100.0
    zmax_at = d.get("map3d_z_max_at")
    zmin_at = d.get("map3d_z_min_at")
    grade_at = d.get("map3d_grade_at")
    worst = d.get("map3d_worst") or {}
    w0 = _num(worst.get("d0"))
    w1 = _num(worst.get("d1"), w0 + _SEG_LEN)
    wrms = _num(worst.get("rms"))

    hi_at = (" · %s m 处" % _fmt_int(zmax_at)) if zmax_at is not None else ""
    lo_at = (" · %s m 处" % _fmt_int(zmin_at)) if zmin_at is not None else ""
    wtxt = "%s–%s" % (_fmt_int(w0), _fmt_int(w1))
    wcls = " sm" if len(wtxt) > 8 else ""
    if grade_at is not None:
        foot = ("最陡处 @ %s m（坡度 %.1f%%） · 全程 %s · %s"
                % (_fmt_int(grade_at), grade_pct, fmt_dist(dist_m),
                   fmt_dur(_num(d.get("dur_s")))))
    else:
        foot = ("最大坡度 %.1f%% · 全程 %s · %s"
                % (grade_pct, fmt_dist(dist_m), fmt_dur(_num(d.get("dur_s")))))
    return f"""
      <article class="card">
        <div class="panel-head">
          <div><h2>路线概览</h2><p>最高 / 最低 / 爬升 / 最颠段</p></div>
          <span class="mini-chip">x / y / z</span>
        </div>
        <div class="m3d-ov">
          <div class="m3d-cell"><b>{zmax:.1f}<small>m</small></b><span>最高点{hi_at}</span></div>
          <div class="m3d-cell"><b>{zmin:.1f}<small>m</small></b><span>最低点{lo_at}</span></div>
          <div class="m3d-cell"><b>{climb:.1f}<small>m</small></b><span>累计爬升 · 坡度 {grade_pct:.1f}%</span></div>
          <div class="m3d-cell warm"><b class="m3d-range{wcls}">{wtxt}<small>m</small></b><span>最颠段 · RMS {wrms:.2f} m/s</span></div>
        </div>
        <div class="m3d-ov-foot">{foot}</div>
      </article>"""


def _ops_card():
    ops = (
        ("左键拖拽", "旋转视角（左右转 + 上下俯仰）"),
        ("滚轮", "以光标为中心缩放"),
        ("双击", "复位到默认视角"),
        ("右键 / Shift+拖拽", "平移画面"),
    )
    rows = "".join(
        '<div class="m3d-op"><span class="m3d-key">%s</span><span>%s</span></div>'
        % (esc(k), esc(v)) for k, v in ops
    )
    return f"""
      <article class="card">
        <div class="panel-head">
          <div><h2>怎么看</h2><p>画布上的鼠标操作</p></div>
          <span class="mini-chip">拖拽</span>
        </div>
        <div class="m3d-ops">{rows}</div>
        <div class="m3d-hint">{IC["info"]}<span>悬停任意位置，会吸附到最近的采样点。</span></div>
      </article>"""


def _note_card(d):
    zscale = _num(d.get("map3d_zscale"), 1.0) or 1.0
    zscale_txt = ("%.1f" % zscale).rstrip("0").rstrip(".")
    points = int(_num(d.get("points")) or _num(d.get("map3d_n")))
    step = _curtain_step(len(d.get("map3d") or []))
    tnote = "地形底图未采样（地图功能已停用），这里画的是路线本身的 x/y/z。"
    foot = ("全程 %s · %s · %s 点 @ 10 Hz"
            % (fmt_dist(_num(d.get("dist_m"))), fmt_dur(_num(d.get("dur_s"))),
               _fmt_int(points)))
    return f"""
      <article class="card m3d-note">
        <div class="panel-head">
          <div><h2>口径说明</h2><p>画的是什么、不是什么</p></div>
        </div>
        <div class="m3d-warn">{IC["info"]}
          <span>{tnote}</span></div>
        <ul class="m3d-ul">
          <li>高程按 <b>×{zscale_txt}</b> 放大显示（落差 ≈ 水平跨度的 18%），否则几米的起伏放在几百米的路线里几乎看不出来。</li>
          <li>帘幕线每隔 <b>{step}</b> 个采样点从轨迹垂到地面，只用来判断高度差，不是轨道支架。</li>
          <li>「颠簸」= 该点所在 500 m 段的减振器速度 RMS；「踏板」颜色 = 绿油门 / 红刹车 / 中间滑行，悬停显示当点油门、刹车开度。</li>
        </ul>
        <div class="m3d-note-foot">{foot}</div>
      </article>"""


# ══════════════════════════════════════════════════════════════════════
# 页面
# ══════════════════════════════════════════════════════════════════════
def render(d):
    """返回完整的一页：<section class="page" data-page="map3d"> ... </section>。"""
    pts = d.get("map3d") or []
    head = _head(d)
    if len(pts) < 2:
        body = ('<article class="card chart-card m3d-empty">%s</article>'
                % empty_state("map3d", "这份数据没有可用的路线坐标",
                              "CSV 里缺少 x / y / z 列，或有效采样点太少 —— "
                              "换一份带位置数据的抓包再来看 3D 赛道。"))
        return ('<section class="page" data-page="%s" data-title="%s">\n%s'
                '<section class="page-body">%s</section>\n</section>'
                % (KEY, esc(TITLE), head, body))
    body = ('<section class="page-body"><section class="grid">%s'
            '<aside class="side">%s%s%s</aside>'
            '</section></section>'
            % (_map_card(d), _overview_card(d), _ops_card(), _note_card(d)))
    return ('<section class="page" data-page="%s" data-title="%s">\n%s%s\n</section>'
            % (KEY, esc(TITLE), head, body))


# ══════════════════════════════════════════════════════════════════════
# CSS（只用本页前缀，避免和别的页撞样式）
# ══════════════════════════════════════════════════════════════════════
CSS = """/* ═══ 3D 赛道页（p_map3d）═══════════════════════════════════════ */
.page[data-page="map3d"] .m3d-card{flex:1;min-height:0;padding:17px 21px 13px}
.page[data-page="map3d"] .m3d-head{align-items:center;margin-bottom:6px}
.page[data-page="map3d"] .m3d-switch{display:inline-flex;gap:3px;padding:3px;border-radius:11px;
  background:rgba(91,143,185,.075);border:1px solid rgba(91,143,185,.1);flex:0 0 auto}
.page[data-page="map3d"] .m3d-btn{border:0;background:transparent;padding:6px 13px;border-radius:8px;
  font:inherit;font-size:11.8px;color:var(--ink-2);cursor:pointer;letter-spacing:.02em;
  transition:background .25s,color .25s,box-shadow .25s}
.page[data-page="map3d"] .m3d-btn:hover{color:var(--blue-3);background:rgba(255,255,255,.62)}
.page[data-page="map3d"] .m3d-btn.active{background:#fff;color:var(--blue-3);font-weight:600;
  box-shadow:0 7px 16px -10px rgba(50,80,110,.75),inset 0 0 0 1px rgba(91,143,185,.14)}

/* 图例 + 复位 */
.page[data-page="map3d"] .m3d-legend{display:flex;align-items:center;justify-content:space-between;
  gap:16px;margin:2px 0 8px}
.page[data-page="map3d"] .m3d-scale{display:flex;align-items:center;gap:10px;min-width:0}
.page[data-page="map3d"] .m3d-scale-name{font-size:11.8px;font-weight:600;color:var(--ink-2);
  letter-spacing:.02em;white-space:nowrap}
.page[data-page="map3d"] .m3d-scale-val{font-size:10.8px;color:var(--muted);white-space:nowrap;
  font-variant-numeric:tabular-nums;min-width:54px}
.page[data-page="map3d"] .m3d-scale-val.lo{text-align:right}
.page[data-page="map3d"] .m3d-ramp{width:196px;height:9px;border-radius:999px;flex:0 0 auto;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.5),0 5px 12px -7px rgba(91,143,185,.9)}
.page[data-page="map3d"] .m3d-tools{display:flex;align-items:center;gap:14px;flex:0 0 auto}
.page[data-page="map3d"] .m3d-hint{display:inline-flex;align-items:center;gap:6px;font-size:11.3px;
  color:var(--muted);white-space:nowrap}
.page[data-page="map3d"] .m3d-hint .ic{flex:0 0 13px;width:13px;height:13px;color:var(--blue);opacity:.8}
.page[data-page="map3d"] .m3d-reset{height:28px;padding:0 13px;border-radius:9px;
  border:1px solid rgba(91,143,185,.24);background:rgba(255,255,255,.74);color:var(--blue-3);
  font-family:inherit;font-size:11.5px;font-weight:600;letter-spacing:.02em;cursor:pointer;
  box-shadow:0 7px 16px -12px rgba(50,80,110,.85);
  transition:background .25s,transform .25s var(--ease),box-shadow .25s}
.page[data-page="map3d"] .m3d-reset:hover{background:#fff;transform:translateY(-1px);
  box-shadow:0 10px 20px -12px rgba(50,80,110,.9)}
.page[data-page="map3d"] .m3d-reset:active{transform:translateY(0)}

/* 画布舞台 */
.page[data-page="map3d"] .m3d-stage{position:relative;flex:1;min-height:0;border-radius:14px;
  overflow:hidden;cursor:grab;touch-action:none;user-select:none;
  background:radial-gradient(120% 116% at 50% 14%,rgba(255,255,255,.84),
    rgba(233,241,249,.44) 55%,rgba(214,230,243,.52) 100%);
  border:1px solid rgba(255,255,255,.9);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.95),
    inset 0 -20px 36px -32px rgba(50,80,110,.6),0 14px 30px -26px rgba(50,80,110,.5)}
.page[data-page="map3d"] .m3d-stage.dragging{cursor:grabbing}
.page[data-page="map3d"] .m3d-stage canvas{position:absolute;inset:0;display:block;
  width:100%;height:100%}
.page[data-page="map3d"] #m3d-over{pointer-events:none}
.page[data-page="map3d"] .m3d-tag{position:absolute;left:12px;top:11px;z-index:2;pointer-events:none;
  padding:4px 9px;border-radius:8px;font-size:10.6px;color:var(--blue-3);letter-spacing:.02em;
  background:rgba(255,255,255,.74);border:1px solid rgba(255,255,255,.92);
  box-shadow:0 6px 14px -12px rgba(50,80,110,.8);
  -webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px)}
.page[data-page="map3d"] .m3d-tip{position:absolute;left:0;top:0;z-index:4;display:none;
  pointer-events:none;min-width:142px;padding:8px 11px 7px;border-radius:10px;
  background:rgba(31,46,60,.93);color:#fff;font-size:11.4px;line-height:1.62;
  letter-spacing:.01em;white-space:nowrap;
  box-shadow:0 16px 36px -14px rgba(20,40,60,.75);
  -webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px)}
.page[data-page="map3d"] .m3d-tip.show{display:block}
.page[data-page="map3d"] .m3d-tip .t-d{color:#9fc0da;margin-bottom:3px;
  font-variant-numeric:tabular-nums}
.page[data-page="map3d"] .m3d-tip .t-row{display:flex;align-items:baseline;
  justify-content:space-between;gap:18px;font-variant-numeric:tabular-nums}
.page[data-page="map3d"] .m3d-tip .t-row>span{color:#9fc0da}
.page[data-page="map3d"] .m3d-tip b{font-weight:600}
.page[data-page="map3d"] .m3d-tip b.t-v{display:inline-flex;align-items:center;gap:5px}
.page[data-page="map3d"] .m3d-tip b.t-v i{width:7px;height:7px;border-radius:50%;
  display:inline-block}

/* 底部说明 */
.page[data-page="map3d"] .m3d-foot{display:flex;align-items:center;justify-content:space-between;
  gap:16px;padding-top:9px;font-size:11.3px;color:var(--muted);letter-spacing:.01em}
.page[data-page="map3d"] .m3d-foot b{color:var(--ink-2);font-weight:600;
  font-variant-numeric:tabular-nums}
.page[data-page="map3d"] .m3d-foot-l{display:inline-flex;align-items:center;gap:7px;
  white-space:nowrap}
.page[data-page="map3d"] .m3d-dot{width:8px;height:8px;border-radius:50%;display:inline-block;
  box-shadow:0 0 0 2px rgba(255,255,255,.9)}
.page[data-page="map3d"] .m3d-dot.start{background:#3E9E7B}
.page[data-page="map3d"] .m3d-dot.end{background:#D06A5C;margin-left:6px}
.page[data-page="map3d"] .m3d-foot-r{text-align:right}

/* 右栏：概览 */
.page[data-page="map3d"] .side .card{display:flex;flex-direction:column}
.page[data-page="map3d"] .side .card:last-child{flex:1 0 auto}
.page[data-page="map3d"] .m3d-ov{display:grid;grid-template-columns:1fr 1fr;gap:9px;
  margin:12px 0 0}
.page[data-page="map3d"] .m3d-cell{padding:9px 12px 8px;border-radius:12px;
  background:rgba(255,255,255,.55);border:1px solid rgba(255,255,255,.8);
  box-shadow:0 8px 18px -18px rgba(50,80,110,.6)}
.page[data-page="map3d"] .m3d-cell b{display:block;font-size:21px;font-weight:700;line-height:1.15;
  color:var(--ink);font-variant-numeric:tabular-nums;letter-spacing:-.01em;white-space:nowrap;
  font-family:"Segoe UI","Microsoft YaHei UI",sans-serif}
.page[data-page="map3d"] .m3d-cell b small{font-size:10.5px;font-weight:500;color:var(--muted);
  margin-left:2px;letter-spacing:0;font-family:"Microsoft YaHei UI","Segoe UI",sans-serif}
.page[data-page="map3d"] .m3d-cell b.m3d-range.sm{font-size:16.5px;letter-spacing:-.02em}
.page[data-page="map3d"] .m3d-cell span{display:block;margin-top:2px;font-size:10.6px;
  color:var(--muted);line-height:1.45;letter-spacing:.01em}
.page[data-page="map3d"] .m3d-cell.warm b{color:#B8503F}
.page[data-page="map3d"] .m3d-ov-foot{margin-top:11px;padding-top:10px;
  border-top:1px dashed var(--line);font-size:10.9px;color:var(--muted);
  font-variant-numeric:tabular-nums;line-height:1.6}

/* 右栏：操作说明 */
.page[data-page="map3d"] .m3d-ops{margin-top:10px;display:flex;flex-direction:column;gap:7px}
.page[data-page="map3d"] .m3d-op{display:flex;align-items:center;gap:10px;font-size:11.5px;
  color:var(--ink-2);line-height:1.45}
.page[data-page="map3d"] .m3d-key{flex:0 0 104px;text-align:center;padding:4px 4px 4.5px;
  border-radius:8px;font-size:10.6px;font-weight:600;color:var(--blue-3);
  background:rgba(255,255,255,.74);border:1px solid rgba(91,143,185,.16);
  box-shadow:0 5px 12px -10px rgba(50,80,110,.8);white-space:nowrap}
.page[data-page="map3d"] .m3d-ops + .m3d-hint{margin-top:11px;font-size:10.9px;
  white-space:normal;line-height:1.55}

/* 右栏：口径说明 */
.page[data-page="map3d"] .m3d-warn{display:flex;align-items:flex-start;gap:8px;margin:11px 0 0;
  padding:9px 11px;border-radius:11px;font-size:11.2px;line-height:1.58;color:var(--ink-2);
  background:linear-gradient(90deg,rgba(217,162,74,.16),rgba(217,162,74,.05));
  border:1px solid rgba(217,162,74,.22)}
.page[data-page="map3d"] .m3d-warn .ic{flex:0 0 14px;width:14px;height:14px;margin-top:2px;
  color:#C08A34}
.page[data-page="map3d"] .m3d-ul{list-style:none;margin:10px 0 0;padding:0;
  display:flex;flex-direction:column;gap:6px}
.page[data-page="map3d"] .m3d-ul li{position:relative;padding-left:12px;font-size:11.1px;
  line-height:1.58;color:var(--muted)}
.page[data-page="map3d"] .m3d-ul li::before{content:"";position:absolute;left:0;top:7px;
  width:4px;height:4px;border-radius:50%;background:var(--blue-2)}
.page[data-page="map3d"] .m3d-ul b{color:var(--ink-2);font-weight:600;
  font-variant-numeric:tabular-nums}
.page[data-page="map3d"] .m3d-note-foot{margin-top:auto;padding-top:11px;
  border-top:1px dashed var(--line);font-size:10.9px;color:var(--muted);
  letter-spacing:.02em;font-variant-numeric:tabular-nums}

/* 空状态 */
.page[data-page="map3d"] .m3d-empty .empty{min-height:0;padding:16px 10px}
.page[data-page="map3d"] .m3d-empty{min-height:360px}

/* 窄窗口：图表卡给个确定高度，长说明收起来，别互相压字 */
@media (max-width:1240px){
  .page[data-page="map3d"] .m3d-legend{flex-wrap:wrap;gap:6px 16px}
  .page[data-page="map3d"] .m3d-tools .m3d-hint{display:none}
  .page[data-page="map3d"] .m3d-card{min-height:440px}
  .page[data-page="map3d"] .m3d-foot-r{display:none}
  .page[data-page="map3d"] .m3d-ul li:nth-child(3){display:none}
  .page[data-page="map3d"] .m3d-ov-foot,
  .page[data-page="map3d"] .m3d-note-foot{display:none}
}
"""


# ══════════════════════════════════════════════════════════════════════
# JS：2D canvas 手写 3D 投影（yaw 绕 z 轴 → pitch 俯仰 → 屏幕投影）
# ══════════════════════════════════════════════════════════════════════
JS = r"""// 3D 赛道页脚本：第一次切到这一页时调用一次
// 注：真实地图 / 地形 / 导入截图校准 这些底图代码按用户要求停用了（build 里不再输出
//     map3d_map / map3d_terrain，页面自动走原来的「地面网格」路径），代码保留便于以后再开。
window.PAGE_INIT = window.PAGE_INIT || {};
window.PAGE_INIT.map3d = function (root, DATA) {
  var stage = root.querySelector('#m3d-stage');
  var base = root.querySelector('#m3d-base');
  var over = root.querySelector('#m3d-over');
  var tip = root.querySelector('#m3d-tip');
  var pts = DATA.map3d || [];
  var TER = DATA.map3d_terrain || null;
  var TNX = TER ? (+TER.nx || 0) : 0;
  var TNY = TER ? (+TER.ny || 0) : 0;
  var TPTS = (TER && TER.pts && TNX >= 2 && TNY >= 2 && TER.pts.length >= TNX * TNY)
    ? TER.pts : null;
  var MAP = DATA.map3d_map || null;
  var HASMAP = !!(MAP && MAP.img);
  var mapImg = null, mapReady = false;
  var calib = null;                     // 导入截图校准中的状态
  if (HASMAP) {
    TPTS = null;                        // 有真实地图就不用采样地形了
    MAP.imgEl = new Image();
    MAP.ready = false;
    MAP.imgEl.onload = function () { MAP.ready = true; drawBase(); };
    MAP.imgEl.src = MAP.img;
    mapImg = MAP.imgEl;
  }

  function apiReady() { return !!(window.pywebview && window.pywebview.api); }
  function toast(m) { if (window.__toast) window.__toast(m); }
  if (!stage || !base || !over || pts.length < 2) return;

  var rough = DATA.map3d_rough || [];
  var z0 = +DATA.map3d_z0 || 0;
  var zscale = +DATA.map3d_zscale || 1;
  var bctx = base.getContext('2d');
  var octx = over.getContext('2d');

  var W = 0, H = 0, dpr = 1;
  var view = {yaw: 0.45, pitch: 0.90, zoom: 1, panx: 0, pany: 0};
  var DEF = {yaw: 0.45, pitch: 0.90, zoom: 1, panx: 0, pany: 0};
  var metric = 'elev';
  var proj = [], gproj = [];
  var rxs = [], rys = [], ups = [];
  var trx = [], tup = [], tproj = [];
  var lastSy = 0, lastCyw = 1, lastSp = 0, lastCp = 1;
  var lastCxm = 0, lastCum = 0, lastScale = 1;
  var hoverIdx = -1, drag = null;

  // 地面网格范围（相对坐标）
  var gxmin = Infinity, gxmax = -Infinity, gymin = Infinity, gymax = -Infinity;
  for (var gi = 0; gi < pts.length; gi++) {
    var gp = pts[gi];
    if (gp[0] < gxmin) gxmin = gp[0];
    if (gp[0] > gxmax) gxmax = gp[0];
    if (gp[1] < gymin) gymin = gp[1];
    if (gp[1] > gymax) gymax = gp[1];
  }
  var gxspan = Math.max(gxmax - gxmin, 1e-6);
  var gyspan = Math.max(gymax - gymin, 1e-6);
  // 地面网格 / 地面板的世界坐标范围（z = 0 平面）
  var gpad = Math.max(gxspan, gyspan) * 0.07 + 1;
  var fx0 = gxmin - gpad, fx1 = gxmax + gpad;
  var fy0 = gymin - gpad, fy1 = gymax + gpad;
  var FC = [[fx0, fy0], [fx1, fy0], [fx1, fy1], [fx0, fy1]];
  if (HASMAP) {
    fx0 = +MAP.x0; fx1 = +MAP.x1; fy0 = +MAP.y0; fy1 = +MAP.y1;
    FC = [[fx0, fy0], [fx1, fy0], [fx1, fy1], [fx0, fy1]];
  }
  // 帘幕线数量控制在 60~75 条左右（点越多间隔越大，免得糊成一片）
  var CURTAIN_STEP = Math.max(3, Math.round(pts.length / 70));

  // ── 地形底图（扩展采样的 NxN 网格；没有就画原来的地面网格板）─────────
  var TX0 = 0, TY0 = 0, TDX = 1, TDY = 1, tzmin = 0, tzmax = 1;
  if (TPTS) {
    TX0 = TPTS[0][0];
    TY0 = TPTS[0][1];
    TDX = Math.max(1e-6, (TPTS[TNX - 1][0] - TX0) / Math.max(1, TNX - 1));
    TDY = Math.max(1e-6, (TPTS[(TNY - 1) * TNX][1] - TY0) / Math.max(1, TNY - 1));
    tzmin = 1e18; tzmax = -1e18;
    for (var ti = 0; ti < TPTS.length; ti++) {
      var tz = TPTS[ti][2];
      if (tz < tzmin) tzmin = tz;
      if (tz > tzmax) tzmax = tz;
    }
  }
  function terrHAt(wx, wy) {
    if (!TPTS) return 0;
    var ii = Math.round((wx - TX0) / TDX);
    var jj = Math.round((wy - TY0) / TDY);
    if (ii < 0) ii = 0; else if (ii >= TNX) ii = TNX - 1;
    if (jj < 0) jj = 0; else if (jj >= TNY) jj = TNY - 1;
    return TPTS[jj * TNX + ii][2];
  }
  function drawMap() {
    var M = calib || (HASMAP ? MAP : null);
    if (!M) return;
    var mx0 = +M.x0, mx1 = +M.x1, my0 = +M.y0, my1 = +M.y1;
    var m1 = scr(mx0, my0, 0), m2 = scr(mx1, my0, 0);
    var m3 = scr(mx1, my1, 0), m4 = scr(mx0, my1, 0);
    bctx.beginPath();
    bctx.moveTo(m1[0], m1[1]); bctx.lineTo(m2[0], m2[1]);
    bctx.lineTo(m3[0], m3[1]); bctx.lineTo(m4[0], m4[1]); bctx.closePath();
    bctx.save();
    bctx.shadowColor = 'rgba(60,90,120,.22)';
    bctx.shadowBlur = 18;
    bctx.shadowOffsetY = 9;
    bctx.fillStyle = 'rgba(232,240,247,.92)';
    bctx.fill();
    bctx.restore();
    var MIMG = M.imgEl || null;
    if (MIMG && M.ready) {
      var P00 = scr(mx0, my1, 0), P10 = scr(mx1, my1, 0), P01 = scr(mx0, my0, 0);
      var iw = Math.max(1, +M.w), ih = Math.max(1, +M.h);
      var a = (P10[0] - P00[0]) / iw, b = (P10[1] - P00[1]) / iw;
      var c = (P01[0] - P00[0]) / ih, d2 = (P01[1] - P00[1]) / ih;
      bctx.save();
      bctx.setTransform(dpr * a, dpr * b, dpr * c, dpr * d2, dpr * P00[0], dpr * P00[1]);
      bctx.imageSmoothingEnabled = true;
      bctx.drawImage(MIMG, 0, 0);
      bctx.restore();
    }
    bctx.beginPath();
    bctx.moveTo(m1[0], m1[1]); bctx.lineTo(m2[0], m2[1]);
    bctx.lineTo(m3[0], m3[1]); bctx.lineTo(m4[0], m4[1]); bctx.closePath();
    bctx.strokeStyle = 'rgba(91,143,185,.32)';
    bctx.lineWidth = 1.2;
    bctx.stroke();
  }
  function drawTerrain() {
    if (!TPTS || tproj.length < TPTS.length) return;
    var NZ = Math.max(tzmax - tzmin, 1e-6);
    var quads = [];
    for (var j = 0; j < TNY - 1; j++) {
      for (var i2 = 0; i2 < TNX - 1; i2++) {
        var ia = j * TNX + i2;
        var py = (tproj[ia][1] + tproj[ia + 1][1] +
                  tproj[ia + TNX][1] + tproj[ia + TNX + 1][1]) / 4;
        quads.push([py, ia]);
      }
    }
    quads.sort(function (q, w) { return q[0] - w[0]; });   // 屏幕上方（远）先画
    bctx.lineWidth = 1;
    for (var qi = 0; qi < quads.length; qi++) {
      var q0 = quads[qi][1];
      var q1 = q0 + 1, q3 = q0 + TNX, q2 = q3 + 1;
      var za = TPTS[q0][2], zb = TPTS[q1][2], zc = TPTS[q2][2], zd = TPTS[q3][2];
      var t = Math.max(0, Math.min(1, ((za + zb + zc + zd) / 4 - tzmin) / NZ));
      var i2 = q0 % TNX, j = Math.floor(q0 / TNX);
      // 苔绿（低）→ 沙黄（高）
      var rr = Math.min(250, Math.round(172 + 58 * t));
      var gg = Math.min(250, Math.round(196 + 18 * t));
      var bb = Math.min(246, Math.round(160 + 14 * t));
      // 光照：坡度用 2 格跨度算（更平滑的坡向），光从西北来
      var iL = Math.max(0, i2 - 1), iR = Math.min(TNX - 1, i2 + 2);
      var jT = Math.max(0, j - 1), jB = Math.min(TNY - 1, j + 2);
      var zL = TPTS[j * TNX + iL][2], zR = TPTS[j * TNX + iR][2];
      var zT = TPTS[jT * TNX + i2][2], zB = TPTS[jB * TNX + i2][2];
      var gxx = (zR - zL) / Math.max(1e-6, (iR - iL) * TDX);
      var gyy = (zB - zT) / Math.max(1e-6, (jB - jT) * TDY);
      var shade = Math.max(0.84, Math.min(1.14, 1 - 0.42 * gxx - 0.28 * gyy));
      var col = 'rgb(' + Math.min(255, Math.round(rr * shade)) + ','
        + Math.min(255, Math.round(gg * shade)) + ','
        + Math.min(255, Math.round(bb * shade)) + ')';
      bctx.beginPath();
      bctx.moveTo(tproj[q0][0], tproj[q0][1]);
      bctx.lineTo(tproj[q1][0], tproj[q1][1]);
      bctx.lineTo(tproj[q2][0], tproj[q2][1]);
      bctx.lineTo(tproj[q3][0], tproj[q3][1]);
      bctx.closePath();
      bctx.fillStyle = col;
      bctx.strokeStyle = col;
      bctx.lineWidth = 0.6;
      bctx.fill();
      bctx.stroke();
    }
  }

  var META = {
    elev:  {name: '高程 (m)',          short: '高程',
            fmt: function (v) { return v.toFixed(1) + ' m'; }},
    speed: {name: '车速 (km/h)',       short: '车速',
            fmt: function (v) { return v.toFixed(0) + ' km/h'; }},
    rough: {name: '颠簸 RMS (m/s)',    short: '颠簸',
            fmt: function (v) { return v.toFixed(2) + ' m/s'; }},
    pedal: {name: '踏板（油门 / 刹车）', short: '踏板',
            fmt: function (v) { return (v > 0 ? '+' : '') + v.toFixed(0); }}
  };
  var RANGE = {lo: 0, hi: 1};
  var hasRough = false;
  for (var ri = 0; ri < rough.length; ri++) {
    if ((+rough[ri] || 0) > 1e-9) { hasRough = true; break; }
  }

  function fmtInt(v) {
    return String(Math.round(v)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  // ── 指标取值 + 归一化范围 ─────────────────────────────────────
  function rawVal(i) {
    var p = pts[i];
    if (metric === 'speed') return p[3];
    if (metric === 'rough') return +rough[i] || 0;
    if (metric === 'pedal') return (p[5] - p[4]) * 100;
    return p[2] + z0;                      // 高程 = 相对 z + 基准 z
  }
  function calcRange() {
    if (metric === 'pedal') { RANGE.lo = -100; RANGE.hi = 100; return; }
    if (metric === 'elev') {
      // 高程范围直接用 analyze() 的 z_min / z_max，和右栏概览卡对得上
      var oz0 = +DATA.z_min, oz1 = +DATA.z_max;
      if (isFinite(oz0) && isFinite(oz1) && oz1 - oz0 > 1e-9) {
        RANGE.lo = oz0; RANGE.hi = oz1; return;
      }
    }
    var lo = Infinity, hi = -Infinity, i, v;
    for (i = 0; i < pts.length; i++) {
      v = rawVal(i);
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    if (!isFinite(lo) || !isFinite(hi)) { lo = 0; hi = 1; }
    if (hi - lo < 1e-9) hi = lo + 1;
    RANGE.lo = lo;
    RANGE.hi = hi;
  }
  function tOf(i) {
    return Math.max(0, Math.min(1, (rawVal(i) - RANGE.lo) / (RANGE.hi - RANGE.lo)));
  }

  // ── 色阶（和旧版 ramp() 同一套颜色；踏板的蓝→灰→红单独一套）──
  var STOPS = [[0, [48, 92, 200]], [0.25, [40, 190, 210]], [0.5, [60, 190, 80]],
               [0.75, [230, 190, 40]], [1, [220, 60, 50]]];
  function mix(a, b, f) {
    return 'rgb(' + Math.round(a[0] + (b[0] - a[0]) * f) + ','
      + Math.round(a[1] + (b[1] - a[1]) * f) + ','
      + Math.round(a[2] + (b[2] - a[2]) * f) + ')';
  }
  function ramp(t) {
    t = Math.max(0, Math.min(1, t));
    for (var i = 1; i < STOPS.length; i++) {
      if (t <= STOPS[i][0]) {
        var a = STOPS[i - 1], b = STOPS[i];
        return mix(a[1], b[1], (t - a[0]) / (b[0] - a[0]));
      }
    }
    return mix(STOPS[4][1], STOPS[4][1], 0);
  }
  function pedalColor(t) {
    t = Math.max(0, Math.min(1, t));
    if (t < 0.5) return mix([30, 190, 99], [228, 236, 243], t / 0.5);    // 亮绿 = 油门
    return mix([228, 236, 243], [208, 106, 92], (t - 0.5) / 0.5);        // 红 = 刹车
  }
  function colorAt(t) { return metric === 'pedal' ? pedalColor(t) : ramp(t); }
  function gradientCss() {
    if (metric === 'pedal') return 'linear-gradient(90deg,#1EBE63,#E4ECF3,#D06A5C)';
    var parts = [];
    for (var i = 0; i < STOPS.length; i++) {
      parts.push(ramp(STOPS[i][0]) + ' ' + (STOPS[i][0] * 100).toFixed(0) + '%');
    }
    return 'linear-gradient(90deg,' + parts.join(',') + ')';
  }

  // ── 图例 / 状态栏 ────────────────────────────────────────────
  var rampEl = root.querySelector('#m3d-ramp');
  var loEl = root.querySelector('#m3d-lo');
  var hiEl = root.querySelector('#m3d-hi');
  var nameEl = root.querySelector('#m3d-mname');
  var footEl = root.querySelector('#m3d-foot-r');
  var footL = root.querySelector('#m3d-foot-l');
  function updateLegend() {
    calcRange();
    var m = META[metric];
    if (nameEl) nameEl.textContent = m.name;
    if (loEl) loEl.textContent = metric === 'pedal' ? '全油门' : m.fmt(RANGE.lo);
    if (hiEl) hiEl.textContent = metric === 'pedal' ? '全刹车' : m.fmt(RANGE.hi);
    if (rampEl) rampEl.style.background = gradientCss();
    if (footL) {
      footL.innerHTML = '<i class="m3d-dot start"></i>起点<i class="m3d-dot end"></i>终点 · 帘幕线每 '
        + CURTAIN_STEP + ' 个采样点垂到地面';
    }
    if (footEl) {
      var txt = '轨迹按「' + m.short + '」上色 · 共 ' + fmtInt(pts.length) + ' 个采样点';
      if (HASMAP) txt += ' · 底图 = 游戏真实地图';
      else if (TPTS) txt += ' · 底图 = 地形网格 ' + TNX + '×' + TNY;
      if (metric === 'pedal' && !DATA.has_pedal) txt = '这份数据没有踏板记录 · 轨道按中性色画';
      else if (metric === 'rough' && !hasRough) txt = '这份数据没有分段 RMS · 轨道按中性色画';
      footEl.textContent = txt;
    }
  }

  // ── 投影：yaw 绕 z 轴 → pitch 俯仰 → 屏幕 ───────────────────
  function computeProjection() {
    if (calib) {
      fx0 = +calib.x0; fx1 = +calib.x1; fy0 = +calib.y0; fy1 = +calib.y1;
      FC = [[fx0, fy0], [fx1, fy0], [fx1, fy1], [fx0, fy1]];
    }
    var n = pts.length;
    var sy = Math.sin(view.yaw), cyw = Math.cos(view.yaw);
    var sp = Math.sin(view.pitch), cp = Math.cos(view.pitch);
    var i, minx = 1e18, maxx = -1e18, minu = 1e18, maxu = -1e18;
    for (i = 0; i < n; i++) {
      var p = pts[i];
      var x = p[0], y = p[1], z = p[2] * zscale;
      var rx = x * cyw - y * sy;
      var ry = x * sy + y * cyw;
      var up = ry * cp + z * sp;
      rxs[i] = rx; rys[i] = ry; ups[i] = up;
      if (rx < minx) minx = rx;
      if (rx > maxx) maxx = rx;
      if (up < minu) minu = up;
      if (up > maxu) maxu = up;
    }
    // 地形网格一起投影，并参与取景（否则底图会被裁掉一半）
    if (TPTS) {
      trx = new Array(TPTS.length);
      tup = new Array(TPTS.length);
      for (i = 0; i < TPTS.length; i++) {
        var qp = TPTS[i];
        var qrx = qp[0] * cyw - qp[1] * sy;
        var qry = qp[0] * sy + qp[1] * cyw;
        var qup = qry * cp + qp[2] * zscale * sp;
        trx[i] = qrx;
        tup[i] = qup;
        if (qrx < minx) minx = qrx;
        if (qrx > maxx) maxx = qrx;
        if (qup < minu) minu = qup;
        if (qup > maxu) maxu = qup;
      }
    }
    // 地面网格四角一起参与取景，地面板不会被裁掉一半
    for (i = 0; i < 4; i++) {
      var cwx = FC[i][0], cwy = FC[i][1];
      var crx = cwx * cyw - cwy * sy;
      var cry = cwx * sy + cwy * cyw;
      var cup = cry * cp;
      if (crx < minx) minx = crx;
      if (crx > maxx) maxx = crx;
      if (cup < minu) minu = cup;
      if (cup > maxu) maxu = cup;
    }
    var cxm = (minx + maxx) / 2, cum = (minu + maxu) / 2;
    var spanx = Math.max(maxx - minx, 1e-6);
    var spanu = Math.max(maxu - minu, 1e-6);
    lastScale = Math.min(W * 0.90 / spanx, H * 0.90 / spanu) * view.zoom;
    lastCxm = cxm; lastCum = cum;
    lastSy = sy; lastCyw = cyw; lastSp = sp; lastCp = cp;
    proj = new Array(n); gproj = new Array(n);
    for (i = 0; i < n; i++) {
      var sx = W / 2 + (rxs[i] - cxm) * lastScale + view.panx;
      proj[i] = [sx, H / 2 - (ups[i] - cum) * lastScale + view.pany];
      var gup = rys[i] * cp;
      if (TPTS) gup += terrHAt(pts[i][0], pts[i][1]) * zscale * sp;
      gproj[i] = [sx, H / 2 - (gup - cum) * lastScale + view.pany];
    }
    if (TPTS) {
      tproj = new Array(TPTS.length);
      for (i = 0; i < TPTS.length; i++) {
        tproj[i] = [W / 2 + (trx[i] - cxm) * lastScale + view.panx,
                    H / 2 - (tup[i] - cum) * lastScale + view.pany];
      }
    }
  }
  function scr(wx, wy, wz) {
    var z = wz * zscale;
    var rx = wx * lastCyw - wy * lastSy;
    var ry = wx * lastSy + wy * lastCyw;
    var up = ry * lastCp + z * lastSp;
    return [W / 2 + (rx - lastCxm) * lastScale + view.panx,
            H / 2 - (up - lastCum) * lastScale + view.pany];
  }

  // ── 画底图（网格 / 帘幕 / 轨迹 / 起终点）────────────────────
  function drawBase() {
    bctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    bctx.clearRect(0, 0, W, H);
    computeProjection();
    var n = pts.length, i;
    var x0 = fx0, x1 = fx1, y0 = fy0, y1 = fy1;
    var N = 8, k, a, b;

    if (calib || HASMAP) {
      drawMap();
    } else if (TPTS) {
      drawTerrain();
    } else {
    // 地面板（z=0 平面，跟着一起投影）
    var c1 = scr(x0, y0, 0), c2 = scr(x1, y0, 0);
    var c3 = scr(x1, y1, 0), c4 = scr(x0, y1, 0);
    bctx.beginPath();
    bctx.moveTo(c1[0], c1[1]); bctx.lineTo(c2[0], c2[1]);
    bctx.lineTo(c3[0], c3[1]); bctx.lineTo(c4[0], c4[1]);
    bctx.closePath();
    bctx.save();
    bctx.shadowColor = 'rgba(50,80,110,.20)';
    bctx.shadowBlur = 16;
    bctx.shadowOffsetY = 8;
    bctx.fillStyle = 'rgba(232,241,249,.72)';
    bctx.fill();
    bctx.restore();
    bctx.strokeStyle = 'rgba(91,143,185,.26)';
    bctx.lineWidth = 1.2;
    bctx.stroke();

    // 棋盘格淡染：一眼看出地面往哪边斜
    bctx.fillStyle = 'rgba(91,143,185,.045)';
    for (var cj = 0; cj < N; cj++) {
      for (var ck = 0; ck < N; ck++) {
        if ((cj + ck) % 2) continue;
        var qx0 = x0 + (x1 - x0) * ck / N, qx1 = x0 + (x1 - x0) * (ck + 1) / N;
        var qy0 = y0 + (y1 - y0) * cj / N, qy1 = y0 + (y1 - y0) * (cj + 1) / N;
        var qa = scr(qx0, qy0, 0), qb = scr(qx1, qy0, 0);
        var qc = scr(qx1, qy1, 0), qd = scr(qx0, qy1, 0);
        bctx.beginPath();
        bctx.moveTo(qa[0], qa[1]); bctx.lineTo(qb[0], qb[1]);
        bctx.lineTo(qc[0], qc[1]); bctx.lineTo(qd[0], qd[1]);
        bctx.closePath();
        bctx.fill();
      }
    }

    // 网格线
    bctx.beginPath();
    for (k = 0; k <= N; k++) {
      var gx = x0 + (x1 - x0) * k / N;
      a = scr(gx, y0, 0); b = scr(gx, y1, 0);
      bctx.moveTo(a[0], a[1]); bctx.lineTo(b[0], b[1]);
      var gy = y0 + (y1 - y0) * k / N;
      a = scr(x0, gy, 0); b = scr(x1, gy, 0);
      bctx.moveTo(a[0], a[1]); bctx.lineTo(b[0], b[1]);
    }
    bctx.strokeStyle = 'rgba(91,143,185,.16)';
    bctx.lineWidth = 1;
    bctx.stroke();
    // 主网格线（每 4 条深一点，读得出距离）
    bctx.beginPath();
    for (k = 0; k <= N; k += 4) {
      var gx2 = x0 + (x1 - x0) * k / N;
      a = scr(gx2, y0, 0); b = scr(gx2, y1, 0);
      bctx.moveTo(a[0], a[1]); bctx.lineTo(b[0], b[1]);
      var gy2 = y0 + (y1 - y0) * k / N;
      a = scr(x0, gy2, 0); b = scr(x1, gy2, 0);
      bctx.moveTo(a[0], a[1]); bctx.lineTo(b[0], b[1]);
    }
    bctx.strokeStyle = 'rgba(91,143,185,.30)';
    bctx.stroke();
    }

    // 地面投影（路线在地面上的影子，帮助判断偏离）
    bctx.beginPath();
    for (i = 0; i < n; i++) {
      if (i === 0) bctx.moveTo(gproj[i][0], gproj[i][1]);
      else bctx.lineTo(gproj[i][0], gproj[i][1]);
    }
    bctx.strokeStyle = 'rgba(91,143,185,.27)';
    bctx.lineWidth = 1.4;
    bctx.stroke();

    // 垂直帘幕：每 CURTAIN_STEP 个采样点从轨迹垂到地面
    var STEP = CURTAIN_STEP;
    bctx.beginPath();
    for (i = 0; i < n; i += STEP) {
      bctx.moveTo(proj[i][0], proj[i][1]);
      bctx.lineTo(gproj[i][0], gproj[i][1]);
    }
    bctx.strokeStyle = 'rgba(91,143,185,.34)';
    bctx.lineWidth = 1;
    bctx.stroke();

    // 轨迹软阴影衬底（让彩色线从网格里跳出来）
    bctx.beginPath();
    for (i = 0; i < n; i++) {
      if (i === 0) bctx.moveTo(proj[i][0], proj[i][1]);
      else bctx.lineTo(proj[i][0], proj[i][1]);
    }
    bctx.strokeStyle = 'rgba(62,107,146,.16)';
    bctx.lineWidth = 5.5;
    bctx.lineJoin = 'round';
    bctx.lineCap = 'round';
    bctx.stroke();

    // 轨迹分段上色：远的先画（画家算法，和旧版一致）
    var order = [];
    for (i = 0; i < n - 1; i++) order.push(i);
    order.sort(function (q, w) {
      return (rys[w] + rys[w + 1]) - (rys[q] + rys[q + 1]);
    });
    var span = RANGE.hi - RANGE.lo;
    bctx.lineWidth = 2.7;
    for (var oi = 0; oi < order.length; oi++) {
      i = order[oi];
      var t = span > 1e-12 ? (rawVal(i) - RANGE.lo) / span : 0.5;
      bctx.strokeStyle = colorAt(t);
      bctx.beginPath();
      bctx.moveTo(proj[i][0], proj[i][1]);
      bctx.lineTo(proj[i + 1][0], proj[i + 1][1]);
      bctx.stroke();
    }

    // 起点 / 终点
    marker(0, '起点', '#3E9E7B');
    marker(n - 1, '终点', '#D06A5C');
  }

  function marker(i, label, color) {
    var p = proj[i];
    if (!p) return;
    bctx.beginPath();
    bctx.arc(p[0], p[1], 5.6, 0, Math.PI * 2);
    bctx.fillStyle = color;
    bctx.fill();
    bctx.lineWidth = 2.2;
    bctx.strokeStyle = 'rgba(255,255,255,.95)';
    bctx.stroke();
    var ty = Math.max(15, p[1] - 10);
    bctx.font = '600 11.5px "Microsoft YaHei UI","Segoe UI",sans-serif';
    bctx.textAlign = 'center';
    bctx.textBaseline = 'bottom';
    bctx.lineWidth = 3;
    bctx.strokeStyle = 'rgba(255,255,255,.9)';
    bctx.strokeText(label, p[0], ty);
    bctx.fillStyle = color;
    bctx.fillText(label, p[0], ty);
  }

  // ── 悬停层（第二块 canvas，单独画，不重绘底图）──────────────
  function drawOverlay() {
    octx.setTransform(dpr, 0, 0, dpr, 0, 0);
    octx.clearRect(0, 0, W, H);
    if (hoverIdx < 0 || !proj[hoverIdx]) return;
    var p = proj[hoverIdx], g = gproj[hoverIdx];
    octx.save();
    octx.setLineDash([3, 3]);
    octx.strokeStyle = 'rgba(62,107,146,.7)';
    octx.lineWidth = 1;
    octx.beginPath();
    octx.moveTo(p[0], p[1]);
    octx.lineTo(g[0], g[1]);
    octx.stroke();
    octx.restore();
    octx.beginPath();
    octx.arc(p[0], p[1], 6.4, 0, Math.PI * 2);
    octx.strokeStyle = 'rgba(255,255,255,.95)';
    octx.lineWidth = 3;
    octx.stroke();
    octx.strokeStyle = colorAt(tOf(hoverIdx));
    octx.lineWidth = 2;
    octx.stroke();
    octx.beginPath();
    octx.arc(p[0], p[1], 1.8, 0, Math.PI * 2);
    octx.fillStyle = '#fff';
    octx.fill();
  }

  function positionTipAt(ptx, pty) {
    if (!tip || !tip.classList.contains('show')) return;
    var tw = tip.offsetWidth, th = tip.offsetHeight;
    var left = ptx + 18, top = pty + 16;
    if (left + tw > W - 8) left = ptx - tw - 18;
    if (top + th > H - 8) top = pty - th - 16;
    left = Math.max(8, Math.min(left, W - tw - 8));
    top = Math.max(8, Math.min(top, H - th - 8));
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }
  function showTip(i) {
    if (!tip) return;
    var p = pts[i], m = META[metric];
    var z = p[2] + z0;
    var rows = '';
    if (metric === 'pedal') {
      // 踏板：不显示「刹车 − 油门」的数字，直接说这一脚是油门 / 刹车 / 滑行
      var pv = rawVal(i);
      var st = pv > 15 ? '刹车' : (pv < -15 ? '油门' : '滑行');
      rows += '<div class="t-row"><span>踏板</span><b class="t-v">'
        + '<i style="background:' + colorAt(tOf(i)) + '"></i>' + st + '</b></div>';
    } else {
      rows += '<div class="t-row"><span>' + m.short + '</span><b class="t-v">'
        + '<i style="background:' + colorAt(tOf(i)) + '"></i>'
        + m.fmt(rawVal(i)) + '</b></div>';
    }
    if (metric !== 'elev') {
      rows += '<div class="t-row"><span>高程</span><b>' + z.toFixed(1) + ' m</b></div>';
    }
    if (metric !== 'speed') {
      rows += '<div class="t-row"><span>车速</span><b>' + p[3].toFixed(0) + ' km/h</b></div>';
    }
    rows += '<div class="t-row"><span>油门/刹车</span><b>'
      + (p[4] * 100).toFixed(0) + '% / ' + (p[5] * 100).toFixed(0) + '%</b></div>';
    tip.innerHTML = '<div class="t-d">里程 ' + fmtInt(p[6]) + ' m</div>' + rows;
    tip.classList.add('show');
    positionTipAt(proj[i][0], proj[i][1]);
  }
  function hideTip() {
    if (tip) tip.classList.remove('show');
    if (hoverIdx >= 0) {
      hoverIdx = -1;
      drawOverlay();
    }
  }

  function updateHover(mx, my) {
    var best = -1, bestD = 26 * 26, i;
    for (i = 0; i < proj.length; i++) {
      var p = proj[i];
      if (!p) continue;
      var dx = p[0] - mx, dy = p[1] - my;
      var dd = dx * dx + dy * dy;
      if (dd < bestD) { bestD = dd; best = i; }
    }
    if (best === hoverIdx) {
      if (best >= 0) positionTipAt(proj[best][0], proj[best][1]);
      return;
    }
    hoverIdx = best;
    drawOverlay();
    if (best < 0) { if (tip) tip.classList.remove('show'); return; }
    showTip(best);
  }

  // ── 尺寸 ────────────────────────────────────────────────────
  function resize() {
    var rect = stage.getBoundingClientRect();
    var w = Math.max(1, Math.round(rect.width));
    var h = Math.max(1, Math.round(rect.height));
    var nd = Math.min(2, window.devicePixelRatio || 1);
    if (w === W && h === H && nd === dpr && base.width) {
      drawBase(); drawOverlay();
      return;
    }
    W = w; H = h; dpr = nd;
    base.width = Math.round(W * dpr);
    base.height = Math.round(H * dpr);
    over.width = base.width;
    over.height = base.height;
    drawBase();
    drawOverlay();
  }

  // 屏幕坐标 → 世界坐标（z=0 平面）
  function screenToWorld(sx, sy) {
    var rx = (sx - W / 2 - view.panx) / lastScale + lastCxm;
    var up = -(sy - H / 2 - view.pany) / lastScale + lastCum;
    var ry = up / (lastCp || 1);
    return [lastCyw * rx + lastSy * ry, -lastSy * rx + lastCyw * ry];
  }
  function screenDeltaToWorld(dsx, dsy) {
    var drx = dsx / lastScale;
    var dry = -dsy / (lastScale * (lastCp || 1));
    return [lastCyw * drx + lastSy * dry, -lastSy * drx + lastCyw * dry];
  }
  function calibScaleAt(mx, my, f) {
    var wpt = screenToWorld(mx, my);
    calib.x0 = wpt[0] + (calib.x0 - wpt[0]) * f;
    calib.x1 = wpt[0] + (calib.x1 - wpt[0]) * f;
    calib.y0 = wpt[1] + (calib.y0 - wpt[1]) * f;
    calib.y1 = wpt[1] + (calib.y1 - wpt[1]) * f;
  }

  // ── 交互：左键旋转 / 右键或 Shift+左键平移 / 滚轮缩放 / 双击复位 ──
  stage.addEventListener('mousedown', function (e) {
    e.preventDefault();
    if (calib) {
      drag = {mode: 'calib', x: e.clientX, y: e.clientY};
      stage.classList.add('dragging');
      hideTip();
      return;
    }
    var pan = (e.button === 2) || (e.button === 0 && e.shiftKey);
    drag = {mode: pan ? 'pan' : 'rot', x: e.clientX, y: e.clientY};
    stage.classList.add('dragging');
    hideTip();
  });
  window.addEventListener('mousemove', function (e) {
    if (!drag) return;
    var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    drag.x = e.clientX;
    drag.y = e.clientY;
    if (drag.mode === 'calib') {
      var dv = screenDeltaToWorld(dx, dy);
      calib.x0 += dv[0]; calib.x1 += dv[0];
      calib.y0 += dv[1]; calib.y1 += dv[1];
      drawBase(); drawOverlay();
      return;
    }
    if (drag.mode === 'rot') {
      view.yaw += dx * 0.0065;
      var lim = 85 * Math.PI / 180;
      view.pitch = Math.max(-lim, Math.min(lim, view.pitch + dy * 0.0055));
    } else {
      view.panx += dx;
      view.pany += dy;
    }
    drawBase();
    drawOverlay();
  });
  window.addEventListener('mouseup', function () {
    if (!drag) return;
    drag = null;
    stage.classList.remove('dragging');
  });
  stage.addEventListener('mousemove', function (e) {
    if (drag || calib) return;
    var rect = stage.getBoundingClientRect();
    updateHover(e.clientX - rect.left, e.clientY - rect.top);
  });
  stage.addEventListener('mouseleave', function () {
    if (!drag) hideTip();
  });
  stage.addEventListener('contextmenu', function (e) { e.preventDefault(); });
  stage.addEventListener('wheel', function (e) {
    e.preventDefault();
    var rect = stage.getBoundingClientRect();
    var mx = e.clientX - rect.left, my = e.clientY - rect.top;
    if (calib) {
      calibScaleAt(mx, my, Math.exp(e.deltaY * 0.0012));
      drawBase(); drawOverlay(); hideTip();
      return;
    }
    var f = Math.exp(-e.deltaY * 0.0012);
    var z2 = Math.max(0.35, Math.min(9, view.zoom * f));
    var r = z2 / view.zoom;
    var cx = W / 2, cy = H / 2;
    view.panx = (mx - cx) - (mx - cx - view.panx) * r;
    view.pany = (my - cy) - (my - cy - view.pany) * r;
    view.zoom = z2;
    drawBase();
    drawOverlay();
    hideTip();
  }, {passive: false});

  function resetView() {
    view.yaw = DEF.yaw;
    view.pitch = DEF.pitch;
    view.zoom = DEF.zoom;
    view.panx = 0;
    view.pany = 0;
    drawBase();
    drawOverlay();
    hideTip();
  }
  stage.addEventListener('dblclick', function (e) {
    e.preventDefault();
    resetView();
  });
  var resetBtn = root.querySelector('#m3d-reset');
  if (resetBtn) resetBtn.addEventListener('click', resetView);

  // ── 导入游戏地图截图 + 校准 ─────────────────────────────────
  function startCalib(res) {
    var im = new Image();
    im.onload = function () {
      calib = {imgEl: im, ready: true, w: im.width, h: im.height,
               x0: +res.calib.x0, y0: +res.calib.y0,
               x1: +res.calib.x1, y1: +res.calib.y1,
               level: res.level, src: res.img};
      view.yaw = 0; view.pitch = 1.15; view.zoom = 1; view.panx = 0; view.pany = 0;
      var bar = root.querySelector('#m3d-calib');
      if (bar) bar.hidden = false;
      drawBase(); drawOverlay();
      hideTip();
      toast('拖拽 / 滚轮把截图对准路线，好了点「保存对齐」');
    };
    im.src = res.img;
  }
  window.__m3dStartCalib = startCalib;

  var importBtn = root.querySelector('#m3d-map-import');
  if (importBtn) importBtn.addEventListener('click', function () {
    if (!apiReady()) { toast('静态预览里没有导入功能，请用真窗口'); return; }
    toast('选择游戏地图截图…');
    window.pywebview.api.pick_mapshot().then(function (res) {
      if (!res || res.cancelled) return;
      if (!res.ok) { toast('导入失败：' + (res.error || '未知错误')); return; }
      startCalib(res);
    }).catch(function (err) { toast('导入失败：' + err); });
  });

  function exitCalib(keep) {
    if (!calib) return;
    var bar = root.querySelector('#m3d-calib');
    if (bar) bar.hidden = true;
    if (!keep) { calib = null; drawBase(); drawOverlay(); }
  }
  var calibSave = root.querySelector('#m3d-calib-save');
  if (calibSave) calibSave.addEventListener('click', function () {
    if (!calib) return;
    var lvl = calib.level || DATA.level || '';
    window.pywebview.api.save_mapshot(lvl, calib.x0, calib.y0, calib.x1, calib.y1)
      .then(function (res) {
        if (!res || !res.ok) { toast('保存失败：' + ((res && res.error) || '未知错误')); return; }
        MAP = {img: calib.src, imgEl: calib.imgEl, ready: true, w: calib.w, h: calib.h,
               x0: calib.x0, x1: calib.x1, y0: calib.y0, y1: calib.y1,
               level: calib.level, custom: true};
        HASMAP = true;
        mapImg = MAP.imgEl;
        mapReady = true;
        exitCalib(true);
        calib = null;
        drawBase(); drawOverlay();
        var warn = root.querySelector('.m3d-warn span');
        if (warn) warn.textContent = '底图 = 你导入的游戏地图截图（已校准），路线按 x/y/z 立在上面。';
        toast('已保存对齐，以后打开这张地图就用这张截图当底图');
      }).catch(function (err) { toast('保存失败：' + err); });
  });
  var calibCancel = root.querySelector('#m3d-calib-cancel');
  if (calibCancel) calibCancel.addEventListener('click', function () { exitCalib(false); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && calib) exitCalib(false);
  });

  // ── 指标切换 ────────────────────────────────────────────────
  var switchEl = root.querySelector('#m3d-switch');
  if (switchEl) {
    switchEl.addEventListener('click', function (e) {
      var btn = e.target && e.target.closest ? e.target.closest('.m3d-btn') : null;
      if (!btn) return;
      var key = btn.getAttribute('data-metric');
      if (!key || key === metric || !META[key]) return;
      metric = key;
      var all = switchEl.querySelectorAll('.m3d-btn');
      for (var i = 0; i < all.length; i++) {
        all[i].classList.toggle('active', all[i] === btn);
      }
      updateLegend();
      drawBase();
      drawOverlay();
      hideTip();
    });
  }

  // ── 启动 ────────────────────────────────────────────────────
  updateLegend();
  if (window.ResizeObserver) {
    var ro = new ResizeObserver(function () { resize(); });
    ro.observe(stage);
  }
  window.addEventListener('resize', function () { resize(); });
  resize();
};"""
