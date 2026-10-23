# -*- coding: utf-8 -*-
"""页面模块注册表：web_ui.py 从这里取每一页。

每个模块的接口见 SPEC.md：
    KEY/LABEL/ICON/TITLE/BADGE/SUB/ORDER
    build(r, d) -> d
    render(d) -> html
    CSS / JS
"""

import importlib

MODULE_NAMES = [
    "p_profile",
    "p_dyno",
    "p_wheels",
    "p_wave",
    "p_pedals",
    "p_compare",
    "p_map3d",
    "p_summary",
    "p_settings",
    "p_help",
]

PAGES = []
ERRORS = []
for _name in MODULE_NAMES:
    try:
        _mod = importlib.import_module("webui_parts." + _name)
        PAGES.append(_mod)
    except Exception as _e:  # noqa: BLE001
        ERRORS.append("%s: %s" % (_name, _e))

PAGES.sort(key=lambda m: getattr(m, "ORDER", 99))

BY_KEY = {getattr(m, "KEY", ""): m for m in PAGES}
