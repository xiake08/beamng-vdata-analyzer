# -*- coding: utf-8 -*-
"""两份对比页 —— 选 A/B 两份 CSV，看三档占比、前后轴、RMS 的变化和大白话结论。

数据来源：
- 文件列表：main() 把 OUTDIR 里的 CSV 列表塞进 data["csv_list"]
- 对比结果：真窗口里走 pywebview.api.compare_pair(a, b)（web_ui.Api）
  headless / 静态导出时用 --compare-a/--compare-b 预先算好的 data["compare_seed"]
- 结论文案：beamng_data.compare_verdict()（数据引擎原样复用）
"""

KEY = "compare"
LABEL = "两份对比"
ICON = "compare"
TITLE = "两份对比"
BADGE = ""
SUB = "这一页看什么：改完悬挂之后，和上一版比到底有没有变好。"
ORDER = 7


def build(r, d):
    return d


def _options(d, selected_index=None, selected_name=None):
    items = d.get("csv_list") or []
    out = []
    for i, it in enumerate(items):
        sel = ""
        if selected_index is not None and i == selected_index:
            sel = " selected"
        elif selected_name is not None and it["name"] == selected_name:
            sel = " selected"
        out.append('<option value="%s"%s>%s · %s KB</option>'
                   % (it["path"].replace('"', "&quot;"), sel, it["name"], it["kb"]))
    return "".join(out), len(items)


def render(d):
    from .common import head_html, chip, esc

    opts_a, n = _options(d, selected_name=d.get("file") or "")
    opts_b = _options(d, selected_index=1)[0] if n >= 2 else opts_a
    chips = chip("compare", "共 %d 份数据可选" % n) + chip("clock", "按修改时间排序")
    head = head_html(d["file"], d["file"], TITLE, BADGE, SUB, chips)

    picker = """
    <section class="card cmp-picker">
      <div class="cmp-pick-row">
        <div class="cmp-field cmp-a">
          <label>A · 基准</label>
          <select id="cmp-a">%s</select>
        </div>
        <div class="cmp-vs">VS</div>
        <div class="cmp-field cmp-b">
          <label>B · 对比</label>
          <select id="cmp-b">%s</select>
        </div>
        <button class="cmp-run" id="cmp-run">开始对比</button>
      </div>
      <div class="hint" id="cmp-hint">选两份跑过同一段路的数据：A 是改动前，B 是改动后。</div>
    </section>""" % (opts_a, opts_b)

    body = """
    <section class="page-body">
      %(picker)s
      <div id="cmp-empty" class="empty">
        <div class="empty-ic">%(icon)s</div>
        <div class="empty-title">还没有选好两份数据</div>
        <div class="empty-text">上面选 A（改动前）和 B（改动后），点「开始对比」；
        两份数据最好是在同一条路上、车速接近时跑的。</div>
      </div>
      <div id="cmp-result" class="cmp-result" hidden></div>
    </section>""" % {"picker": picker, "icon": ""}

    return ('<section class="page" data-page="%s" data-title="%s">\n%s%s\n</section>'
            % (KEY, TITLE, head, body))


CSS = """
.cmp-picker{padding:14px 18px;margin:0}
.cmp-pick-row{display:flex;align-items:flex-end;gap:14px;flex-wrap:wrap}
.cmp-field{display:flex;flex-direction:column;gap:6px;min-width:0}
.cmp-field label{font-size:11.5px;color:var(--muted);letter-spacing:.04em}
.cmp-field.cmp-a label{color:var(--blue-3)}
.cmp-field select{height:36px;min-width:340px;max-width:500px;padding:0 12px;border-radius:11px;
  border:1px solid rgba(255,255,255,.9);background:rgba(255,255,255,.75);color:var(--ink);
  font-size:12.6px;font-family:inherit;outline:none;box-shadow:0 8px 20px -16px rgba(50,80,110,.7)}
.cmp-field select:focus{border-color:rgba(91,143,185,.5);box-shadow:0 0 0 3px rgba(91,143,185,.12)}
.cmp-vs{font-size:12px;font-weight:700;color:var(--muted);letter-spacing:.12em;padding-bottom:10px}
.cmp-run{height:36px;margin-left:auto;padding:0 22px;border:0;border-radius:11px;cursor:pointer;
  font-family:inherit;font-size:12.8px;font-weight:600;color:#fff;letter-spacing:.03em;
  background:linear-gradient(150deg,#7FB2D6,#4A7398);
  box-shadow:0 12px 24px -12px rgba(74,115,152,.9);transition:transform .25s var(--ease),box-shadow .25s}
.cmp-run:hover{transform:translateY(-1px);box-shadow:0 16px 30px -12px rgba(74,115,152,.95)}
.cmp-run:disabled{opacity:.55;cursor:default;transform:none}
#cmp-hint{margin-top:10px}
#cmp-hint.cmp-err{color:#B4762F}
.cmp-result{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1.06fr) minmax(0,1fr);
  grid-template-rows:auto minmax(0,1fr);gap:16px}
.cmp-card{display:flex;flex-direction:column;min-height:0;padding:16px 20px}
.cmp-verdict{overflow:auto;padding-right:2px}
.cmp-verdict ul{margin:6px 0 0;padding:0;list-style:none}
.cmp-verdict li{padding:5px 0;font-size:12.2px;line-height:1.55;color:var(--ink-2);
  border-bottom:1px dashed var(--line)}
.cmp-verdict li:last-child{border-bottom:0}
.cmp-verdict li.warn{color:#B4762F}
.cmp-verdict li.good{color:#2F7D5E}
.cmp-verdict li.head{font-weight:600;color:var(--ink);border-bottom:1px solid var(--line)}
.cmp-suggest{margin-top:10px;padding:10px 13px;border-radius:12px;font-size:11.9px;line-height:1.65;
  color:var(--ink-2);background:linear-gradient(90deg,rgba(91,143,185,.10),rgba(91,143,185,.03));
  border:1px solid rgba(91,143,185,.12)}
.cmp-suggest b{color:var(--ink)}
.cmp-band{display:flex;align-items:center;gap:12px;padding:8px 0}
.cmp-band .name{flex:0 0 64px;font-size:12.4px;font-weight:600;color:var(--ink)}
.cmp-band .bars{flex:1;display:flex;flex-direction:column;gap:4px;min-width:0}
.cmp-bar{display:flex;align-items:center;gap:7px;font-size:11px;color:var(--muted)}
.cmp-bar i{display:block;height:8px;border-radius:999px;min-width:2px}
.cmp-bar .tag{flex:0 0 11px;font-weight:700;color:var(--muted)}
.cmp-delta{flex:0 0 72px;text-align:right;font-variant-numeric:tabular-nums;font-size:12.4px;font-weight:600}
.up{color:#C0662F}.down{color:#2F7D5E}.flat{color:var(--muted)}
.cmp-table{display:flex;flex-direction:column;margin-top:2px;overflow:auto;padding-right:2px}
.cmp-tr{display:grid;grid-template-columns:minmax(0,1.15fr) 88px 88px 74px;gap:8px;align-items:baseline;
  padding:5px 0;border-bottom:1px dashed var(--line);font-size:11.8px}
.cmp-tr:last-child{border-bottom:0}
.cmp-tr.hd{color:var(--muted);font-size:11.2px;letter-spacing:.03em;border-bottom:1px solid var(--line)}
.cmp-tr .v{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink);font-weight:500}
.cmp-tr .d{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.cmp-file{margin-top:2px;overflow:auto}
.cmp-file .row{display:flex;justify-content:space-between;gap:10px;padding:5.5px 0;font-size:12px;
  border-bottom:1px dashed var(--line)}
.cmp-file .row:last-child{border-bottom:0}
.cmp-file .row span{color:var(--muted)}
.cmp-file .row b{font-weight:500;color:var(--ink);max-width:66%;text-align:right;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cmp-file .tagA{color:var(--blue-3)}.cmp-file .tagB{color:#B4762F}
"""

JS = """
window.PAGE_INIT = window.PAGE_INIT || {};
window.PAGE_INIT.compare = function (root, DATA) {
  var $ = function (sel) { return root.querySelector(sel); };
  var selA = $('#cmp-a'), selB = $('#cmp-b'), runBtn = $('#cmp-run'),
      result = $('#cmp-result'), empty = $('#cmp-empty'), hint = $('#cmp-hint');

  function bridgeReady() {
    return !!(window.pywebview && window.pywebview.api && window.pywebview.api.compare_pair);
  }

  function esc(s) {
    return String(s === undefined || s === null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function n(v, dp) {
    if (v === undefined || v === null || isNaN(v)) return '–';
    return Number(v).toFixed(dp === undefined ? 1 : dp);
  }
  function worst(x) { return x.worst_m >= 1 ? n(x.worst_m, 0) + ' m 处' : '起点那段'; }
  function tone(delta, lowerBetter) {
    if (Math.abs(delta) < 0.05 || !lowerBetter) return 'flat';
    return delta < 0 ? 'down' : 'up';
  }
  function row(label, a, b, opts) {
    opts = opts || {};
    var out = '<div class="cmp-tr"><div>' + esc(label) + '</div>' +
      '<div class="v">' + n(a, opts.dp) + '</div><div class="v">' + n(b, opts.dp) + '</div>';
    if (typeof a === 'number' && typeof b === 'number') {
      if (opts.pctDiff) {
        var base = Math.abs(a) > 1e-9 ? a : 1e-9;
        var dd = (b - a) / base * 100;
        out += '<div class="d ' + tone(dd, opts.lowerBetter) + '">' +
          (dd > 0 ? '+' : '') + n(dd, 0) + '%</div>';
      } else {
        var d2 = b - a;
        out += '<div class="d ' + tone(d2, opts.lowerBetter) + '">' +
          (d2 > 0 ? '+' : '') + n(d2, opts.dp) + '</div>';
      }
    } else {
      out += '<div class="d flat">—</div>';
    }
    return out + '</div>';
  }

  function bandRows(a, b) {
    var out = '';
    (a.bands || []).forEach(function (band, i) {
      var bb = (b.bands || [])[i] || { pct: 0 };
      var da = bb.pct - band.pct;
      out += '<div class="cmp-band"><div class="name">' + esc(band.name) + '</div>' +
        '<div class="bars">' +
        '<div class="cmp-bar"><span class="tag">A</span><i style="width:' +
        Math.max(1, band.pct * 1.6) + '%;background:linear-gradient(90deg,' + band.c1 + ',' + band.c2 +
        ')"></i><span>' + n(band.pct, 0) + '%</span></div>' +
        '<div class="cmp-bar"><span class="tag">B</span><i style="width:' +
        Math.max(1, bb.pct * 1.6) + '%;background:#C9B08B"></i><span>' + n(bb.pct, 0) + '%</span></div>' +
        '</div>' +
        '<div class="cmp-delta flat">' + (da > 0 ? '+' : '') + n(da, 0) + ' pt</div></div>';
    });
    return out;
  }

  function syncSelects(res) {
    var items = DATA.csv_list || [];
    function find(name) {
      for (var i = 0; i < items.length; i++) { if (items[i].name === name) return items[i].path; }
      return null;
    }
    var pa = res.a && find(res.a.file), pb = res.b && find(res.b.file);
    if (pa) selA.value = pa;
    if (pb) selB.value = pb;
  }

  function render(res) {
    var a = res.a, b = res.b;
    var verdict = (res.verdict || []).map(function (line, i) {
      var cls = '';
      if (i < 2) cls = ' head';
      else if (line.indexOf('⚠') >= 0 || line.indexOf('❌') >= 0) cls = ' warn';
      else if (line.indexOf('✔') >= 0) cls = ' good';
      return '<li class="' + cls + '">' + esc(line) + '</li>';
    }).join('');
    var suggest = (res.suggest || []).map(function (s) { return '· ' + esc(s); }).join('<br>');

    var rows = '<div class="cmp-tr hd"><div>指标</div><div class="v">A</div><div class="v">B</div>' +
      '<div class="d">变化</div></div>';
    rows += row('整车 RMS (m/s)', a.rms, b.rms, { dp: 3, pctDiff: true, lowerBetter: true });
    rows += row('前轴 RMS (m/s)', a.rms_f, b.rms_f, { dp: 3, pctDiff: true, lowerBetter: true });
    rows += row('后轴 RMS (m/s)', a.rms_r, b.rms_r, { dp: 3, pctDiff: true, lowerBetter: true });
    rows += row('前轴轮荷 σ (N)', a.sig_f, b.sig_f, { dp: 0, pctDiff: true, lowerBetter: true });
    rows += row('后轴轮荷 σ (N)', a.sig_r, b.sig_r, { dp: 0, pctDiff: true, lowerBetter: true });
    rows += row('前轴占比 (%)', a.front_share, b.front_share, { dp: 1 });
    rows += row('最颠段 RMS (m/s)', a.worst_rms, b.worst_rms, { dp: 3, pctDiff: true, lowerBetter: true });
    rows += '<div class="cmp-tr"><div>最颠位置</div><div class="v">' + esc(worst(a)) +
      '</div><div class="v">' + esc(worst(b)) + '</div><div class="d flat">—</div></div>';
    rows += row('最大离地 (%)', a.lift_max, b.lift_max, { dp: 1, lowerBetter: true });
    rows += row('平均车速 (km/h)', a.v_avg_kmh, b.v_avg_kmh, { dp: 0 });

    var info = '';
    [['A', a, 'tagA'], ['B', b, 'tagB']].forEach(function (t) {
      var tag = t[0], x = t[1], cls = t[2];
      info += '<div class="row"><span class="' + cls + '">' + tag + ' · 文件</span><b title="' +
        esc(x.file) + '">' + esc(x.file) + '</b></div>';
      info += '<div class="row"><span class="' + cls + '">' + tag + ' · 车辆/配置</span><b>' +
        esc(x.vehicle || '—') + ' / ' + esc(x.config || '—') + '</b></div>';
      info += '<div class="row"><span class="' + cls + '">' + tag + ' · 里程/时长</span><b>' +
        n(x.dist_m, 0) + ' m · ' + n(x.dur_s, 0) + ' s</b></div>';
      info += '<div class="row"><span class="' + cls + '">' + tag + ' · 结论</span><b>' +
        esc(x.verdict) + '（RMS ' + n(x.rms, 3) + '）</b></div>';
    });

    result.innerHTML =
      '<article class="card cmp-card"><div class="panel-head"><div><h2>结论</h2>' +
      '<p>beamng_data.compare_verdict() 原样输出</p></div></div>' +
      '<div class="cmp-verdict"><ul>' + verdict + '</ul>' +
      (suggest ? '<div class="cmp-suggest"><b>调校建议</b><br>' + suggest + '</div>' : '') +
      '</div></article>' +
      '<article class="card cmp-card"><div class="panel-head"><div><h2>三档占比</h2>' +
      '<p>A 用原色，B 用米色对比</p></div></div>' + bandRows(a, b) + '</article>' +
      '<article class="card cmp-card"><div class="panel-head"><div><h2>关键指标</h2>' +
      '<p>变化 = B 相对 A；绿色是变好，橙色是变差</p></div></div>' +
      '<div class="cmp-table">' + rows + '</div></article>' +
      '<article class="card cmp-card"><div class="panel-head"><div><h2>这两份数据</h2>' +
      '<p>确认一下是不是同一条路、车速接近</p></div></div>' +
      '<div class="cmp-file">' + info + '</div></article>';
    result.hidden = false;
    empty.hidden = true;
  }

  function fail(msg) {
    empty.hidden = false;
    result.hidden = true;
    hint.textContent = msg;
    hint.classList.add('cmp-err');
  }

  runBtn.addEventListener('click', function () {
    var a = selA.value, b = selB.value;
    if (!a || !b) { fail('先选两份数据'); return; }
    if (a === b) { fail('A 和 B 选的是同一份，换一个再对比'); return; }
    if (!bridgeReady()) {
      fail('当前是静态/无头预览，不能读 CSV；开真窗口，或加 --compare-a/--compare-b 参数。');
      if (window.__toast) window.__toast('静态预览不能对比，请开真窗口');
      return;
    }
    runBtn.disabled = true;
    hint.textContent = '正在分析两份 CSV…';
    window.pywebview.api.compare_pair(a, b).then(function (res) {
      runBtn.disabled = false;
      if (!res || !res.ok) { fail('对比失败：' + ((res && res.error) || '未知错误')); return; }
      hint.textContent = '对比完成：A ' + res.a.file + '  ↔  B ' + res.b.file;
      render(res);
    }).catch(function (e) {
      runBtn.disabled = false;
      fail('对比失败：' + e);
    });
  });

  if (DATA.compare_seed && DATA.compare_seed.ok) {
    syncSelects(DATA.compare_seed);
    render(DATA.compare_seed);
    hint.textContent = '已载入预置对比（--compare-a / --compare-b）';
    if (bridgeReady()) hint.textContent += '；也可以换两份重新对比';
  } else if (!bridgeReady()) {
    hint.textContent = '静态预览：选好 A/B 也不会真的分析，请开真窗口或用 --compare-a/--compare-b。';
  }
  window.addEventListener('pywebviewready', function () {
    if (!DATA.compare_seed) {
      hint.textContent = '选两份跑过同一段路的数据：A 是改动前，B 是改动后。';
    }
  });
};
"""
