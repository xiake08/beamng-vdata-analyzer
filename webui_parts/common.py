# -*- coding: utf-8 -*-
"""webui_parts 共用小工具（不 import web_ui，避免循环导入）。

- IC：内联 SVG 图标（web_ui.py 也直接从这里 import）
- esc / fmt_dist / fmt_dur：HTML 转义 + 距离/时长格式化
- head_html()：每一页顶部的标题区（crumb + h1 + badge + sub + 右侧 chips）
- chip()：右上角小 chip
- WHEEL_COLORS / AXIS_COLORS：四轮/轴向统一配色
"""

import html as _html


# ── 图标（24x24 viewBox，stroke 用 currentColor）──────────────────────────
IC = {
    "pin": '<svg class="ic" viewBox="0 0 24 24"><path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z"/>'
           '<circle cx="12" cy="10" r="2.4"/></svg>',
    "route": '<svg class="ic" viewBox="0 0 24 24"><path d="M4 18c3.2 0 3.6-6 7-6s3.8-6 7-6"/>'
             '<circle cx="4" cy="18" r="1.6"/><circle cx="18" cy="6" r="1.6"/></svg>',
    "pulse": '<svg class="ic" viewBox="0 0 24 24"><path d="M3 13h3.5l2-6 3.6 12 2.4-6H21"/></svg>',
    "wave": '<svg class="ic" viewBox="0 0 24 24"><path d="M3 12.5h2.6l2-5.4 3.4 10.4 2.4-6.6 1.6 3.4h5.4"/></svg>',
    "swap": '<svg class="ic" viewBox="0 0 24 24"><path d="M4 9h13M13 5l4 4-4 4"/>'
            '<path d="M20 15H7M11 11l-4 4 4 4"/></svg>',
    "bars": '<svg class="ic" viewBox="0 0 24 24"><path d="M5 19v-7M12 19V5M19 19v-4.5"/></svg>',
    "sliders": '<svg class="ic" viewBox="0 0 24 24"><path d="M4 7h9M18 7h2M4 17h3M12 17h8"/>'
               '<circle cx="15.5" cy="7" r="2.2"/><circle cx="9.5" cy="17" r="2.2"/></svg>',
    "car": '<svg class="ic" viewBox="0 0 24 24"><path d="M4 16h16M6.2 16l1.4-5.2A2 2 0 0 1 9.5 9.3h5a2 2 0 0 1 1.9 1.5'
           'L17.8 16"/><circle cx="8" cy="18.2" r="1.5"/><circle cx="16" cy="18.2" r="1.5"/></svg>',
    "help": '<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/>'
            '<path d="M9.6 9.2a2.5 2.5 0 1 1 3.7 2.3c-.8.5-1.3 1-1.3 2"/><circle cx="12" cy="17" r=".9"/></svg>',
    "info": '<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/>'
            '<path d="M12 11.2v5"/><circle cx="12" cy="8" r=".9"/></svg>',
    "pedal": '<svg class="ic" viewBox="0 0 24 24"><rect x="7" y="3.5" width="10" height="17" rx="3.2"/>'
             '<path d="M12 7.5v5"/></svg>',
    "wheel": '<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.2"/><circle cx="12" cy="12" r="3.2"/>'
             '<path d="M12 3.8v5M12 15.2v5M3.8 12h5M15.2 12h5"/></svg>',
    "compare": '<svg class="ic" viewBox="0 0 24 24"><path d="M5 19V9M12 19V5M19 19v-6"/>'
               '<path d="M3 21h18"/></svg>',
    "clock": '<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>',
    "gauge": '<svg class="ic" viewBox="0 0 24 24"><path d="M4.5 17a8.5 8.5 0 1 1 15 0"/>'
             '<path d="M12 12.8l3.4-3.4"/><circle cx="12" cy="13.4" r="1.4"/></svg>',
    "map3d": '<svg class="ic" viewBox="0 0 24 24"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z"/>'
             '<path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/></svg>',
    "folder": '<svg class="ic" viewBox="0 0 24 24"><path d="M3.5 7.5A1.8 1.8 0 0 1 5.3 5.7h4l2 2h7.4'
              'a1.8 1.8 0 0 1 1.8 1.8v8.7a1.8 1.8 0 0 1-1.8 1.8H5.3a1.8 1.8 0 0 1-1.8-1.8z"/></svg>',
    "install": '<svg class="ic" viewBox="0 0 24 24"><path d="M12 4v9M8.5 10.5L12 14l3.5-3.5"/>'
               '<path d="M4.5 16.5v1.8a1.7 1.7 0 0 0 1.7 1.7h11.6a1.7 1.7 0 0 0 1.7-1.7v-1.8"/></svg>',
    "play": '<svg class="ic" viewBox="0 0 24 24"><path d="M8.5 5.4v13.2L19 12z"/></svg>',
    "refresh": '<svg class="ic" viewBox="0 0 24 24"><path d="M20 11a8 8 0 1 0-2.3 6.3"/>'
               '<path d="M20 4.8V11h-6.2"/></svg>',
    "doc": '<svg class="ic" viewBox="0 0 24 24"><path d="M6.5 3.5h7L18.5 8v12.5A1.5 1.5 0 0 1 17 22H6.5'
           'A1.5 1.5 0 0 1 5 20.5v-15A1.5 1.5 0 0 1 6.5 3.5z"/><path d="M13.5 3.5V8h4.5"/>'
           '<path d="M8.5 12.5h7M8.5 16h7"/></svg>',
}

# ── 统一配色 ─────────────────────────────────────────────────────────────
WHEEL_COLORS = {"FL": "#5B8FB9", "FR": "#D9A24A", "RL": "#D06A5C", "RR": "#4E9E7B"}
AXIS_COLORS = {"front": "#5B8FB9", "rear": "#D9A24A"}
BLUE, BLUE_DEEP, BLUE_SOFT = "#5B8FB9", "#3E6B92", "#8FBEDD"
WARM, COLD, GOOD, BAD = "#D9A24A", "#4F86B2", "#3E9E7B", "#D06A5C"


def esc(s):
    return _html.escape(str(s), quote=True)


def fmt_dist(m):
    return ("%.2f km" % (m / 1000.0)) if m >= 1000 else ("%.0f m" % m)


def fmt_dur(s):
    s = max(0, int(round(s)))
    if s >= 60:
        return "%d 分 %02d 秒" % (s // 60, s % 60)
    return "%d 秒" % s


def chip(icon_key, text, cls=""):
    """右上角小 chip。"""
    icon = IC.get(icon_key, "")
    return '<span class="chip%s">%s%s</span>' % ((' ' + cls) if cls else "", icon, esc(text))


def head_html(file_stem, file_full, title, badge, sub, chips=""):
    """每页顶部标题区（和首页完全同款）。右侧除了页面自己的 chips，还固定放一个「换数据」按钮。"""
    badge_html = ('<span class="badge">%s</span>' % esc(badge)) if badge else ""
    live_chip = ('<span class="chip live-chip live-idle" id="live-status" '
                 'title="游戏 / 抓包实时状态（每 3 秒刷新）">游戏没开</span>')
    play_btn = ('<button class="chip chip-btn play-btn" id="launch-game" '
                'title="通过 Steam 启动 BeamNG.drive">'
                '%s<span>启动游戏</span></button>' % IC["play"])
    data_btn = ('<button class="chip chip-btn" id="open-data" title="切换数据文件（CSV）">'
                '%s<span>换数据</span></button>' % IC["folder"])
    return (
        '<header class="head">\n'
        '  <div>\n'
        '    <div class="crumb"><span>车辆数据分析器</span><i>/</i><span>抓包数据</span><i>/</i>'
        '<b title="%s">%s</b></div>\n'
        '    <h1>%s %s</h1>\n'
        '    <p class="sub">%s</p>\n'
        '  </div>\n'
        '  <div class="head-right">%s%s%s%s</div>\n'
        '</header>\n'
    ) % (esc(file_full), esc(file_stem), esc(title), badge_html, sub, chips,
         live_chip, play_btn, data_btn)


def empty_state(icon_key, title, text):
    """空数据占位块。"""
    return ('<div class="empty"><div class="empty-ic">%s</div>'
            '<div class="empty-title">%s</div><div class="empty-text">%s</div></div>'
            % (IC.get(icon_key, ""), esc(title), esc(text)))


def legend(items):
    """图例：items = [(name, color, dashed_bool), ...]"""
    out = []
    for name, color, dash in items:
        out.append('<span class="lg%s"><i style="background:%s"></i>%s</span>'
                   % (' lg-dash' if dash else '', color, esc(name)))
    return '<div class="legend">%s</div>' % "".join(out)
