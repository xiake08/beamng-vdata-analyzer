# webui_parts 页面模块 · 接口说明（给负责各页的人）

目标：把本项目的界面从「只有第①页」补成多页完整版。
**你只负责自己那一页的 `webui_parts/p_<key>.py`**，其他文件不要动。

---

## 0. 环境 / 命令

解释器（所有脚本都用它）：

```
python.exe
```

工作目录：本项目根目录

快速预览某一页（不开窗口，Edge 无头渲染，最常用）：

```
python web_ui.py --page profile --shot webui_parts\shot_profile.png --headless
```

开真窗口看过一次（会弹 pywebview 窗口，3 秒后自动截图关闭）：

```
python web_ui.py --page profile --shot webui_parts\shot_profile.png
```

只导 HTML 用浏览器看（调试 DOM/CSS）：

```
python web_ui.py --page profile --html webui_parts\preview_profile.html
```

控制台是 GBK：**Python 里不要 print 中文/emoji**。改完用上面的 `--shot` 验证（它只打印 ASCII）。

---

## 1. 你的文件 & 接口

文件：`webui_parts/p_<key>.py`（UTF-8，纯字符串，不要引入外部网络资源/字体/图片）

```python
KEY = "profile"      # 唯一 key，别改
LABEL = "赛道剖面"     # 左侧导航文字
ICON = "route"       # common.IC 里的图标 key
TITLE = "赛道剖面"     # 页面大标题
BADGE = ""           # 标题旁小标签，可留空；如「原厂悬挂」
SUB = "这一页看什么：……"
ORDER = 2            # 导航顺序：2 profile / 3 dyno / 4 wheels / 5 wave / 6 pedals / 7 compare

def build(r, d):
    """r = analyze() 原始结果，d = 各页共享的数据 dict。
    往 d 里补本页字段（必须能被 json.dumps 序列化），不要做 HTML。"""

def render(d):
    """返回完整的一页 HTML，最外层必须是：
    <section class="page" data-page="profile" data-title="赛道剖面"> ... </section>
    页面内部结构随意，但请复用第①页的视觉语言（见第 3 节）。"""

CSS = """/* 本页专属 CSS，会拼进页面 <style> 末尾 */"""

JS = """// 本页脚本：第一次切到这一页时调用一次
window.PAGE_INIT = window.PAGE_INIT || {};
window.PAGE_INIT.profile = function (root, DATA) {
  // root = 本页 <section>；DATA = 页面数据（含 build() 加的字段）
};"""
```

框架保证：
- 页面默认是隐藏的（`.page` 没有 `active`）；点左侧导航切过去时加 `active`，**第一次显示时才调用 `PAGE_INIT`**。
- 所以 `PAGE_INIT` 里可以放心量尺寸、初始化 ChartKit。
- 页面切走再回来不会重复 init；ChartKit 自己用 ResizeObserver 处理重新显示时重绘。
- 每一页自己有 `<header class="head">`（标题区），用 `common.head_html(...)` 生成即可，不要自己手搓。
  **`head_html` 会自动在右上角带「游戏状态 chip」+「▶ 启动游戏」（id=launch-game，走 Steam 协议）+「换数据」（id=open-data）**，
  由框架统一处理（chip 每 3 秒由 `api.poll()` 刷新），你不用管它们。
- `d["csv_list"]` = 数据目录里的 CSV 列表（换数据弹层用），页面里不要写死。
- 新数据自动识别在框架里做：`api.poll()` 每 3 秒把游戏用户目录里的 `roadProfile_*.csv` 搬进数据目录；
  正在看最新一份时自动重载，看历史数据只弹提示 —— 页面模块不需要管。
- 需要文件选择 / 路径保存 / 装 mod 等桌面能力时，用 `window.pywebview.api.*`（`open_csv` / `pick_csv_file` /
  `pick_folder` / `pick_exe` / `config_info` / `save_config` / `install_mod` / `compare_pair` / `list_csvs` /
  `launch_game` / `poll`），静态预览里这些 API 不存在，要有降级提示（参考 `p_compare.py` / `p_settings.py`）。

---

## 2. 数据（全部来自 `analyze()`，禁止写死数字）

共享字段（`d` 里已有，直接 `d["xxx"]`；对应 Python 里 `r[...]`）：

| 字段 | 含义 |
|---|---|
| `d["file"]` | CSV 文件名 |
| `d["profile_pts"]` | `[[里程 m, 高程 z, 车速 km/h, 油门 0-1, 刹车 0-1], ...]`（已 decimate，~318 点） |
| `d["sv_pts"]` | `[[里程, FL减振器速度, FR, RL, RR], ...]`（m/s，正负=压缩/回弹） |
| `d["segments"]` | `[{"d0": 段起点m, "n": 点数, "rms": 该段RMS m/s, "v": 该段均速 km/h}, ...]`（按位置排序，每段 500m） |
| `d["z_min"] / d["z_max"]` | 高程范围 m |
| `d["climb"]` | 累计爬升 m；`d["grade"]` 最大坡度（小数，0.116 = 11.6%） |
| `d["dist_m"]`, `d["dur_s"]`, `d["points"]` | 里程 / 时长 / 采样点数 |
| `d["v_avg_kmh"]`, `d["v_max_kmh"]` | 均速 / 最高车速 |
| `d["rms_f"]`, `d["rms_r"]`, `d["rms"]` | 前轴/后轴/整车 减振器速度 RMS |
| `d["sig_f"]`, `d["sig_r"]` | 前/后轴轮荷标准差 σ（前后对比只用这个，别用 RMS） |
| `d["bands"]` | 三档占比 `[{name,tag,range,pct,c1,c2,glow}]` |
| `d["axis_text"]`, `d["axis_pct"]`, `d["front_share"]` | 前后轴忙碌文案 / 百分比 / 前轴占比 |
| `d["worst_m"]`, `d["worst_rms"]`, `d["worst_pos"]` | 最颠的一段起点 m / 该段 RMS / 位置百分比 |
| `d["lift_max"]` | 最大离地比例 % |
| `d["stock"]` | 是否原厂悬挂（bool） |
| `d["has_dyno"]`, `d["has_pedal"]` | 本份数据有没有动力/踏板数据 |

`analyze()` 里还有的原始数据（在 `build()` 的 `r` 里取，自己塞进 `d`）：

```
r["meta"] = {"veh","cfg","susp","level"}
r["dyno"] = [(rpm, 扭矩 Nm, 功率 kW), ...]         # 27 档左右；没有全油门段时空
r["mass"] = 整车质量 kg（用四轮载荷算的）
r["model"] = 车型简称（"GBK_dmi"）
r["power"] = [(lo, hi, avg_acc_g, n), ...]         # 7 个车速档的平均加速度 g
r["power_curve"] = [(km/h, 加速度 g), ...]         # 每 5 km/h 细曲线（可能为空）
r["acc_max"] = 最大纵向加速度 g；r["acc_min"] = 最大减速度 g（负）
r["t100"] = 0-100 最快秒数（可能 None）
r["wheels"] = {tag: {"ld": 平均载荷 N, "ld_max": 最大载荷, "sp": 平均轮速 m/s}}
r["load"] / r["lmin"] / r["lmax"] / r["air"] / r["loadsig"] = {FL/FR/RL/RR: 值}
    load 平均载荷 N；lmin/lmax 载荷范围；air 离地比例 %；loadsig 轮荷标准差 σ
r["load_pct"] = {tag: 载荷占比 %}；r["wb_balance"] = {"front":前%, "left":左%, "cross":对角%}
r["slip_pct"] = {tag: 滑移率 %}（>0 打滑，<0 抱死）
r["thr_on"/"brk_on"] = 油门/刹车踩下时间 %；r["thr_avg"/"brk_avg"] = 平均开度 0-1
r["align"], r["align_geo"] = 静态定位参数（可能为空 dict，页面别强依赖）
r["path"] = 完整路径
```

参考数值：可以先读 `webui_parts/_data.json`（当前 CSV 的完整 analyze 结果，JSON 化）和老程序的输出，
再拿界面上的数字对一遍。**别把 _data.json 的数值写死进代码**，它只是参考。

---

## 3. 视觉规范（第①页有的东西，直接复用，不要另起一套）

设计变量（:root 已定义）：`--blue #5B8FB9` `--blue-2 #8FBEDD` `--blue-3 #3E6B92`
`--ink #1F2E3C` `--ink-2 #4B6072` `--muted #8496A7` `--card rgba(255,255,255,.72)`
`--shadow` `--ease`。字体已在 body 设好，页面里不要改。

现有 class（都是第①页在用的）：
- 卡片：`<article class="card ...">`（毛玻璃 + 圆角 16 + hover 抬升）
- 卡片标题：`.panel-head` > `<h2>` + `<p>`
- 小标签：`.mini-chip`（浅蓝），`.badge`（大标题旁）
- 右上角 chip：`common.chip(icon, text)`（渲染成 `.chip`）
- 页头：`common.head_html(file_stem, file_full, TITLE, BADGE, SUB, chips_html)`
- 键值行：`.kv` > `.kv-row` > `<dt>/<dd>`
- 统计卡：`.stat` / `.stat-label` / `.stat-value` / `.stat-foot`（首页三张卡那种）
- 新增的通用：`.page-card`（带 padding 的卡片）、`.chart-card` + `.chart-head`、
  `.chart`（ChartKit 容器，flex:1 需父级有高度）、`.legend`、`.empty`（空状态）、`.hint`
- 布局：`.grid` = 左大右窄两栏（`1fr / 388px`，窄屏自动堆叠）；`.page-body` = 纵向 flex 容器

建议每页结构：

```html
<section class="page" data-page="KEY" data-title="TITLE">
  [head_html]
  <section class="page-body">
    <section class="grid">      <!-- 或别的布局 -->
      <article class="card chart-card">…</article>
      <aside class="side"> <article class="card">…</article> … </aside>
    </section>
  </section>
</section>
```

页面高度是固定的（窗口 1600×950，内容区约 1386×820 CSS px，无滚动），
卡片要 `min-height:0` + `flex:1` 才能把图表撑开。

---

## 4. ChartKit（折线图引擎，已内置）

脚本已全局可用：`window.ChartKit.mount(el, opts)`，canvas 绘制，自带：
滚轮缩放（光标为锚点）、左键拖拽平移、双击复位、悬停十字线 + 数值气泡。

```js
var chart = ChartKit.mount(document.getElementById('chart-xxx'), {
  series: [
    {name:'高程', color:'#5B8FB9', data:[[d,z],...], fill:true,
     fillTop:'rgba(91,143,185,.28)', fillBottom:'rgba(91,143,185,0)', width:2},
    {name:'车速', color:'#D9A24A', data:[[d,v*3.6],...], axis:'y2', width:1.6, dash:true}
  ],
  x:  {label:'里程 (m)', fmt:function(v){ return v.toFixed(0)+' m'; }},
  y1: {label:'高程 (m)'},
  y2: {label:'车速 (km/h)'},     // 可选；没有就单轴
  gap: 0,                        // 可选：数据允许的最大 x 间隔，超过则断线
  hover: true                    // 默认 true，false 可关掉气泡
});
// chart.reset() 复位；chart.destroy() 销毁；chart.resize()
```

容器 `<div class="chart" id="chart-xxx"></div>` 需要有确定高度（`.chart-card` 里 flex:1 即可）。
多轴时左右两侧刻度颜色都是灰的，图例自己用 `common.legend([(名字, 颜色, 是否虚线), ...])` 放在卡片头部。

---

## 5. 数据引擎（`beamng_data.py`）与旧界面

- 老 tkinter 界面已于 **2026-10-21 删除**（备份 zip 在 `D:\Deepseek Harness\_legacy_tkinter_backup_20261021.zip`），
  只留下数据层 `beamng_data.py`（纯 Python，无 GUI 依赖）：`analyze()`、`conclusions()`、`suggestions()`、
  `compare_verdict()`、`fmt_report()`、`decimate_pts()`、`read_rows()`、`install_to_game()` 等。
- 老版的绘制代码（`_draw_profile` / `_draw_dyno` / `_draw_wheels` / `_draw_wave` / `_draw_pedals` / `_draw_3d`）
  已经不存在了；页面长什么样以现有页面 + 本 SPEC 为准。
- 数据口径不能变（比如轮荷 σ 前后对比、三档占比的算法）——这些都在 `beamng_data.analyze()` 里，不要重写。
- 有新页面想要共用的小工具（格式化函数等），可以先在 `common.py` 里加；改公共文件前先在团队任务里说一声。

---

## 6. 验收标准

1. `python web_ui.py --page <key> --shot <png> --headless` 退出码 0，图里能看到真数据。
2. 页面上所有数字都能在 `_data.json` / 老程序输出里对上（截图和数字一起交给 Lead）。
3. 没有数据的情况（比如没有 dyno / 没有踏板）要有空状态，不能崩、不能空白。
4. 1600×950 下来满屏不滚动、不溢出；把窗口缩到 1120×720 时不互相压字（`--shot` 只截 1600×950，可自己用 `--html` + Edge 改尺寸看）。
5. 不新增外部依赖、不发网络请求、不写死中文数字答案。

## 7. 红线

- 不要动 `web_ui.py`、`webui_parts/common.py`、`webui_parts/chartkit.js`、`webui_parts/__init__.py`、别人的 `p_*.py`。
- 不要动 `beamng_data.py`（数据引擎）/ 抓包逻辑 / 安装器。
- `build()` 里塞进 `d` 的必须是 JSON 可序列化类型（list/dict/str/int/float/bool/None）。
- 截图/日志自己留好，汇报时给路径。
