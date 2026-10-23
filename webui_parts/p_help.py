# -*- coding: utf-8 -*-
"""使用说明页（左下角 ?，不属于页面导航）—— 页面速查 + 图表操作 + 数据口径。"""

KEY = "help"
LABEL = "使用说明"
ICON = "help"
TITLE = "使用说明"
BADGE = ""
SUB = "这一页看什么：九个数据页分别看什么、图表怎么操作、里面的数字是怎么算出来的。"
ORDER = 91
UTILITY = True          # 左下角工具按钮，不出现在左侧页面导航里


def build(r, d):
    return d


PAGE_GUIDE = [
    ("bars", "减振器分布", "三档颠簸占比（细碎 / 常见 / 大冲击）+ 4 组详细分布 + 自动调校建议"),
    ("route", "赛道剖面", "高程与车速随里程的曲线，每 500 m 一段的颠簸 RMS，最颠的一段在哪"),
    ("pulse", "动力曲线", "转速-功率/扭矩曲线、加速度-车速曲线，以及质量、0-100 等关键数"),
    ("car", "四轮载荷", "四个轮子各扛多少、前后左右配重、滑移率、离地比例、轮荷波动 σ"),
    ("wave", "悬挂波形", "四角减振器速度随里程的波形；可切前/后轴，点图例只看单个轮"),
    ("pedal", "踏板", "油门/刹车开度曲线和踩踏统计（这趟跑得有多激烈）"),
    ("compare", "两份对比", "选 A/B 两份 CSV，看改完悬挂后到底有没有变好"),
    ("map3d", "3D 赛道", "整条路线按真实 x/y/z 立起来转着看，颜色可按高程/车速/颠簸/踏板切"),
    ("doc", "数据总结", "整份数据的大白话结论 + 老版完整文本报告（可一键复制）"),
]


def render(d):
    from .common import IC, chip, esc, head_html

    rows = "".join(
        '<div class="help-page-row"><span class="help-ic">%s</span>'
        '<span class="help-name">%s</span><span class="help-desc">%s</span></div>'
        % (IC.get(icon, ""), esc(name), esc(desc))
        for icon, name, desc in PAGE_GUIDE)

    chips = chip("help", "9 个数据页") + chip("info", "数据全部来自 analyze()")
    head = head_html(d["file"], d["file"], TITLE, BADGE, SUB, chips)

    body = """
    <section class="page-body">
      <section class="grid">
        <article class="card page-card">
          <div class="panel-head"><div><h2>页面速查</h2><p>左侧图标从上到下</p></div></div>
          <div class="help-pages">%(rows)s</div>
        </article>
        <aside class="side">
          <article class="card">
            <div class="panel-head"><div><h2>图表怎么操作</h2><p>剖面 / 动力 / 波形 / 踏板 这几页</p></div></div>
            <dl class="kv">
              <div class="kv-row"><dt>滚轮</dt><dd>以鼠标位置为中心缩放</dd></div>
              <div class="kv-row"><dt>左键拖拽</dt><dd>左右平移</dd></div>
              <div class="kv-row"><dt>双击</dt><dd>复位到全程</dd></div>
              <div class="kv-row"><dt>悬停</dt><dd>十字线 + 该点数值</dd></div>
              <div class="kv-row"><dt>点图例</dt><dd>只看该轮（波形页；再点恢复四轮）</dd></div>
            </dl>
          </article>
          <article class="card">
            <div class="panel-head"><div><h2>数字怎么来的</h2><p>数据引擎算的，界面不写死</p></div></div>
            <div class="tip-text" style="line-height:1.75">
              · 读 CSV + 同名 .txt 摘要，采样 10 Hz，全部由 <b>beamng_data.analyze()</b> 计算。<br>
              · 三档占比按四个减振器的工作速度分桶统计；<br>
              · <b>RMS</b> 是减振器速度均方根，受安装几何影响，前后轴不要直接比大小；<br>
              · <b>σ</b>（轮荷标准差）几何无关，前后轴忙不忙看它。
            </div>
          </article>
          <article class="card">
            <div class="panel-head"><div><h2>启动游戏 / 换数据 / 装 mod</h2><p>都在界面里</p></div></div>
            <div class="tip-text" style="line-height:1.75">
              · 右上角「▶ 启动游戏」：走 Steam 启动 BeamNG.drive（直接拉 exe 会新建空档案）；<br>
              · 新数据自动识别：游戏把 roadProfile_*.csv 写进用户目录后会自动搬进数据目录并改名；正在看最新一份时自动刷新，在看历史数据只弹提示；<br>
              · 页头 chip 每 3 秒刷新：`● 正在记录 1.23 km / 734 点` / `游戏在跑 · 等待进入地图` / `游戏没开 · 上次 2.12 km / 734 点`（进程检测 + 抓包状态文件，mod 没写状态时也能知道游戏起没起）；<br>
              · 右上角「换数据」：列出数据目录里的 CSV，也能选外部文件，换完整页自动重载；每行右边「✕」可以删掉不要的抓包（CSV + 同名 .txt，会二次确认；删当前这份会自动换到下一份）；<br>
              · 左下角 ⚙ 设置：改游戏/用户/输出目录，自动探测；<br>
              · 同一页里有「一键安装 / 修复」，把抓包扩展、自动加载脚本、面板 mod 装进游戏目录，重启游戏生效。
            </div>
          </article>
        </aside>
      </section>
    </section>""" % {"rows": rows}
    return ('<section class="page" data-page="%s" data-title="%s">\n%s%s\n</section>'
            % (KEY, TITLE, head, body))


CSS = """
.help-pages{display:flex;flex-direction:column;gap:2px;margin-top:2px}
.help-page-row{display:flex;align-items:center;gap:12px;padding:9px 4px;border-bottom:1px dashed var(--line)}
.help-page-row:last-child{border-bottom:0}
.help-ic .ic{width:18px;height:18px;color:var(--blue)}
.help-name{flex:0 0 82px;font-size:13px;font-weight:600;color:var(--ink)}
.help-desc{font-size:12.2px;line-height:1.55;color:var(--ink-2)}
"""

JS = ""
