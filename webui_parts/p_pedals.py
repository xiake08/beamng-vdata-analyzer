# -*- coding: utf-8 -*-
"""踏板页 —— 油门/刹车开度曲线 + 踩踏统计；滚轮缩放 / 拖拽平移 / 双击复位

- 数据：d["profile_pts"] = [[里程, 高程, 车速, 油门 0-1, 刹车 0-1], ...]
- build() 把 r["thr_on"]/["brk_on"]/["thr_avg"]/["brk_avg"] 塞进 d，并算好
  驾驶风格文案、操作构成（纯油门 / 同时 / 纯刹车 / 滑行）
- 没有踏板数据（d["has_pedal"] 为 False）给空状态
- 只改这个文件，接口约定见 SPEC.md；不要 print 中文。
"""

import os

KEY = "pedals"
LABEL = "踏板"
ICON = "pedal"
TITLE = "踏板"
BADGE = ""
SUB = "这一页看什么：油门和刹车怎么踩的，以及这趟跑得有多激烈。"
ORDER = 6


def _style_text(thr_on, brk_on, thr_avg, brk_avg):
    """按踏板使用特征给一句驾驶风格 + 色调 + 短标签（数字全部来自数据）。"""
    tp = thr_on
    bp = brk_on
    ta = thr_avg * 100.0
    ba = brk_avg * 100.0
    if thr_on >= 55 and thr_avg >= 0.6 and brk_on < 20:
        return ("blue", "持续给油型",
                "油门压了 <b>%.0f%%</b> 的时间、平均开度 <b>%.0f%%</b>，刹车占 <b>%.0f%%</b> —— "
                "油门主导，属于持续给油型。" % (tp, ta, bp))
    if brk_on >= 15:
        return ("red", "激烈切替型",
                "刹车踩了 <b>%.0f%%</b> 的时间、平均开度 <b>%.0f%%</b>，油门 <b>%.0f%%</b> —— "
                "减速段不少，属于油门刹车来回切的激烈跑法。" % (bp, ba, tp))
    if thr_on >= 40:
        return ("amber", "节奏型驾驶",
                "油门踩下 <b>%.0f%%</b> 时间、平均开度 <b>%.0f%%</b>，踩放比较频繁 —— "
                "属于弯道里点油门的节奏型开法。" % (tp, ta))
    return ("green", "温柔滑行型",
            "油门只踩了 <b>%.0f%%</b> 的时间（平均开度 <b>%.0f%%</b>），大部分时间在滑行 —— "
            "这趟开得比较温柔。" % (tp, ta))


def build(r, d):
    """analyze() 结果 r -> 往共享数据 d 里补本页字段（必须是 JSON 能序列化的）。"""
    from .common import BAD, BLUE
    prof = r.get("profile") or []
    n = len(prof) or 1
    thr_on = float(r.get("thr_on", 0.0) or 0.0)
    brk_on = float(r.get("brk_on", 0.0) or 0.0)
    thr_avg = float(r.get("thr_avg", 0.0) or 0.0)
    brk_avg = float(r.get("brk_avg", 0.0) or 0.0)

    d["thr_on"] = thr_on                    # 油门踩下时间 %（analyze() 原值）
    d["brk_on"] = brk_on                    # 刹车踩下时间 %
    d["thr_avg"] = thr_avg                  # 平均开度 0-1
    d["brk_avg"] = brk_avg                  # 平均开度 0-1
    # 油门/刹车配色统一从 common 来（前端画线 / 图例共用）
    d["ped_colors"] = {"thr": BLUE, "brk": BAD}

    # 操作构成（互斥四类，加起来 100%）：纯油门 / 油门+刹车 / 纯刹车 / 滑行
    cats = {"thr": 0, "both": 0, "brk": 0, "coast": 0}
    thr_full = 0
    brk_full = 0
    for p in prof:
        try:
            t = float(p[5]) if len(p) > 5 else 0.0
            b = float(p[6]) if len(p) > 6 else 0.0
        except (TypeError, ValueError):
            t = b = 0.0
        to, bo = t > 0.1, b > 0.1
        if to and bo:
            cats["both"] += 1
        elif to:
            cats["thr"] += 1
        elif bo:
            cats["brk"] += 1
        else:
            cats["coast"] += 1
        if t >= 0.9:
            thr_full += 1
        if b >= 0.8:
            brk_full += 1

    d["ped_cats"] = {k: round(v / n * 100.0, 1) for k, v in cats.items()}
    d["thr_full"] = round(thr_full / n * 100.0, 1)
    d["brk_full"] = round(brk_full / n * 100.0, 1)

    tone, label, text = _style_text(thr_on, brk_on, thr_avg, brk_avg)
    d["pedal_tone"] = tone
    d["pedal_label"] = label
    d["pedal_style"] = text
    d["pedal_note"] = ("刹车时间占比不低 —— 减速时的点头/前倾会混进悬挂数据，判断悬挂时先看油门段。"
                       if brk_on > 15 else
                       "判断悬挂表现时先看油门段：刹车时的点头/前倾会混进波形。")
    return d


def _head(d):
    from .common import chip, esc, fmt_dist, fmt_dur, head_html
    stem = os.path.splitext(str(d.get("file", "")))[0] or "抓包数据"
    level = str(d.get("level") or "—").replace("_", " ")
    chips = (chip("pin", level)
             + chip("route", "%s · %s" % (fmt_dist(d.get("dist_m", 0.0)),
                                          fmt_dur(d.get("dur_s", 0.0))))
             + chip("pedal", "油门 %.0f%% · 刹车 %.0f%%"
                    % (float(d.get("thr_on", 0.0)), float(d.get("brk_on", 0.0)))))
    return head_html(stem, d.get("file", ""), TITLE, BADGE, SUB, chips)


def _chart_card(d):
    from .common import IC, legend
    colors = d.get("ped_colors") or {}
    c_thr = colors.get("thr", "#5B8FB9")
    c_brk = colors.get("brk", "#D06A5C")
    lg = legend([("油门开度", c_thr, False), ("刹车开度", c_brk, False)])
    return f"""
      <article class="card chart-card">
        <div class="panel-head chart-head">
          <div>
            <h2>油门 / 刹车开度</h2>
            <p>蓝 = 油门 · 红 = 刹车 · 面积越高踩得越深 · 横轴是里程</p>
          </div>
          {lg}
        </div>
        <div class="chart" id="chart-pedals"></div>
        <div class="pd-foot">
          <span class="pd-hint">{IC["info"]}<span>滚轮缩放 · 拖拽平移 · 双击复位</span></span>
          <span>全程 {d.get("dist_m", 0.0):,.0f} m / {d.get("dur_s", 0.0):.0f} 秒 · {int(d.get("points", 0)):,} 个采样点</span>
        </div>
      </article>"""


def _use_card(d):
    """踏板使用：油门/刹车两行（踩下时间 + 平均开度 + 全开占比）。"""
    ta = float(d.get("thr_avg", 0.0)) * 100.0
    ba = float(d.get("brk_avg", 0.0)) * 100.0
    tp = float(d.get("thr_on", 0.0))
    bp = float(d.get("brk_on", 0.0))
    rows = []
    for name, when, avg, full, full_label, c1, c2 in (
            ("油门", tp, ta, float(d.get("thr_full", 0.0)), "全开 ≥90%", "#5B8FB9", "#8FBEDD"),
            ("刹车", bp, ba, float(d.get("brk_full", 0.0)), "到底 ≥80%", "#D06A5C", "#E39A8E")):
        rows.append(f"""
        <div class="pd-row" style="--c:{c1};--c1:{c1};--c2:{c2}">
          <div class="pd-row-head">
            <span class="pd-dot"></span><b class="pd-name">{name}</b>
            <span class="pd-time">踩下 <b>{when:.0f}%</b> 时间</span>
            <span class="pd-avg">平均开度 <b>{avg:.0f}%</b></span>
          </div>
          <div class="pd-bar"><span style="width:{min(max(when, 0.0), 100.0):.1f}%"></span></div>
          <div class="pd-row-foot">{full_label} <b>{full:.0f}%</b> 时间</div>
        </div>""")
    return f"""
      <article class="card">
        <div class="panel-head">
          <div><h2>踏板使用</h2><p>踩下时间占比 · 平均开度</p></div>
          <span class="mini-chip">0–100%</span>
        </div>
        {"".join(rows)}
      </article>"""


def _pct_label(v):
    """占比文案：小于 10% 的保留一位小数，别把 0.3% 显示成 0%。"""
    v = float(v)
    return ("%.1f%%" % v) if 0 < v < 10 else ("%.0f%%" % v)


def _style_card(d):
    from .common import IC, esc
    cats = d.get("ped_cats") or {}
    tone = d.get("pedal_tone", "blue")
    label = d.get("pedal_label", "驾驶风格")
    parts = [("纯油门", cats.get("thr", 0.0), "#5B8FB9"),
             ("油门+刹车", cats.get("both", 0.0), "#D9A24A"),
             ("纯刹车", cats.get("brk", 0.0), "#D06A5C"),
             ("滑行", cats.get("coast", 0.0), "rgba(91,143,185,.28)")]
    segs = "".join('<span style="width:%.2f%%;background:%s"></span>'
                   % (max(0.0, float(v)), c) for _n, v, c in parts)
    lg = "".join('<span><i style="background:%s"></i>%s %s</span>'
                 % (c, esc(n), _pct_label(v)) for n, v, c in parts)
    return f"""
      <article class="card">
        <div class="panel-head">
          <div><h2>驾驶风格</h2><p>按踏板使用特征自动判断</p></div>
          <span class="pd-chip pd-chip-{tone}">{esc(label)}</span>
        </div>
        <div class="pd-style">{d.get("pedal_style", "")}</div>
        <div class="pd-split">{segs}</div>
        <div class="pd-split-legend">{lg}</div>
        <div class="pd-note">{IC["info"]}<span>{esc(d.get("pedal_note", ""))}</span></div>
      </article>"""


def _info_card(d):
    from .common import fmt_dist, fmt_dur
    rows = [
        ("里程", fmt_dist(d.get("dist_m", 0.0))),
        ("时长", fmt_dur(d.get("dur_s", 0.0))),
        ("均速", "%.0f km/h" % float(d.get("v_avg_kmh", 0.0))),
        ("最高车速", "%.0f km/h" % float(d.get("v_max_kmh", 0.0))),
        ("采样", "%s 点 @ 10 Hz" % "{:,}".format(int(d.get("points", 0)))),
        ("文件", "%.0f KB" % float(d.get("file_kb", 0.0))),
    ]
    kv = "".join('<div class="kv-row"><dt>%s</dt><dd>%s</dd></div>' % (k, v) for k, v in rows)
    return f"""
      <article class="card">
        <div class="panel-head">
          <div><h2>这份数据</h2><p>BeamNG 抓包 · 10 Hz</p></div>
        </div>
        <dl class="kv">{kv}</dl>
      </article>"""


def render(d):
    """返回完整的一页：<section class="page" data-page="pedals"> ... </section>。"""
    from .common import empty_state
    head = _head(d)
    if not d.get("has_pedal") or not d.get("profile_pts"):
        body = ('<article class="card chart-card">%s</article>'
                % empty_state("pedal", "这份数据没有踏板记录",
                              "这份 CSV 没有油门/刹车列（或者全程都没踩过踏板）—— "
                              "换一份带 thr / brk 列的新版抓包再来看这一页。"))
        return ('<section class="page" data-page="pedals" data-title="%s">\n%s'
                '<section class="page-body">%s</section>\n</section>' % (TITLE, head, body))
    body = ('<section class="grid">%s<aside class="side">%s%s%s</aside></section>'
            % (_chart_card(d), _use_card(d), _style_card(d), _info_card(d)))
    return ('<section class="page" data-page="pedals" data-title="%s">\n%s'
            '<section class="page-body">%s</section>\n</section>' % (TITLE, head, body))


CSS = """/* ── 踏板页（p_pedals）──────────────────────────────── */
.pd-hint{display:flex;align-items:center;gap:7px;font-size:11.4px;color:var(--muted)}
.pd-hint .ic{width:13px;height:13px;color:var(--blue);opacity:.8}
.pd-foot{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:9px;
  font-size:11.4px;color:var(--muted);letter-spacing:.01em}

/* 右栏：踏板使用 */
.pd-row{margin-top:14px}
.pd-row-head{display:flex;align-items:baseline;gap:8px;font-size:11.8px;color:var(--muted)}
.pd-dot{flex:0 0 8px;width:8px;height:8px;border-radius:50%;background:var(--c);align-self:center}
.pd-name{font-size:13px;font-weight:600;color:var(--ink);letter-spacing:.01em}
.pd-time{margin-left:auto;color:var(--ink-2)}
.pd-time b{font-size:14.5px;font-weight:700;color:var(--c);font-variant-numeric:tabular-nums}
.pd-avg{flex:0 0 auto;color:var(--muted)}
.pd-avg b{color:var(--ink-2);font-weight:600;font-variant-numeric:tabular-nums}
.pd-bar{position:relative;height:10px;margin-top:9px;border-radius:999px;overflow:hidden;
  background:rgba(91,143,185,.1);box-shadow:inset 0 1px 2px rgba(60,90,120,.1)}
.pd-bar span{display:block;height:100%;border-radius:999px;
  background:linear-gradient(90deg,var(--c1),var(--c2));transition:width 1s var(--ease)}
.pd-row-foot{margin-top:7px;font-size:10.9px;color:var(--muted);letter-spacing:.01em}
.pd-row-foot b{color:var(--ink-2);font-weight:600;font-variant-numeric:tabular-nums}

/* 右栏：驾驶风格 */
.pd-chip{flex:0 0 auto;font-size:10.8px;font-weight:600;letter-spacing:.02em;padding:4px 9px;
  border-radius:999px;white-space:nowrap}
.pd-chip-blue{color:#3E6B92;background:rgba(91,143,185,.12);border:1px solid rgba(91,143,185,.18)}
.pd-chip-red{color:#A9453A;background:rgba(208,106,92,.12);border:1px solid rgba(208,106,92,.22)}
.pd-chip-amber{color:#96661A;background:rgba(217,162,74,.15);border:1px solid rgba(217,162,74,.24)}
.pd-chip-green{color:#2F6B52;background:rgba(62,158,123,.12);border:1px solid rgba(62,158,123,.2)}
.pd-style{margin-top:12px;font-size:12.4px;line-height:1.72;color:var(--ink-2)}
.pd-style b{color:var(--ink);font-weight:700;font-variant-numeric:tabular-nums}
.pd-split{display:flex;gap:2px;height:12px;margin-top:14px;border-radius:999px;overflow:hidden;
  background:rgba(91,143,185,.08);box-shadow:inset 0 1px 2px rgba(60,90,120,.08)}
.pd-split span{display:block;height:100%}
.pd-split-legend{display:flex;flex-wrap:wrap;gap:8px 14px;margin-top:10px;font-size:11px;color:var(--muted)}
.pd-split-legend span{display:inline-flex;align-items:center;gap:5px;font-variant-numeric:tabular-nums}
.pd-split-legend i{width:8px;height:8px;border-radius:2px;display:inline-block}
.pd-note{display:flex;align-items:flex-start;gap:8px;margin-top:13px;padding:10px 12px;border-radius:11px;
  font-size:11.3px;line-height:1.6;color:var(--ink-2);
  background:linear-gradient(90deg,rgba(91,143,185,.09),rgba(91,143,185,.03));
  border:1px solid rgba(91,143,185,.12)}
.pd-note .ic{flex:0 0 14px;width:14px;height:14px;margin-top:1px;color:var(--blue);opacity:.85}

/* 窄窗口（≤1240 时框架把右栏横排）：图表让位、收起长提示，别压字 */
@media (max-width:1240px){
  .page[data-page="pedals"] .grid{grid-template-rows:minmax(0,1fr) auto}
  .page[data-page="pedals"] .grid .chart{min-height:120px}
  .page[data-page="pedals"] .pd-hint{display:none}
  .page[data-page="pedals"] .pd-note{margin-top:10px}
}
"""

JS = """// 踏板页脚本：显示这一页时调用一次
window.PAGE_INIT = window.PAGE_INIT || {};
window.PAGE_INIT.pedals = function (root, DATA) {
  var el = root.querySelector('#chart-pedals');
  if (!el || !window.ChartKit) return;
  var pts = DATA.profile_pts || [];
  if (!pts.length) return;
  var thr = [], brk = [];
  for (var i = 0; i < pts.length; i++) {
    var p = pts[i];
    thr.push([p[0], p[3] * 100]);
    brk.push([p[0], p[4] * 100]);
  }
  var COLORS = DATA.ped_colors || {};
  var cThr = COLORS.thr || '#5B8FB9';
  var cBrk = COLORS.brk || '#D06A5C';
  ChartKit.mount(el, {
    series: [
      {name: '油门开度', color: cThr, width: 2, fill: true,
       fillTop: 'rgba(91,143,185,.28)', fillBottom: 'rgba(91,143,185,.015)', data: thr},
      {name: '刹车开度', color: cBrk, width: 2, fill: true,
       fillTop: 'rgba(208,106,92,.26)', fillBottom: 'rgba(208,106,92,.015)', data: brk}
    ],
    x: {label: '里程 (m)', fmt: function (v) { return v.toFixed(0) + ' m'; }},
    y1: {label: '踏板开度 (%)'}
  });
};"""
