# -*- coding: utf-8 -*-
"""数据总结页 —— 老版左下角的「结论（大白话）」+「完整文本报告」，原样搬过来。

数据来源：
- conclusions(r)：把统计翻译成人话（含最后的调校建议）
- fmt_report(r)：老版完整文本报告（分档分布 / 四轮负荷 / 最颠路段……）
两个函数都来自数据引擎 beamng_data.py，原样调用，不重写。
"""

KEY = "summary"
LABEL = "数据总结"
ICON = "doc"
TITLE = "数据总结"
BADGE = ""
SUB = "这一页看什么：整份数据翻译成大白话，外加老版那份可以直接复制给懂行的人看的完整报告。"
ORDER = 9


def build(r, d):
    """把 analysis 的结论和文本报告塞进页面数据（都是纯字符串，JSON 稳）。"""
    concl, report = [], ""
    try:
        import beamng_data as T               # 数据引擎（纯 Python）
        concl = list(T.conclusions(r) or [])
        report = T.fmt_report(r) or ""
    except Exception:                          # noqa: BLE001  单页不能拖垮整个程序
        pass
    d["summary_conclusions"] = [str(x) for x in concl]
    d["summary_report"] = str(report)
    return d


def render(d):
    from .common import chip, esc, head_html, fmt_dist, fmt_dur

    concl = d.get("summary_conclusions") or []
    report = d.get("summary_report") or ""

    chips = (chip("doc", "%d 条结论" % len([x for x in concl if x.strip()]))
             + chip("compare", "可直接复制"))
    head = head_html(d["file"], d["file"], TITLE, BADGE, SUB, chips)

    # 结论：→ 开头的缩进行单独缩进；空行当分隔
    items = []
    for line in concl:
        raw = line.rstrip()
        if not raw.strip():
            items.append('<li class="sum-gap"></li>')
            continue
        stripped = raw.strip()
        # meta 里的空配置显示成「默认配置」，别让 [] 露到界面上
        stripped = stripped.replace("配置：[]", "配置：默认配置").replace("配置：{}", "配置：默认配置")
        cls = "sum-arrow" if stripped.startswith("→") else ""
        items.append('<li class="%s">%s</li>' % (cls, esc(stripped)))
    concl_html = "".join(items)

    if not report:
        report_html = '<div class="empty-text" style="padding:16px 0">这份数据没有文本报告</div>'
    else:
        report_html = '<pre class="sum-report-pre" id="sum-report-pre">%s</pre>' % esc(report)

    body = """
    <section class="page-body">
      <section class="grid">
        <article class="card page-card sum-report-card">
          <div class="panel-head">
            <div><h2>完整文本报告</h2><p>beamng_data.fmt_report() 原样输出 · 可直接复制</p></div>
            <button class="sum-copy" id="sum-copy" type="button">复制报告</button>
          </div>
          %(report)s
        </article>
        <aside class="side">
          <article class="card sum-concl-card">
            <div class="panel-head">
              <div><h2>结论（大白话）</h2><p>beamng_data.conclusions() · 改完车再跑一段对比看变化</p></div>
            </div>
            <ul class="sum-list" id="sum-concl">%(concl)s</ul>
            <div class="sum-meta">%(meta)s</div>
          </article>
        </aside>
      </section>
    </section>""" % {
        "report": report_html,
        "concl": concl_html,
        "meta": "文件：%s<br>%s · %s · %s 点 · 均速 %.0f km/h" % (
            esc(d["file"]), fmt_dist(d["dist_m"]), fmt_dur(d["dur_s"]),
            "{:,}".format(d["points"]), d["v_avg_kmh"]),
    }
    return ('<section class="page" data-page="%s" data-title="%s">\n%s%s\n</section>'
            % (KEY, TITLE, head, body))


CSS = """
.sum-report-card{min-height:0}
.sum-report-pre{flex:1;min-height:0;overflow:auto;margin:6px 0 0;padding:14px 16px;border-radius:12px;
  background:rgba(255,255,255,.55);border:1px solid rgba(91,143,185,.14);
  font-family:"Consolas","Microsoft YaHei UI",monospace;font-size:11.8px;line-height:1.72;
  color:var(--ink-2);white-space:pre;letter-spacing:0}
.sum-copy{height:30px;padding:0 14px;border:0;border-radius:9px;cursor:pointer;font-family:inherit;
  font-size:11.8px;font-weight:600;color:var(--blue-3);background:rgba(91,143,185,.12);
  white-space:nowrap;transition:background .2s}
.sum-copy:hover{background:rgba(91,143,185,.2)}
.sum-concl-card{min-height:0}
.sum-list{list-style:none;margin:6px 0 0;padding:0;overflow:auto;flex:1;min-height:0}
.sum-list li{padding:5px 0;font-size:12.2px;line-height:1.6;color:var(--ink-2);
  border-bottom:1px dashed var(--line)}
.sum-list li:last-child{border-bottom:0}
.sum-list li.sum-arrow{padding:3px 0 6px 14px;color:var(--blue-3);border-bottom:0;font-size:11.8px}
.sum-list li.sum-gap{height:10px;border-bottom:0;padding:0}
.sum-meta{margin-top:10px;padding-top:10px;border-top:1px solid var(--line);
  font-size:11.2px;line-height:1.7;color:var(--muted)}
"""

JS = """
window.PAGE_INIT = window.PAGE_INIT || {};
window.PAGE_INIT.summary = function (root, DATA) {
  var btn = root.querySelector('#sum-copy');
  var pre = root.querySelector('#sum-report-pre');
  function toast(m) { if (window.__toast) window.__toast(m); }
  if (!btn || !pre) return;
  btn.addEventListener('click', function () {
    var text = pre.textContent || '';
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;opacity:0;left:-999px';
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      toast(ok ? '报告已复制' : '复制失败，请手动选中复制');
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { toast('报告已复制'); }, fallback);
    } else {
      fallback();
    }
  });
};
"""
