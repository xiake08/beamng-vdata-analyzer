# -*- coding: utf-8 -*-
"""悬挂波形页 —— 四角减振器速度随里程的波形；滚轮缩放 / 拖拽平移 / 双击复位

- 数据：d["sv_pts"] = [[里程, FL, FR, RL, RR], ...]（m/s，analyze() 原始符号）
- 展示时按 analyze()["comp_sign"] 归一：向上 = 压缩（顶住），向下 = 回弹（放掉）
- 右侧：前/后轴 RMS、轮荷波动 σ（前后对比看 σ，不看 RMS）、各角 P90
- 只改这个文件，接口约定见 SPEC.md；不要 print 中文。
"""

import os

KEY = "wave"
LABEL = "悬挂波形"
ICON = "wave"
TITLE = "悬挂波形"
BADGE = ""
SUB = "这一页看什么：四根减振器各自怎么跟着路面动 —— 前/后、左/右谁动得多。可以只看前轴、只看后轴，也可以点图例单看某一个轮子。"
ORDER = 5

# tag -> (序号列, 显示名)
_WHEELS = (("FL", "前左 FL"), ("FR", "前右 FR"),
           ("RL", "后左 RL"), ("RR", "后右 RR"))


def build(r, d):
    """analyze() 结果 r -> 往共享数据 d 里补本页字段（必须是 JSON 能序列化的）。"""
    from .common import WHEEL_COLORS
    sv = r.get("sv") or d.get("sv_pts") or []

    # 各角 P90 绝对速度（和老板 _draw_wave 的口径一致：90% 的采样点比它小）
    p90 = {}
    peak = 0.0
    for tag, idx in (("FL", 1), ("FR", 2), ("RL", 3), ("RR", 4)):
        vals = []
        for p in sv:
            try:
                v = abs(float(p[idx]))
            except (TypeError, ValueError, IndexError):
                continue
            vals.append(v)
            if v > peak:
                peak = v
        vals.sort()
        p90[tag] = round(vals[min(len(vals) - 1, int(len(vals) * 0.9))], 3) if vals else 0.0

    d["wave_p90"] = p90
    d["wave_peak"] = round(peak, 3)
    # analyze() 里 comp_sign 表示“速度 × comp_sign >= 0 即压缩”，统一成正=压缩再画
    d["wave_sign"] = 1 if (r.get("comp_sign", 1) or 1) >= 0 else -1
    d["wave_n"] = len(d.get("sv_pts") or [])
    # 四轮配色统一从 common.WHEEL_COLORS 来（前端画线 / 图例共用）
    d["wave_colors"] = dict(WHEEL_COLORS)
    return d


def _head(d):
    from .common import chip, esc, fmt_dist, fmt_dur, head_html
    stem = os.path.splitext(str(d.get("file", "")))[0] or "抓包数据"
    level = str(d.get("level") or "—").replace("_", " ")
    chips = (chip("pin", level)
             + chip("route", "%s · %s" % (fmt_dist(d.get("dist_m", 0.0)),
                                          fmt_dur(d.get("dur_s", 0.0))))
             + chip("pulse", "整车 RMS %.2f m/s" % float(d.get("rms", 0.0))))
    return head_html(stem, d.get("file", ""), TITLE, BADGE, SUB, chips)


def _chart_card(d):
    from .common import IC, WHEEL_COLORS
    lg_items = "".join(
        '<span class="lg wv-lg" data-tag="%s" title="点一下只看 %s，再点回到四轮全部">'
        '<i style="background:%s"></i>%s</span>'
        % (tag, label, WHEEL_COLORS[tag], label) for tag, label in _WHEELS)
    lg = '<div class="legend">%s</div>' % lg_items
    return f"""
      <article class="card chart-card">
        <div class="panel-head chart-head">
          <div>
            <h2>四角减振器速度</h2>
            <p>向上 = 压缩（顶住）· 向下 = 回弹（放掉）· 振幅越大说明这个角越忙</p>
          </div>
          <div class="wv-switch" id="wave-switch" role="group" aria-label="显示范围">
            <button type="button" class="wv-btn active" data-mode="all">全部</button>
            <button type="button" class="wv-btn" data-mode="f">前轴</button>
            <button type="button" class="wv-btn" data-mode="r">后轴</button>
          </div>
        </div>
        <div class="wv-legend-row">
          <div id="wave-legend">{lg}</div>
          <span class="wv-tip">{IC["info"]}<span>点图例 = 只看这一个轮子（再点恢复四轮）</span></span>
          <span class="wv-view" id="wave-view">当前显示：四轮全部</span>
        </div>
        <div class="chart" id="chart-wave"></div>
        <div class="wv-foot">
          <span>符号已按压缩方向归一 · 四条线共用同一纵轴 · 滚轮缩放 / 拖拽平移 / 双击复位</span>
          <span>最大单点振幅 <b>±{d.get("wave_peak", 0.0):.2f}</b> m/s · 全程 {d.get("dist_m", 0.0):,.0f} m</span>
        </div>
      </article>"""


def _rms_card(d):
    from .common import AXIS_COLORS
    fa = float(d.get("rms_f", 0.0))
    ra = float(d.get("rms_r", 0.0))
    mx = max(fa, ra, 1e-9)
    fw = fa / mx * 100.0
    rw = ra / mx * 100.0
    return f"""
      <article class="card">
        <div class="panel-head">
          <div><h2>前后轴工作量</h2><p>减振器速度 RMS · 越大越忙</p></div>
          <span class="mini-chip">RMS</span>
        </div>
        <div class="wv-axis">
          <span class="wv-axis-name">前轴</span>
          <div class="wv-axis-track"><span style="width:{fw:.1f}%;background:linear-gradient(90deg,{AXIS_COLORS["front"]},#8FBEDD)"></span></div>
          <span class="wv-axis-val">{fa:.3f}<small>m/s</small></span>
        </div>
        <div class="wv-axis">
          <span class="wv-axis-name">后轴</span>
          <div class="wv-axis-track"><span style="width:{rw:.1f}%;background:linear-gradient(90deg,{AXIS_COLORS["rear"]},#EBC98E)"></span></div>
          <span class="wv-axis-val">{ra:.3f}<small>m/s</small></span>
        </div>
        <div class="wv-note">整车 RMS <b>{float(d.get("rms", 0.0)):.3f} m/s</b> —— 前/后轴各取左右两个轮的平均。</div>
      </article>"""


def _sigma_card(d):
    from .common import IC, esc
    sf = float(d.get("sig_f", 0.0))
    sr = float(d.get("sig_r", 0.0))
    tot = sf + sr
    fs = sf / tot * 100.0 if tot > 0 else 50.0
    rs = 100.0 - fs
    if d.get("axis_rear"):
        fix = "后轴更忙 —— 优先动后轴的弹簧/阻尼"
    elif float(d.get("axis_pct", 0.0)) > 0:
        fix = "前轴更忙 —— 优先动前轴的弹簧/阻尼"
    else:
        fix = "两轴强度相当 —— 前后不用单独偏袒"
    axis = esc(d.get("axis_text", "前后轴差不多忙"))
    return f"""
      <article class="card">
        <div class="panel-head">
          <div><h2>轮荷波动 σ</h2><p>前后谁更忙，看这个</p></div>
          <span class="mini-chip">σ N</span>
        </div>
        <div class="wv-sig">
          <div class="wv-sig-cell"><b>{sf:,.0f}</b><span>前轴 σ（FL/FR 平均）</span></div>
          <div class="wv-sig-cell"><b>{sr:,.0f}</b><span>后轴 σ（RL/RR 平均）</span></div>
        </div>
        <div class="balance" style="height:9px">
          <span class="front" style="width:{fs:.1f}%;background:linear-gradient(90deg,#5B8FB9,#8FBEDD)"></span>
          <span class="rear" style="width:{rs:.1f}%;background:linear-gradient(90deg,#D9A24A,#EBC98E)"></span>
        </div>
        <div class="wv-axis-text"><b>{axis}</b> —— {fix}</div>
        <div class="wv-hint">{IC["info"]}<span>速度 RMS 受减振器安装几何影响，前后不能直接比大小；轮荷波动 σ 几乎不受影响，前后对比看 σ。</span></div>
      </article>"""


def _p90_card(d):
    from .common import IC, WHEEL_COLORS, esc, fmt_dist
    p90 = d.get("wave_p90") or {}
    mx = max(list(p90.values()) + [1e-9])
    rows = []
    for tag, label in _WHEELS:
        v = float(p90.get(tag, 0.0))
        w = v / mx * 100.0
        color = WHEEL_COLORS[tag]
        rows.append(
            '<div class="wv-p90-row">'
            '<span class="wv-dot" style="background:%s"></span>'
            '<span class="wv-p90-name">%s</span>'
            '<div class="wv-p90-bar"><span style="width:%.1f%%;background:linear-gradient(90deg,%s,%s)"></span></div>'
            '<span class="wv-p90-val">%.2f<small>m/s</small></span>'
            '</div>' % (color, esc(label), w, color, color + "AA", v))
    worst_m = float(d.get("worst_m", 0.0))
    worst_label = ("%s 米处" % "{:,.0f}".format(worst_m)) if worst_m >= 1 else "起点那段"
    worst_rms = float(d.get("worst_rms", 0.0))
    worst_pos = float(d.get("worst_pos", 1.6))
    return f"""
      <article class="card wv-p90-card">
        <div class="panel-head">
          <div><h2>各角 P90 速度</h2><p>只看幅度 · 90% 的采样点比它小</p></div>
          <span class="mini-chip">abs</span>
        </div>
        <div class="wv-p90">{"".join(rows)}</div>
        <div class="wv-hint">{IC["info"]}<span>P90 越大，这个角全程被“折腾”得越狠；和上面的 RMS 是两套口径，别混用。</span></div>
        <div class="wv-sep"></div>
        <div class="wv-worst-head"><span class="wv-worst-label">{IC["pin"]}最颠的一段</span><b>{esc(worst_label)}</b></div>
        <div class="track-mini"><span class="mk" style="left:{min(max(worst_pos, 1.6), 98.4):.2f}%"></span></div>
        <div class="wv-worst-foot">该段 RMS {worst_rms:.2f} m/s · 全程 {fmt_dist(d.get("dist_m", 0.0))}</div>
      </article>"""


def render(d):
    """返回完整的一页：<section class="page" data-page="wave"> ... </section>。"""
    from .common import empty_state
    head = _head(d)
    if not d.get("sv_pts"):
        body = ('<article class="card chart-card">%s</article>'
                % empty_state("wave", "这份数据没有减振器速度记录",
                              "CSV 里没有 FLsv / FRsv / RLsv / RRsv 这几列 —— "
                              "换一份带减振器速度的抓包再来看这一页。"))
        return ('<section class="page" data-page="wave" data-title="%s">\n%s'
                '<section class="page-body">%s</section>\n</section>' % (TITLE, head, body))
    body = ('<section class="grid">%s<aside class="side">%s%s%s</aside></section>'
            % (_chart_card(d), _rms_card(d), _sigma_card(d), _p90_card(d)))
    return ('<section class="page" data-page="wave" data-title="%s">\n%s'
            '<section class="page-body">%s</section>\n</section>' % (TITLE, head, body))


CSS = """/* ── 悬挂波形页（p_wave）────────────────────────────── */
.wv-switch{display:inline-flex;gap:3px;padding:3px;border-radius:11px;
  background:rgba(91,143,185,.075);border:1px solid rgba(91,143,185,.1)}
.wv-btn{border:0;background:transparent;padding:6px 13px;border-radius:8px;font:inherit;
  font-size:11.8px;color:var(--ink-2);cursor:pointer;letter-spacing:.02em;
  transition:background .25s,color .25s,box-shadow .25s}
.wv-btn:hover{color:var(--blue-3);background:rgba(255,255,255,.62)}
.wv-btn.active{background:#fff;color:var(--blue-3);font-weight:600;
  box-shadow:0 7px 16px -10px rgba(50,80,110,.75),inset 0 0 0 1px rgba(91,143,185,.14)}
.wv-legend-row{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:2px 0 6px}
.wv-legend-row .legend .lg{transition:opacity .25s}
.wv-lg{cursor:pointer;border-radius:8px;padding:2px 5px;
  transition:opacity .25s,background .2s,color .2s;
  box-shadow:inset 0 -1px 0 rgba(91,143,185,.22)}
.wv-lg:hover{background:rgba(255,255,255,.7);color:var(--blue-3);box-shadow:inset 0 -1px 0 rgba(91,143,185,.45)}
.wv-lg.off{opacity:.30}
.wv-lg.solo{font-weight:600;color:var(--ink)}
.wv-tip{display:inline-flex;align-items:center;gap:6px;font-size:11.3px;color:var(--muted);
  white-space:nowrap}
.wv-tip .ic{flex:0 0 13px;width:13px;height:13px;color:var(--blue);opacity:.8}
.wv-view{font-size:11.3px;color:var(--blue-3);font-weight:600;white-space:nowrap}
.wv-legend-row .legend .lg.off{opacity:.26}
.wv-legend-row .wv-hint{white-space:nowrap}
.wv-hint{display:flex;align-items:flex-start;gap:7px;font-size:11.4px;line-height:1.6;color:var(--muted)}
.wv-hint .ic{flex:0 0 13px;width:13px;height:13px;margin-top:2px;color:var(--blue);opacity:.8}
.wv-foot{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:9px;
  font-size:11.4px;color:var(--muted);letter-spacing:.01em}
.wv-foot b{color:var(--ink-2);font-weight:600;font-variant-numeric:tabular-nums}

/* 右栏：RMS */
.wv-axis{display:flex;align-items:center;gap:10px;margin-top:13px;font-size:12px;color:var(--ink-2)}
.wv-axis-name{flex:0 0 32px;font-weight:600;color:var(--ink)}
.wv-axis-track{position:relative;flex:1;height:9px;border-radius:999px;overflow:hidden;
  background:rgba(91,143,185,.11);box-shadow:inset 0 1px 2px rgba(60,90,120,.1)}
.wv-axis-track span{display:block;height:100%;border-radius:999px;transition:width .9s var(--ease)}
.wv-axis-val{flex:0 0 78px;text-align:right;font-weight:600;color:var(--ink);font-variant-numeric:tabular-nums}
.wv-axis-val small{font-weight:400;font-size:10.5px;color:var(--muted);margin-left:3px}
.wv-note{margin-top:13px;font-size:11.5px;line-height:1.6;color:var(--muted)}
.wv-note b{color:var(--ink-2);font-weight:600;font-variant-numeric:tabular-nums}

/* 右栏：σ */
.wv-sig{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:13px 0 12px}
.wv-sig-cell{padding:10px 13px 9px;border-radius:12px;background:rgba(255,255,255,.55);
  border:1px solid rgba(255,255,255,.8);box-shadow:0 8px 18px -18px rgba(50,80,110,.6)}
.wv-sig-cell b{display:block;font-size:23px;font-weight:700;line-height:1.15;color:var(--ink);
  font-variant-numeric:tabular-nums;font-family:"Segoe UI","Microsoft YaHei UI",sans-serif}
.wv-sig-cell span{font-size:10.8px;color:var(--muted);letter-spacing:.01em}
.wv-axis-text{margin-top:11px;font-size:11.9px;line-height:1.6;color:var(--ink-2)}
.wv-axis-text b{color:var(--blue-3);font-weight:700}
.wv-sig + .wv-axis-text + .wv-hint{margin-top:11px}

/* 右栏：P90 */
.wv-p90-card{display:flex;flex-direction:column}
.wv-p90{flex:1;display:flex;flex-direction:column;justify-content:space-evenly;margin-top:2px}
.wv-p90-row{display:flex;align-items:center;gap:10px;font-size:12px}
.wv-dot{flex:0 0 9px;width:9px;height:9px;border-radius:50%}
.wv-p90-name{flex:0 0 66px;color:var(--ink-2);letter-spacing:.01em}
.wv-p90-bar{position:relative;flex:1;height:8px;border-radius:999px;overflow:hidden;
  background:rgba(91,143,185,.1)}
.wv-p90-bar span{display:block;height:100%;border-radius:999px}
.wv-p90-val{flex:0 0 76px;text-align:right;font-weight:600;color:var(--ink);font-variant-numeric:tabular-nums}
.wv-p90-val small{font-weight:400;font-size:10.5px;color:var(--muted);margin-left:3px}
.wv-p90-card .wv-hint{margin-top:12px}
.wv-sep{height:1px;margin:14px 0 11px;background:rgba(91,143,185,.14)}
.wv-worst-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;
  font-size:11.8px;color:var(--muted)}
.wv-worst-label{display:inline-flex;align-items:center;gap:7px;letter-spacing:.03em}
.wv-worst-label .ic{width:14px;height:14px;color:var(--blue);opacity:.85}
.wv-worst-head b{font-size:13.5px;font-weight:600;color:var(--ink);font-variant-numeric:tabular-nums}
.wv-worst-foot{margin-top:8px;font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.wv-p90-card .track-mini{margin-top:9px;height:5px}

/* 窄窗口（≤1240 时框架把右栏横排）：收起长说明，保留数字主体，避免压字/溢出 */
@media (max-width:1240px){
  .page[data-page="wave"] .grid{grid-template-rows:minmax(0,1fr) auto}
  .page[data-page="wave"] .grid .chart{min-height:120px}
  .page[data-page="wave"] .wv-hint,
  .page[data-page="wave"] .wv-tip,
  .page[data-page="wave"] .wv-note,
  .page[data-page="wave"] .wv-sep,
  .page[data-page="wave"] .wv-worst-head,
  .page[data-page="wave"] .wv-worst-foot,
  .page[data-page="wave"] .wv-p90-card .track-mini{display:none}
  .page[data-page="wave"] .wv-axis{margin-top:11px}
  .page[data-page="wave"] .wv-sig{margin:11px 0 10px}
  .page[data-page="wave"] .wv-axis-text{margin-top:10px}
  .page[data-page="wave"] .wv-p90{justify-content:flex-start}
  .page[data-page="wave"] .wv-p90-row{margin-top:9px}
  .page[data-page="wave"] .wv-p90-row:first-child{margin-top:2px}
}
"""

JS = """// 悬挂波形页脚本：显示这一页时调用一次
window.PAGE_INIT = window.PAGE_INIT || {};
window.PAGE_INIT.wave = function (root, DATA) {
  var el = root.querySelector('#chart-wave');
  if (!el || !window.ChartKit) return;
  var pts = DATA.sv_pts || [];
  if (!pts.length) return;
  var sign = DATA.wave_sign || 1;          // 归一：正值 = 压缩
  var ORDER = ['FL', 'FR', 'RL', 'RR'];
  var COLORS = DATA.wave_colors || {};
  var META = {
    FL: {name: '前左 FL', color: COLORS.FL || '#5B8FB9', idx: 1},
    FR: {name: '前右 FR', color: COLORS.FR || '#D9A24A', idx: 2},
    RL: {name: '后左 RL', color: COLORS.RL || '#D06A5C', idx: 3},
    RR: {name: '后右 RR', color: COLORS.RR || '#4E9E7B', idx: 4}
  };
  var chart = null;
  var active = ORDER.slice();      // 当前显示的轮子

  function tagsOf(mode) {
    if (mode === 'f') return ['FL', 'FR'];
    if (mode === 'r') return ['RL', 'RR'];
    return ORDER.slice();
  }

  function makeSeries(tags) {
    return tags.map(function (tag) {
      var m = META[tag];
      var data = [];
      for (var i = 0; i < pts.length; i++) {
        data.push([pts[i][0], pts[i][m.idx] * sign]);
      }
      return {name: m.name, color: m.color, width: 1.7, data: data};
    });
  }

  function viewText(tags) {
    if (tags.length >= 4) return '当前显示：四轮全部';
    if (tags.length === 1) return '当前显示：只看 ' + META[tags[0]].name;
    if (tags.length === 2 && tags[0] === 'FL' && tags[1] === 'FR') return '当前显示：前轴（FL / FR）';
    if (tags.length === 2 && tags[0] === 'RL' && tags[1] === 'RR') return '当前显示：后轴（RL / RR）';
    return '当前显示：' + tags.map(function (t) { return META[t].name; }).join(' + ');
  }

  function paint(tags) {
    var lgs = root.querySelectorAll('#wave-legend .lg');
    for (var i = 0; i < lgs.length; i++) {
      var tag = ORDER[i];
      var on = tags.indexOf(tag) >= 0;
      lgs[i].classList.toggle('off', !on);
      lgs[i].classList.toggle('solo', tags.length < 4 && on);
    }
    var isAll = tags.length >= 4;
    var isF = tags.length === 2 && tags[0] === 'FL' && tags[1] === 'FR';
    var isR = tags.length === 2 && tags[0] === 'RL' && tags[1] === 'RR';
    var btns = root.querySelectorAll('#wave-switch .wv-btn');
    Array.prototype.forEach.call(btns, function (b) {
      var m = b.dataset.mode;
      b.classList.toggle('active', (m === 'all' && isAll) || (m === 'f' && isF) || (m === 'r' && isR));
    });
    var view = root.querySelector('#wave-view');
    if (view) view.textContent = viewText(tags);
  }

  function render(tags) {
    active = tags.slice();
    if (!active.length) active = ORDER.slice();
    active.sort(function (a, b) { return ORDER.indexOf(a) - ORDER.indexOf(b); });
    if (chart) { chart.destroy(); chart = null; }
    el.innerHTML = '';
    chart = ChartKit.mount(el, {
      series: makeSeries(active),
      x: {label: '里程 (m)', fmt: function (v) { return v.toFixed(0) + ' m'; }},
      y1: {label: '减振器速度 (m/s)'}
    });
    paint(active);
  }

  // 按钮：全部 / 前轴 / 后轴
  Array.prototype.forEach.call(root.querySelectorAll('#wave-switch .wv-btn'), function (btn) {
    btn.addEventListener('click', function () { render(tagsOf(btn.dataset.mode)); });
  });

  // 图例：点某个轮子 = 只看它；再点同一个 = 回到四轮全部
  Array.prototype.forEach.call(root.querySelectorAll('#wave-legend .wv-lg'), function (lgEl) {
    lgEl.addEventListener('click', function () {
      var tag = lgEl.getAttribute('data-tag');
      if (active.length === 1 && active[0] === tag) render(ORDER);
      else render([tag]);
    });
  });

  render(ORDER);
};"""
