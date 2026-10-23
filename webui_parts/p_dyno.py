# -*- coding: utf-8 -*-
"""动力曲线页 —— 转速-扭矩/功率双轴曲线 + 加速度-车速曲线 + 关键统计

数据口径（全部来自 analyze()，一个数字都不写死）：
- dyno：[rpm, 扭矩 Nm, 功率 kW]，由四轮载荷反推的【轮上】功率（不是台架实测）。
  P = m·a·v 按 120 rpm 分档取 90 分位，扭矩由 P 与 rpm 反算。
- power_curve：[(车速 km/h, 加速度 g)]，只取油门 >60%、方向盘回正的直线段。
- power：7 个车速档的平均加速度 g（可能全是 None）。
- mass / acc_max / acc_min / t100 / model / meta 里取车型配置。

页面结构：页头 → 三项 dyno 峰值统计 → 左侧 dyno 双轴曲线 + 加速度曲线 + 分档柱状
→ 右侧关键指标 / 发力特性 / 数据出处。没有 dyno 数据时曲线卡片有专门空状态。
"""

KEY = "dyno"
LABEL = "动力曲线"          # 左侧导航上的文字（尽量 ≤4 字）
ICON = "pulse"            # common.IC 里的图标 key
TITLE = "动力曲线"          # 页面大标题
BADGE = "轮上反推"          # 标题旁小标签
SUB = "这一页看什么：轮上功率和扭矩随转速的变化，以及加速、刹车能有多狠。"
ORDER = 3


# ══════════════════════════════════════════════════════════════════════
# 数据
# ══════════════════════════════════════════════════════════════════════
def build(r, d):
    """analyze() 结果 r -> 往共享数据 d 里补本页字段（JSON 可序列化）。"""
    # ── 转速 / 扭矩 / 功率曲线（轮上反推）──────────────────────────────
    dy = r.get("dyno") or []
    d["dyno"] = [[int(round(float(p[0]))), round(float(p[1]), 2), round(float(p[2]), 2)]
                 for p in dy]
    d["dyno_bins"] = len(d["dyno"])
    d["has_dyno_chart"] = len(d["dyno"]) >= 2      # 少于 2 档画不成折线
    if d["dyno"]:
        pk = max(d["dyno"], key=lambda q: q[2])          # 功率峰值
        pt = max(d["dyno"], key=lambda q: q[1])          # 扭矩峰值
        d["dyno_peak_kw"], d["dyno_peak_kw_rpm"] = pk[2], pk[0]
        d["dyno_peak_nm"], d["dyno_peak_nm_rpm"] = pt[1], pt[0]
        d["dyno_rpm_lo"] = min(q[0] for q in d["dyno"])
        d["dyno_rpm_hi"] = max(q[0] for q in d["dyno"])
        # 扭矩带宽（只统计正值，避免空转/断油把下界拉低）
        tqs = [q[1] for q in d["dyno"] if q[1] > 0]
        tq_lo = min(tqs) if tqs else 0.0
        tq_hi = max(tqs) if tqs else 0.0
        d["dyno_tq_lo"], d["dyno_tq_hi"] = round(tq_lo, 1), round(tq_hi, 1)
        flat = ((tq_hi - tq_lo) / tq_hi) < 0.35 if tq_hi > 0 else True
        d["dyno_flat"] = flat
        d["dyno_shape"] = ("扭矩平台很平（%.0f – %.0f Nm），全程都有劲" % (tq_lo, tq_hi)
                           if flat else
                           "扭矩随转速起伏（%.0f – %.0f Nm），不是平顺的扭矩平台"
                           % (tq_lo, tq_hi))
        # 发力特性：和老版 _draw_dyno 的阈值一致（>6000 高转 / <3500 低转 / 其余中等）
        krpm = d["dyno_peak_kw_rpm"]
        if krpm > 6000:
            d["dyno_style"] = "高转取向"
            d["dyno_style_note"] = "要拉到 %d rpm 以上才最有劲" % krpm
        elif krpm < 3500:
            d["dyno_style"] = "低转取向"
            d["dyno_style_note"] = "%d rpm 就到峰值，之后开始乏力" % krpm
        else:
            d["dyno_style"] = "中等转速取向"
            d["dyno_style_note"] = "%d rpm 附近最有力" % krpm

    # ── 加速度 – 车速曲线 ────────────────────────────────────────────
    curve = r.get("power_curve") or []
    d["accel_curve"] = [[round(float(v), 1), round(float(a), 3)] for v, a in curve]
    d["has_accel_chart"] = len(d["accel_curve"]) >= 2   # 少于 2 个点画不成折线
    peak = None
    if d["accel_curve"]:
        pv, pa = max(d["accel_curve"], key=lambda q: q[1])
        peak = [pv, pa]
    d["accel_peak"] = peak

    bands = []
    for lo, hi, avg, n in (r.get("power") or []):
        bands.append({
            "lo": int(lo), "hi": int(hi),
            "g": (round(float(avg), 3) if avg is not None else None),
            "n": int(n),
        })
    d["accel_bands"] = bands
    gs = [b["g"] for b in bands if b["g"] is not None]
    d["accel_band_max"] = max(gs) if gs else None
    d["accel_band_n"] = len(gs)
    d["has_accel"] = d["has_accel_chart"] or bool(gs)

    # ── 关键统计 ────────────────────────────────────────────────────
    d["mass"] = round(float(r.get("mass") or 0.0), 1)
    d["model"] = (r.get("model") or "").strip()
    if not d["model"]:      # 没有 sidecar .txt 时退回到完整车型名
        d["model"] = " ".join((r.get("meta", {}).get("veh") or "").split())
    d["acc_max"] = round(float(r.get("acc_max") or 0.0), 3)
    d["acc_min"] = round(float(r.get("acc_min") or 0.0), 3)
    t100 = r.get("t100")
    d["t100"] = round(float(t100), 2) if t100 else None
    # 0-100 没测到时要能说清楚为什么（没到 100，还是没静止起步）
    d["v_start"] = round(float(r.get("v_start") or 0.0), 1)
    d["roll"] = r.get("roll") or {}
    if d["t100"]:
        d["t100_note"] = "从静止起步实测"
    elif (r.get("v_max") or 0.0) * 3.6 < 100.0:
        d["t100_note"] = "最高车速没到 100 km/h，测不到"
    elif d["roll"].get("0-100"):
        d["t100_note"] = "这段没有完整静止起步，可分档看下面的滚动加速"
    else:
        d["t100_note"] = ("这段抓包从 %.0f km/h 开始、没经过静止，"
                          "所以 0-100 测不到；看下面的滚动加速" % d["v_start"])
    return d


# ══════════════════════════════════════════════════════════════════════
# 页面片段
# ══════════════════════════════════════════════════════════════════════
def _stats_html(d):
    """顶部三张 dyno 峰值统计卡（没有 dyno 时整条不出现）。"""
    from .common import IC

    if not d.get("dyno"):
        return ""
    return """
    <section class="stats">
      <article class="card stat" style="--tone:#5B8FB9">
        <div class="stat-label">%s最大轮上功率</div>
        <div class="stat-value tone">%.0f<small>kW</small></div>
        <div class="stat-foot">@ %d rpm · 由四轮载荷反推</div>
      </article>
      <article class="card stat" style="--tone:#D9A24A">
        <div class="stat-label">%s峰值扭矩</div>
        <div class="stat-value tone">%.0f<small>Nm</small></div>
        <div class="stat-foot">@ %d rpm · 由功率与转速反算</div>
      </article>
      <article class="card stat">
        <div class="stat-label">%s有效转速区间</div>
        <div class="stat-value sm">%d – %d<small>rpm</small></div>
        <div class="stat-foot">%d 个转速档 · 每档取 90 分位</div>
      </article>
    </section>""" % (
        IC["pulse"], d["dyno_peak_kw"], d["dyno_peak_kw_rpm"],
        IC["gauge"], d["dyno_peak_nm"], d["dyno_peak_nm_rpm"],
        IC["clock"], d["dyno_rpm_lo"], d["dyno_rpm_hi"], d["dyno_bins"],
    )


def _power_card_html(d):
    from .common import IC, legend, empty_state

    if not d.get("has_dyno_chart"):
        if d.get("dyno"):
            title = "转速采样档位太少"
            text = ("只凑到 %d 个转速档，画不成曲线；跑一段更长的全油门加速再回来看。"
                    % d.get("dyno_bins", len(d.get("dyno") or [])))
            hint = "目前只有 %d 个转速档。" % len(d.get("dyno") or [])
        else:
            title = "这份数据没有算出发动机曲线"
            text = ("dyno 是从四轮载荷反推的轮上功率：需要一段转速稳定上升、油门较大的采样。"
                    "用新版抓包扩展跑一段全油门加速，再回来看这一页。")
            hint = "这份数据里没有可用的转速 / 扭矩记录，其它页面的数据不受影响。"
        return """
      <article class="card chart-card dyno-power-card">
        <div class="chart-head">
          <div>
            <h2>转速 – 功率 / 扭矩</h2>
            <p>dyno 由轮荷反推，需要转速与油门的重叠采样</p>
          </div>
        </div>
        %s
        <div class="hint">%s<span>%s</span></div>
      </article>""" % (empty_state("pulse", title, text), IC["info"], hint)

    lg = legend([
        ("功率 kW（左轴）", "#5B8FB9", False),
        ("扭矩 Nm（右轴）", "#D9A24A", False),
    ])
    return """
      <article class="card chart-card dyno-power-card">
        <div class="chart-head">
          <div>
            <h2>转速 – 功率 / 扭矩</h2>
            <p>由四轮载荷反推的轮上功率，按转速 120 rpm 分档取 90 分位 · 不是台架实测</p>
          </div>
          %s
        </div>
        <div class="chart" id="chart-dyno"></div>
      </article>""" % lg


def _accel_card_html(d):
    from .common import IC, legend, empty_state

    if not d.get("has_accel_chart"):
        if d.get("accel_curve"):
            title = "加速采样点太少"
            why = ("只凑到 %d 个车速点，画不成连续曲线。"
                   % len(d.get("accel_curve") or []))
        else:
            title = "算不出加速曲线"
            why = ("这份数据的全油门直线段太少，凑不出每 5 km/h 的平均值。"
                   if d.get("accel_band_max") is None else
                   "这份数据的加速采样不够密，画不出连续曲线。")
        return """
      <article class="card chart-card dyno-accel-card">
        <div class="chart-head">
          <div>
            <h2>加速度 – 车速</h2>
            <p>只取全油门直线段（油门 &gt;60%%）· 每 5 km/h 取均值</p>
          </div>
        </div>
        %s
        <div class="hint">%s<span>加速 G 需要连续的全油门加速段，巡航 / 制动数据算不出来。</span></div>
      </article>""" % (
            empty_state("gauge", title, why),
            IC["info"],
        )

    peak = d.get("accel_peak")
    peak_txt = ("峰值 +%.2f g @ %.0f km/h" % (peak[1], peak[0])) if peak else ""
    lg = legend([("纵向加速度 (g)", "#5B8FB9", False)])
    return """
      <article class="card chart-card dyno-accel-card">
        <div class="chart-head">
          <div>
            <h2>加速度 – 车速</h2>
            <p>全油门直线段 · 每 5 km/h 取均值%s</p>
          </div>
          %s
        </div>
        <div class="chart" id="chart-accel"></div>
      </article>""" % (((" · " + peak_txt) if peak_txt else ""), lg)


def _band_card_html(d):
    from .common import empty_state

    bands = d.get("accel_bands") or []
    bmax = d.get("accel_band_max")
    if bmax is None:
        return """
      <article class="card dyno-band-card">
        <div class="panel-head"><div><h2>分档加速度</h2><p>按车速分 7 档 · 单位 g</p></div></div>
        %s
      </article>""" % empty_state("bars", "没有分档数据", "缺少油门 >60% 的直线加速段。")

    rows = []
    for b in bands:
        label = "%d–%d" % (b["lo"], b["hi"])
        g = b["g"]
        if g is None:
            rows.append(
                '<div class="dyno-band"><span class="bl">%s</span>'
                '<span class="bt"></span><span class="bv dim">—</span></div>' % label)
            continue
        w = min(100.0, max(2.0, g / bmax * 100.0))
        peak_cls = " is-peak" if abs(g - bmax) < 1e-9 else ""
        rows.append(
            '<div class="dyno-band%s"><span class="bl">%s</span>'
            '<span class="bt"><span class="bf" style="width:%.1f%%"></span></span>'
            '<span class="bv">%+.2f</span></div>' % (peak_cls, label, w, g))
    return """
      <article class="card dyno-band-card">
        <div class="panel-head"><div><h2>分档加速度</h2><p>按车速分 7 档取均值 · 单位 g</p></div></div>
        <div class="dyno-band-list">%s</div>
      </article>""" % "".join(rows)


def _left_html(d):
    accel = _accel_card_html(d)
    if not d.get("has_accel"):
        # 加速/分档都没数据时只留一张说明卡，别摆两个空状态
        accel = accel.replace('class="card chart-card dyno-accel-card"',
                              'class="card chart-card dyno-accel-card is-solo"')
        return "%s\n      <div class=\"dyno-row\">%s</div>" % (_power_card_html(d), accel)
    return "%s\n      <div class=\"dyno-row\">%s%s</div>" % (
        _power_card_html(d), accel, _band_card_html(d))


def _side_html(d):
    from .common import IC, esc, empty_state

    has_dyno = bool(d.get("dyno"))
    if d.get("t100"):
        t100_html = "%.1f 秒" % d["t100"]
    else:
        t100_html = '<span class="dyno-dim">未测到</span>'

    def _roll(k):
        v = (d.get("roll") or {}).get(k)
        if v is None:
            return '<span class="dyno-dim">—</span>'
        return "%.2f 秒" % float(v)

    kv_rows = [
        ("整车质量", "%.0f kg" % d["mass"]),
        ("最大加速", "%+.2f g" % d["acc_max"]),
        ("最大减速", "%.2f g" % d["acc_min"]),
        ("0-100", t100_html),
        ("60-100 km/h", _roll("60-100")),
        ("80-120 km/h", _roll("80-120")),
        ("100-150 km/h", _roll("100-150")),
        ("车型", esc(d.get("model") or "—")),
        ("配置", esc(d.get("config") or "—")),
    ]
    kv = "".join('<div class="kv-row"><dt>%s</dt><dd>%s</dd></div>' % (k, v)
                 for k, v in kv_rows)

    kv_hint = ""
    if not d.get("t100"):
        kv_hint = ('<div class="hint dyno-kv-hint">%s<span>0-100 未测到：%s。'
                   '滚动加速是同一份数据里 a→b km/h 的最快用时（线性插值过线）。</span></div>'
                   % (IC["info"], esc(d.get("t100_note") or "")))

    kv_card = """
      <article class="card dyno-kv-card">
        <div class="panel-head">
          <div><h2>关键指标</h2><p>这份 CSV 算出来的数</p></div>
          <span class="mini-chip">%s</span>
        </div>
        <dl class="kv">%s</dl>
        %s
      </article>""" % ("轮上反推" if has_dyno else "无转速数据", kv, kv_hint)

    if has_dyno:
        style_card = """
      <article class="card dyno-tell-card">
        <div class="panel-head">
          <div><h2>发力特性</h2><p>按功率 / 扭矩曲线自动判断</p></div>
        </div>
        <div class="dyno-verdict">%s</div>
        <p class="dyno-verdict-sub">%s</p>
        <p class="hint dyno-shape">%s<span>%s</span></p>
      </article>""" % (esc(d.get("dyno_style") or "—"),
                        esc(d.get("dyno_style_note") or ""),
                        IC["info"], esc(d.get("dyno_shape") or ""))
    else:
        style_card = """
      <article class="card dyno-tell-card">
        <div class="panel-head">
          <div><h2>为什么没有 dyno</h2><p>这份数据缺了什么</p></div>
        </div>
        %s
      </article>""" % empty_state(
            "pulse", "缺转速 / 扭矩记录",
            "dyno 需要转速稳定上升、油门 >25% 且车速 >2 m/s 的重叠采样。"
            "用新版抓包扩展跑一段全油门加速再导出即可。")

    if has_dyno:
        note_items = (
            '<li>%s<span>功率 P = m·a·v：m 取四轮载荷 <b>%.0f kg</b>，a 为 dv/dt；'
            '按转速 120 rpm 分档取 90 分位。扭矩由 T = 9549·P / rpm 反算 —— '
            '都是轮上反推，不是台架实测。</span></li>'
            '<li>%s<span>加速 G 只取油门 &gt;60%%、方向盘接近回正的直线段，'
            '避免过弯和制动的干扰。</span></li>'
        ) % (IC["pulse"], d["mass"], IC["gauge"])
    else:
        note_items = (
            '<li>%s<span>这份数据没有可用的转速记录，所以功率 / 扭矩曲线算不出来；'
            '其余指标照常从载荷与车速算出。</span></li>'
            '<li>%s<span>加速 G 只取油门 &gt;60%%、方向盘接近回正的直线段，'
            '避免过弯和制动的干扰。</span></li>'
        ) % (IC["pulse"], IC["gauge"])

    note_card = """
      <article class="card dyno-note-card">
        <div class="panel-head">
          <div><h2>这些数怎么来的</h2><p>全部由 analyze() 从 CSV 算出</p></div>
        </div>
        <ul class="dyno-notes">%s</ul>
        <div class="dyno-src" title="%s">数据出处：%s · %s 点 @ 10 Hz</div>
      </article>""" % (note_items, esc(d["file"]), esc(d["file"]),
                        "{:,}".format(d["points"]))

    return kv_card + style_card + note_card


def render(d):
    """返回完整的一页：<section class="page" data-page="dyno"> ... </section>。"""
    from .common import head_html, chip

    has_dyno = bool(d.get("dyno"))
    chips = (
        chip("pin", d["level"])
        + chip("clock", "%s 点 @ 10 Hz" % "{:,}".format(d["points"]))
        + chip("gauge", "均 %.0f · 最高 %.0f km/h" % (d["v_avg_kmh"], d["v_max_kmh"]))
    )
    head = head_html(d["file"], d["file"], TITLE,
                     "轮上反推" if has_dyno else "无转速数据", SUB, chips)
    body = """
    <section class="page-body">
      %s
      <section class="grid">
        <div class="dyno-left">%s</div>
        <aside class="side">%s</aside>
      </section>
    </section>""" % (_stats_html(d), _left_html(d), _side_html(d))
    return ('<section class="page" data-page="dyno" data-title="%s">\n%s%s\n</section>'
            % (TITLE, head, body))


# ══════════════════════════════════════════════════════════════════════
# 本页样式 / 脚本
# ══════════════════════════════════════════════════════════════════════
CSS = """
/* ── 动力曲线页 ─────────────────────────────────────── */
[data-page="dyno"] .dyno-left{display:flex;flex-direction:column;gap:16px;min-height:0}
[data-page="dyno"] .dyno-power-card{flex:1.36;min-height:0}
[data-page="dyno"] .dyno-row{display:flex;gap:16px;flex:1;min-height:0}
[data-page="dyno"] .dyno-accel-card{flex:1.62;min-width:0;min-height:0}
[data-page="dyno"] .dyno-accel-card.is-solo{flex:1}
[data-page="dyno"] .dyno-accel-card.is-solo .empty-text{max-width:560px}
[data-page="dyno"] .dyno-band-card{flex:1;min-width:0;min-height:0;padding:16px 18px 13px}

[data-page="dyno"] .dyno-band-card .panel-head h2{font-size:15px}
[data-page="dyno"] .dyno-band-card .panel-head p{font-size:11.2px}
[data-page="dyno"] .dyno-band-list{flex:1;display:flex;flex-direction:column;
  justify-content:space-evenly;gap:3px;min-height:0;margin-top:6px}
[data-page="dyno"] .dyno-band{display:flex;align-items:center;gap:8px;line-height:1.2}
[data-page="dyno"] .dyno-band .bl{flex:0 0 44px;text-align:right;color:var(--muted);
  font-size:10.6px;font-variant-numeric:tabular-nums}
[data-page="dyno"] .dyno-band .bt{position:relative;flex:1;height:10px;border-radius:999px;
  background:rgba(91,143,185,.1);box-shadow:inset 0 1px 2px rgba(60,90,120,.08)}
[data-page="dyno"] .dyno-band .bf{display:block;height:100%;border-radius:999px;
  background:linear-gradient(90deg,#8FBEDD,#5B8FB9);
  box-shadow:0 5px 12px -7px rgba(91,143,185,.9)}
[data-page="dyno"] .dyno-band.is-peak .bf{background:linear-gradient(90deg,#EFC98C,#D9A24A);
  box-shadow:0 5px 12px -7px rgba(217,162,74,.9)}
[data-page="dyno"] .dyno-band .bv{flex:0 0 40px;text-align:right;font-size:10.8px;
  font-weight:600;color:var(--ink);font-variant-numeric:tabular-nums}
[data-page="dyno"] .dyno-band .bv.dim{color:var(--muted);font-weight:500}

[data-page="dyno"] .chart-card .empty{min-height:0;padding:4px 14px;gap:6px}
[data-page="dyno"] .chart-card .empty-ic .ic{width:32px;height:32px}
[data-page="dyno"] .chart-card .empty-title{font-size:14px}
[data-page="dyno"] .chart-card .empty-text{font-size:11.6px;line-height:1.65;max-width:440px}
[data-page="dyno"] .dyno-band-card .empty{padding:0 6px}
[data-page="dyno"] .dyno-band-card .empty-title{font-size:13px}
[data-page="dyno"] .dyno-band-card .empty-text{font-size:11.4px}
[data-page="dyno"] .hint{line-height:1.5}
[data-page="dyno"] .chart-card>.hint{flex:0 0 auto;margin-top:4px;justify-content:center}

[data-page="dyno"] .dyno-dim{color:var(--muted);font-weight:500}
[data-page="dyno"] .side{gap:14px}
[data-page="dyno"] .side .card{padding:15px 18px 13px}
[data-page="dyno"] .kv-row{padding:5px 0;font-size:11.8px}
[data-page="dyno"] .dyno-kv-card{padding-bottom:13px}
[data-page="dyno"] .dyno-kv-hint{margin-top:9px;align-items:flex-start;line-height:1.55}
[data-page="dyno"] .dyno-kv-hint .ic{margin-top:2px}
[data-page="dyno"] .dyno-tell-card{display:flex;flex-direction:column}
[data-page="dyno"] .dyno-verdict{font-size:20px;font-weight:700;letter-spacing:.01em;
  color:var(--ink);margin-top:7px}
[data-page="dyno"] .dyno-verdict-sub{margin:5px 0 0;font-size:12px;line-height:1.5;
  color:var(--blue-3);font-weight:600}
[data-page="dyno"] .dyno-shape{margin-top:auto;padding-top:8px;align-items:flex-start;line-height:1.55}
[data-page="dyno"] .dyno-shape .ic{margin-top:2px;flex:0 0 13px}
[data-page="dyno"] .dyno-note-card{display:flex;flex-direction:column}
[data-page="dyno"] .dyno-notes{list-style:none;margin:8px 0 0;padding:0;
  display:flex;flex-direction:column;gap:7px}
[data-page="dyno"] .dyno-notes li{display:flex;align-items:flex-start;gap:8px;
  font-size:11.4px;line-height:1.58;color:var(--ink-2)}
[data-page="dyno"] .dyno-notes li .ic{flex:0 0 14px;width:14px;height:14px;margin-top:2px;
  color:var(--blue);opacity:.85}
[data-page="dyno"] .dyno-notes b{color:var(--ink);font-weight:600}
[data-page="dyno"] .dyno-src{margin-top:auto;padding-top:10px;border-top:1px dashed var(--line);
  font-size:10.6px;color:var(--muted);letter-spacing:.01em;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

@media (max-width:1240px){
  /* 窄屏：改成纵向堆叠 + 页面内滚动，避免固定高度里卡片互相压 */
  [data-page="dyno"].page.active{overflow-y:auto;overflow-x:hidden;padding-right:2px}
  [data-page="dyno"] .page-body{flex:0 0 auto}
  [data-page="dyno"] .grid{flex:0 0 auto}
  [data-page="dyno"] .dyno-left{min-height:620px}
  [data-page="dyno"] .dyno-power-card{min-height:300px}
  [data-page="dyno"] .dyno-row{flex-direction:column;min-height:470px}
  [data-page="dyno"] .dyno-accel-card{flex:1.1;min-height:230px}
  [data-page="dyno"] .dyno-band-card{flex:1;min-height:210px}
  [data-page="dyno"] .side{flex-direction:row;flex-wrap:wrap;gap:12px}
  [data-page="dyno"] .side .card{flex:1 1 320px;min-width:0}
  [data-page="dyno"] .side .card:last-child{flex:1 1 320px}
}
"""

JS = """
// 动力曲线页脚本：第一次显示这一页时调用一次
window.PAGE_INIT = window.PAGE_INIT || {};
window.PAGE_INIT.dyno = function (root, DATA) {
  function mount(id, opts) {
    var el = root.querySelector('#' + id);
    if (!el || !window.ChartKit) return null;
    try { return window.ChartKit.mount(el, opts); } catch (e) {
      console.error('[dyno chart]', id, e);
      return null;
    }
  }

  // 转速 – 功率（左轴）/ 扭矩（右轴）
  var dy = DATA.dyno || [];
  if (dy.length >= 2) {
    mount('chart-dyno', {
      series: [
        {name: '功率 kW（左轴）', color: '#5B8FB9',
         data: dy.map(function (p) { return [p[0], p[2]]; }),
         fill: true, fillTop: 'rgba(91,143,185,.26)', fillBottom: 'rgba(91,143,185,0)',
         width: 2.4},
        {name: '扭矩 Nm（右轴）', color: '#D9A24A',
         data: dy.map(function (p) { return [p[0], p[1]]; }),
         axis: 'y2', width: 2.2}
      ],
      x:  {label: '转速 (rpm)', fmt: function (v) { return v.toFixed(0) + ' rpm'; }},
      y1: {label: '功率 (kW)'},
      y2: {label: '扭矩 (Nm)'}
    });
  }

  // 加速度 G – 车速
  var cv = DATA.accel_curve || [];
  if (cv.length >= 2) {
    mount('chart-accel', {
      series: [
        {name: '纵向加速度 g', color: '#5B8FB9',
         data: cv.map(function (p) { return [p[0], p[1]]; }),
         fill: true, fillTop: 'rgba(91,143,185,.24)', fillBottom: 'rgba(91,143,185,0)',
         width: 2.4}
      ],
      x:  {label: '车速 (km/h)', fmt: function (v) { return v.toFixed(0) + ' km/h'; }},
      y1: {label: '加速度 (g)'}
    });
  }
};
"""
