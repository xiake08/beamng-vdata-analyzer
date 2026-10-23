# -*- coding: utf-8 -*-
"""卸载程序源码（构建成安装目录里的 卸载.exe）。

构建（无空格路径）：
pyinstaller --onefile --windowed --name 卸载 --icon app.ico uninstaller.py

行为：
- 关闭正在运行的程序
- 删除桌面快捷方式（仅当它指向本目录）
- 删除安装目录（目录里的「抓包数据」保留为同级 <目录>_抓包数据）
- 删除注册表卸载项（仅当 InstallLocation 指向本目录）
- 支持 --silent 静默模式
"""
import base64
import os
import random
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import winreg
from tkinter import messagebox

APP_NAME = "车辆数据分析器"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\车辆数据分析器"


def install_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def log(msg):
    try:
        with open(os.path.join(os.environ.get("TEMP", "."), "dsh_uninstaller.log"),
                  "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:  # noqa: BLE001
        pass


def desktop_lnk():
    return os.path.join(os.path.expanduser("~"), "Desktop", APP_NAME + ".lnk")


def shortcut_target(lnk):
    ps = ("$ws = New-Object -ComObject WScript.Shell; "
          "$s = $ws.CreateShortcut('%s'); Write-Output $s.TargetPath" % lnk)
    enc = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-EncodedCommand", enc], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        return (r.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def registry_install_location():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
            loc, _ = winreg.QueryValueEx(k, "InstallLocation")
            return loc or ""
    except OSError:
        return ""


def do_uninstall(d, silent=False):
    subprocess.run(["taskkill", "/F", "/IM", APP_NAME + ".exe"],
                   capture_output=True, timeout=30)
    time.sleep(1.0)
    lnk = desktop_lnk()
    if os.path.exists(lnk):
        tgt = shortcut_target(lnk).lower()
        if tgt.startswith(d.lower()):
            try:
                os.remove(lnk)
                log("removed shortcut")
            except OSError as e:
                log("shortcut fail %r" % e)
        else:
            log("keep shortcut (points to %s)" % tgt)
    loc = registry_install_location()
    if loc and os.path.abspath(loc).lower() == d.lower():
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
            log("removed registry")
        except OSError as e:
            log("registry fail %r" % e)
    else:
        log("keep registry (points to %s)" % loc)
    data_dir = os.path.join(d, "抓包数据")
    if os.path.isdir(data_dir):
        keep = d.rstrip("\\/") + "_抓包数据"
        try:
            if os.path.exists(keep):
                keep = keep + "_" + time.strftime("%H%M%S")
            os.rename(data_dir, keep)
            log("kept data at " + keep)
        except OSError as e:
            log("data move fail %r" % e)
    bat = os.path.join(tempfile.gettempdir(),
                       "dsh_uninst_%d_%d.bat" % (os.getpid(), random.randint(100, 999)))
    with open(bat, "w", encoding="gbk", errors="replace") as f:
        f.write("@echo off\r\n")
        f.write('cd /d "%TEMP%"\r\n')
        f.write("ping -n 3 127.0.0.1 >nul\r\n")
        f.write("taskkill /F /IM %s.exe >nul 2>&1\r\n" % APP_NAME)
        f.write('rmdir /S /Q "%s"\r\n' % d)
        f.write('del /Q "%~f0"\r\n')
    subprocess.Popen(["cmd", "/c", bat], creationflags=0x00000008,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    return True


class App(tk.Tk):
    def __init__(self, silent=False):
        super().__init__()
        self.silent = silent
        self.d = install_dir()
        self.title("卸载 %s" % APP_NAME)
        self.geometry("480x260")
        self.resizable(False, False)
        self.configure(bg="#f2f6fa")
        head = tk.Frame(self, bg="#7a2530", height=64)
        head.pack(fill="x")
        tk.Label(head, text="卸载 %s" % APP_NAME, bg="#7a2530", fg="#ffffff",
                 font=("Microsoft YaHei", 15, "bold")).pack(anchor="w", padx=18,
                                                            pady=(12, 0))
        body = tk.Frame(self, bg="#f2f6fa", padx=18, pady=14)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="安装目录：%s" % self.d, bg="#f2f6fa", fg="#274156",
                 font=("Microsoft YaHei", 9), wraplength=440, justify="left",
                 anchor="w").pack(fill="x")
        tk.Label(body, text="将关闭程序、删除桌面快捷方式和安装目录。\n"
                            "如果目录里有「抓包数据」，会保留到同级的 <目录>_抓包数据。",
                 bg="#f2f6fa", fg="#5c7288", font=("Microsoft YaHei", 9),
                 justify="left", anchor="w", wraplength=440).pack(fill="x", pady=(10, 0))
        foot = tk.Frame(self, bg="#f2f6fa", pady=10)
        foot.pack(fill="x", side="bottom")
        tk.Button(foot, text="取消", command=self.destroy, relief="flat",
                  font=("Microsoft YaHei", 10), width=8).pack(side="right", padx=(0, 18))
        tk.Button(foot, text="卸载", command=self.run, bg="#C0504D", fg="#ffffff",
                  relief="flat", font=("Microsoft YaHei", 11, "bold"),
                  width=10).pack(side="right")
        if silent:
            self.withdraw()
            self.after(200, self.run)

    def run(self):
        if not self.silent:
            if not messagebox.askyesno("确认卸载",
                                       "确定要卸载 %s 吗？\n\n目录：%s"
                                       % (APP_NAME, self.d)):
                return
        try:
            do_uninstall(self.d, self.silent)
        except Exception as e:  # noqa: BLE001
            log("ERROR %r" % e)
            if not self.silent:
                messagebox.showerror("卸载失败", str(e))
            self.destroy()
            return
        log("uninstall requested for " + self.d)
        if not self.silent:
            messagebox.showinfo("已卸载",
                                "已安排删除：\n%s\n\n程序目录会在几秒后自动删除。"
                                % self.d)
        self.destroy()


def main():
    silent = "--silent" in sys.argv
    App(silent=silent).mainloop()


if __name__ == "__main__":
    main()
