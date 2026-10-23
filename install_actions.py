# -*- coding: utf-8 -*-
"""
游戏内启动抓包 —— 三套入口一次配齐：

  ① UI App（mod 包已打好 roadProfileUI.zip）里的按钮：清空重记 / 开始·停止 / 导出
  ② 快捷键（本脚本装）：
        ctrl + shift + M   开始/停止（toggle，清空与否按当前状态）
        ctrl + shift + N   立即导出
  ③ 控制台（~）：extensions.roadProfile.start() / .stop() / .dump()

动作 ctx 用 tlua —— 引擎自己的 gameplay.json 里调 extensions.* 就是 tlua
（elua 也能用，但 tlua 是官方在用的；vlua 会跑到车辆沙箱里，没有 extensions）。

另外扩展里加了游戏内消息条提示（guihooks.trigger('Message', ...)），
启动/停止/导出都会在屏幕右上角弹一条，确认操作生效。
"""
import json, os, shutil

USER = r"D:\BeamNG\current"
ACT_DIR = os.path.join(USER, "lua", "ge", "extensions", "core", "input", "actions")
MAP_DIR = os.path.join(USER, "settings", "inputmaps")
os.makedirs(ACT_DIR, exist_ok=True)
os.makedirs(MAP_DIR, exist_ok=True)

ACTIONS = {
    "roadprofile_toggle": {
        "cat": "general", "order": 950, "ctx": "tlua",
        "onDown": "extensions.roadProfile.toggle()",
        "title": "路面抓包 开始/停止",
        "desc": "在游戏内开始或停止路面抓包（对所有车生效）",
    },
    "roadprofile_restart": {
        "cat": "general", "order": 951, "ctx": "tlua",
        "onDown": "extensions.roadProfile.start()",
        "title": "路面抓包 清空并重记",
        "desc": "清空缓冲重新开始记录（跑干净一圈用）",
    },
    "roadprofile_dump": {
        "cat": "general", "order": 952, "ctx": "tlua",
        "onDown": "extensions.roadProfile.dump()",
        "title": "路面抓包 导出",
        "desc": "立即导出 CSV + 调车摘要",
    },
}
BINDINGS = {
    "devicetype": "keyboard", "version": 1,
    "bindings": [
        {"action": "roadprofile_toggle", "control": "ctrl shift m"},
        {"action": "roadprofile_restart", "control": "ctrl shift b"},
        {"action": "roadprofile_dump", "control": "ctrl shift n"},
    ],
}

p = os.path.join(ACT_DIR, "roadProfileActions.json")
json.dump(ACTIONS, open(p, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
json.load(open(p, encoding="utf-8"))
print("动作:", p)

p2 = os.path.join(MAP_DIR, "keyboard_roadprofile.json")
json.dump(BINDINGS, open(p2, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
json.load(open(p2, encoding="utf-8"))
print("绑定:", p2)
for b in BINDINGS["bindings"]:
    print("   %-22s %s" % (b["action"], b["control"]))

# 同步扩展
src = r"D:\Deepseek Harness\yu7_yunnian\tools\roadProfile.lua"
dst = os.path.join(USER, "lua", "ge", "extensions", "roadProfile.lua")
shutil.copy2(src, dst)
t = open(dst, encoding="utf-8").read()
assert "guihooks.trigger('Message'" in t and "function M.getLive()" in t
print("扩展已同步:", os.path.getsize(dst), "bytes（含游戏内消息条提示）")
print("DONE")
