# -*- coding: utf-8 -*-
"""发动机页 —— 转速 / 增压 / 空燃比 / 温度 / 油压 + 自动问题诊断

数据来自 CSV 的 eng 列（扩展采样 electrics 里发动机相关数值，键名随车不同，
analyze_engine() 已做同义词归一化），build() 只负责把 d["engine"] 搬过来。
"""

KEY = "engine"
LABEL = "发动机"
ICON = "gauge"
TITLE = "发动机"
BADGE = ""
SUB = "这一页看什么：转速、增压、空燃比、水温/油温、油温超温报警，以及自动查出来的发动机问题。"
ORDER = 3.5


def build(r, d):
    eng = r.get("engine") or {}
    d["engine"] = eng
    return d


def _head(d):
    from .common import chip, esc, fmt_dist, fmt_dur, head_html
    import os
    stem = os.path.splitext(str(d.get("file", "")))[0] or "抓包数据"
    level = str(d.get("level") or "—").replace("_", " ")
    eng = d.get("engine") or {}
    st = eng.get("stats") or {}
    bits = []
    if st.get("boost"):
        bits.append("增压 %.2f bar" % st["boost"]["max"])
    if st.get("water"):
        bits.append("水温最高 %.0f°C" % st["water"]["max"])
    chips = (chip("pin", level)
             + chip("route", "%s · %s" % (fmt_dist(d.get("dist_m", 0.0)),
                                          fmt_dur(d.get("dur_s", 0.0))))
             + (chip("gauge", " · ".join(bits)) if bits else ""))
    return head_html(stem, d.get("file", ""), TITLE, BADGE, SUB, chips)


def _fmt(v, unit="", digits=1):
    if v is None:
        return "—"
    return ("%." + str(digits) + "f%s") % (v, unit)


def _stats_html(d):
    from .common import IC
    eng = d.get("engine") or {}
    st = eng.get("stats") or {}
    boost = st.get("boost") or {}
    boost_psi = st.get("boost_psi") or {}
    afr = st.get("afr") or {}
    water = st.get("water") or {}
    oil = st.get("oil") or {}
    oa = st.get("oilalarm") or {}
    rpm = st.get("rpm") or {}
    cards = []

    def card(tone, icon, label, value, unit, foot):
        cards.append(
            '<article class="card stat" style="--tone:%s">'
            '<div class="stat-label">%s%s</div>'
            '<div class="stat-value tone">%s<small>%s</small></div>'
            '<div class="stat-foot">%s</div></article>'
            % (tone, IC[icon], label, value, unit, foot))

    if boost:
        card("#5B8FB9", "gauge", "峰值增压", _fmt(boost.get("max"), "", 2), "bar",
             "≈ %.0f psi · 本车最大 %.2f bar"
             % (boost_psi.get("max", 0), (st.get("boostmax") or {}).get("bar", 0)))
    if afr:
        card("#D9A24A", "pulse", "空燃比（全程）",
             _fmt(afr.get("min"), "", 1) + "–" + _fmt(afr.get("max"), "", 1), "AFR",
             "负载下 11–15 为正常范围")
    if water:
        foot = ("油温最高 %s °C" % _fmt(oil.get("max"), "", 0)) if oil else \
               ("最高转速 %.0f rpm" % (rpm.get("max") or 0)) if rpm else ""
        card("#4E9E7B", "clock", "最高水温", _fmt(water.get("max"), "", 0), "°C", foot)
    if not cards:
        return ""
    return '<section class="stats">%s</section>' % "".join(cards)


def _howto_card(d):
    from .common import IC
    items = [
        ("温度", "水温 80–105°C、油温 90–120°C。长时间往上爬 = 散热/机油扛不住。"),
        ("空燃比 AFR", "理论 14.7；全油门 11–13 算浓（保护发动机），>16 太稀容易爆震/过热。"),
        ("增压", "看你这台车的目标值；突然掉压/超压 = 泄压阀、管路或调校有问题。"),
        ("转速", "台阶 = 换挡；贴着红区不掉 = 可能限转/打滑；尖峰 = 断油或空转。"),
        ("发动机状态", "正常 / 扭矩受限 / 已损坏停用；部位栏会列出损坏的具体部件。"),
    ]
    rows = "".join('<div class="eng-how-row"><b>%s</b><span>%s</span></div>' % (k, v)
                   for k, v in items)
    return """
      <article class="card eng-how-card">
        <div class="panel-head"><div><h2>这一页怎么看</h2><p>先看温度/空燃比/增压，再看曲线形状</p></div></div>
        %s
        <div class="hint">%s<span>横轴统一用时间，原地轰油门也能看；没有的字段不会显示。</span></div>
      </article>""" % (rows, IC["info"])


def _problems_card(d):
    from .common import IC
    probs = (d.get("engine") or {}).get("problems") or []
    rows = []
    for it in probs:
        tone = it.get("tone", "ok")
        rows.append(
            '<div class="eng-prob eng-%s"><span class="eng-dot"></span>'
            '<div><b>%s</b><p>%s</p></div></div>'
            % (tone, it.get("title", ""), it.get("text", "")))
    if not rows:
        rows = ['<div class="hint">%s<span>这份数据没有发动机异常。</span></div>' % IC["info"]]
    return """
      <article class="card eng-prob-card">
        <div class="panel-head"><div><h2>发动机诊断</h2><p>按温度 / 空燃比 / 增压 / 损伤自动判断</p></div>
        <span class="mini-chip">%d 条</span></div>
        %s
      </article>""" % (len(probs), "".join(rows))


def _eng_state(dmg):
    """发动机状态一句话：正常 / 扭矩受限 / 已损坏停用 / 旧数据 —"""
    if not dmg.get("has"):
        return "—"
    st = dmg.get("state") or {}
    if st.get("broken") or st.get("disabled") or dmg.get("flags", {}).get("engineDisabled"):
        return "已损坏停用"
    ts = st.get("torque_state")
    if isinstance(ts, (int, float)) and ts < 0.99:
        return "扭矩受限 %.0f%%" % (ts * 100)
    if dmg.get("bad"):
        return "有损伤"
    return "正常"


def _values_card(d):
    eng = d.get("engine") or {}
    st = eng.get("stats") or {}
    dmg = eng.get("damage") or {}

    def rng(k, unit="", digits=1):
        s = st.get(k)
        if not s:
            return "—"
        return ("%s – %s" % (_fmt(s["min"], unit, digits), _fmt(s["max"], unit, digits)))

    rows = [
        ("转速", rng("rpm", " rpm", 0)),
        ("发动机负荷", rng("load", "%", 0)),
        ("增压", rng("boost", " bar", 2)),
        ("空燃比", rng("afr", "", 1)),
        ("水温", rng("water", "°C", 0)),
        ("油温", rng("oil", "°C", 0)),
    ]
    pct = (st.get("oilalarm") or {}).get("pct")
    if pct:
        rows.append(("机油超温报警", "%.0f%% 时间" % pct))
    if dmg.get("has"):
        rows.append(("发动机状态", _eng_state(dmg)))
        bad = dmg.get("bad") or []
        if bad:
            rows.append(("发动机损伤部位", "、".join(bad[:8])))
        elif _eng_state(dmg) != "正常":
            rows.append(("发动机损伤部位", "无"))
    rows = [(k, v) for k, v in rows if v not in ("—", "", None)]
    kv = "".join('<div class="kv-row"><dt>%s</dt><dd>%s</dd></div>' % (k, v) for k, v in rows)
    return """
      <article class="card">
        <div class="panel-head"><div><h2>数值范围</h2><p>这一趟的最小 – 最大</p></div></div>
        <dl class="kv">%s</dl>
      </article>""" % kv


def _chart_card(cid, title, sub, lg=""):
    return """
      <article class="card chart-card eng-chart">
        <div class="chart-head">
          <div><h2>%s</h2><p>%s</p></div>
          %s
        </div>
        <div class="chart" id="%s"></div>
      </article>""" % (title, sub, lg, cid)


def render(d):
    from .common import empty_state
    head = _head(d)
    eng = d.get("engine") or {}
    if not eng.get("has"):
        body = ('<article class="card chart-card">%s</article>'
                % empty_state("gauge", "这份数据没有发动机记录",
                              "发动机数据是 v2.2 抓包扩展新加的：用新版扩展重新装进游戏、"
                              "重启游戏后再跑一段，CSV 会多出 eng 列。旧 CSV 只能看悬挂/动力那些页。"))
        return ('<section class="page" data-page="%s" data-title="%s">\n%s'
                '<section class="page-body">%s</section>\n</section>' % (KEY, TITLE, head, body))

    from .common import legend, IC
    lg_rpm = legend([("转速", "#5B8FB9", False)])
    lg_temp = legend([("水温", "#D06A5C", False), ("油温", "#D9A24A", False)])
    lg_fuel = legend([("空燃比", "#4E9E7B", False), ("增压 bar", "#5B8FB9", False)])

    charts = _chart_card("chart-eng-rpm", "转速", "横轴是时间（秒）· 台阶处是换挡，尖峰看有没有断油/空转",
                         lg_rpm)
    charts2 = ('<div class="eng-two">%s%s</div>'
               % (_chart_card("chart-eng-temp", "温度", "水温 80–105°C、油温 90–120°C 算正常；持续往上走就要查散热/机油", lg_temp),
                  _chart_card("chart-eng-fuel", "空燃比 / 增压", "负载下 AFR 11–15 正常；增压看调校值和有没有掉压",
                              lg_fuel)))
    left = '<div class="eng-left">%s%s</div>' % (charts, charts2)
    side = "%s%s%s" % (_howto_card(d), _problems_card(d), _values_card(d))
    note = ('<div class="hint">%s<span>阈值：水温 ≥100°C 偏高 / ≥110°C 过热；油温 ≥115°C 偏高；'
            '空燃比 &gt;16 偏稀 / &lt;9.5 偏浓；增压 &gt;2.5 bar 提醒。'
            '数据来自游戏电控（不同车字段不同，缺的项会写明而不是画空白）。</span></div>' % IC["info"])
    return ('<section class="page" data-page="%s" data-title="%s">\n%s'
            '<section class="page-body">%s'
            '<section class="grid">%s<aside class="side">%s</aside></section>'
            '%s</section>\n</section>'
            % (KEY, TITLE, head, _stats_html(d), left, side, note))


CSS = """
[data-page="engine"] .eng-how-card{flex:0 0 auto}
[data-page="engine"] .eng-how-row{display:flex;gap:8px;margin-top:7px;font-size:11.6px;line-height:1.5}
[data-page="engine"] .eng-how-row b{flex:0 0 66px;color:var(--ink-2);font-size:11.8px}
[data-page="engine"] .eng-how-row span{color:var(--muted)}
[data-page="engine"] .stats{grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
[data-page="engine"] .eng-left{display:flex;flex-direction:column;gap:16px;min-height:0}
[data-page="engine"] .eng-chart{min-height:220px}
[data-page="engine"] .eng-two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
[data-page="engine"] .eng-prob-card{flex:0 0 auto}
[data-page="engine"] .eng-prob{display:flex;gap:10px;padding:9px 10px;border-radius:12px;
  background:rgba(255,255,255,.55);border:1px solid rgba(255,255,255,.8);margin-top:8px}
[data-page="engine"] .eng-prob .eng-dot{width:8px;height:8px;border-radius:50%;margin-top:5px;flex:0 0 auto}
[data-page="engine"] .eng-prob b{font-size:12.6px;color:var(--ink)}
[data-page="engine"] .eng-prob p{margin:2px 0 0;font-size:11.6px;line-height:1.55;color:var(--muted)}
[data-page="engine"] .eng-bad{background:rgba(208,106,92,.10);border-color:rgba(208,106,92,.28)}
[data-page="engine"] .eng-bad .eng-dot{background:#D06A5C}
[data-page="engine"] .eng-warn{background:rgba(217,162,74,.12);border-color:rgba(217,162,74,.30)}
[data-page="engine"] .eng-warn .eng-dot{background:#D9A24A}
[data-page="engine"] .eng-info{background:rgba(91,143,185,.10);border-color:rgba(91,143,185,.26)}
[data-page="engine"] .eng-info .eng-dot{background:#5B8FB9}
[data-page="engine"] .eng-ok{background:rgba(78,158,123,.10);border-color:rgba(78,158,123,.28)}
[data-page="engine"] .eng-ok .eng-dot{background:#4E9E7B}
@media (max-width:1180px){[data-page="engine"] .eng-two{grid-template-columns:1fr}}
"""

JS = """
window.PAGE_INIT = window.PAGE_INIT || {};
window.PAGE_INIT.engine = function (root, DATA) {
  var eng = DATA.engine || {};
  var ser = eng.series || {};
  if (!window.ChartKit) return;
  function mount(id, cfg) {
    var el = root.querySelector('#' + id);
    if (!el) return;
    var missing = (cfg.series || []).filter(function (s) { return !s.data || !s.data.length; })
      .map(function (s) { return s.name; });
    var usable = (cfg.series || []).filter(function (s) { return s.data && s.data.length; });
    if (!usable.length) {
      var names = (cfg.series || []).map(function (s) { return s.name; }).join(' / ');
      el.innerHTML = '<div class="hint" style="justify-content:center;text-align:center">'
        + '这辆车没有 ' + (names || '这些') + ' 数据（BeamNG 电控里没这项，不是程序坏了）</div>';
      return;
    }
    ChartKit.mount(el, cfg);
    if (missing.length) {
      var tip = document.createElement('div');
      tip.className = 'hint';
      tip.style.cssText = 'justify-content:center;font-size:11.2px;margin-top:4px';
      tip.textContent = '⚠ 这辆车没有 ' + missing.join(' / ') + ' 数据（电控里没这项）';
      el.parentNode.insertBefore(tip, el.nextSibling);
    }
  }
  mount('chart-eng-rpm', {
    series: [{name: '转速', color: '#5B8FB9', width: 2, data: ser.rpm || []}],
    x: {label: '时间 (秒)', fmt: function (v) { return v.toFixed(1) + ' s'; }},
    y1: {label: '转速 (rpm)'}
  });
  mount('chart-eng-temp', {
    series: [
      {name: '水温', color: '#D06A5C', width: 2, data: ser.water || []},
      {name: '油温', color: '#D9A24A', width: 2, data: ser.oil || []}
    ],
    x: {label: '时间 (秒)', fmt: function (v) { return v.toFixed(1) + ' s'; }},
    y1: {label: '温度 (°C)'}
  });
  mount('chart-eng-fuel', {
    series: [
      {name: '空燃比', color: '#4E9E7B', width: 2, data: ser.afr || []},
      {name: '增压', color: '#5B8FB9', width: 2, data: ser.boost || []}
    ],
    x: {label: '时间 (秒)', fmt: function (v) { return v.toFixed(1) + ' s'; }},
    y1: {label: 'AFR / bar'}
  });
};
"""
