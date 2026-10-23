# -*- coding: utf-8 -*-
"""车辆数据分析器 v2.0 安装程序（源码，放 tools/installer_gui.py）。

构建（无空格路径）：app.zip / app.ico 与脚本同目录
pyinstaller --onefile --windowed --name 车辆数据分析器_v2.0_安装程序 --icon app.ico --add-data "app.zip;." --add-data "app.ico;." installer_gui.py

功能：
- 检测旧版本：注册表卸载项（关键字 车辆/beamng_road_tool/roadProfile）、常见目录、
  桌面+开始菜单快捷方式、各盘符浅层扫描特征目录
- 多版本列表选择要覆盖的目标（默认旧版本）
- 覆盖：关旧进程 → 保留 config.json → 清旧文件 → 解压新版 → 写版本号/注册卸载项
- 卸载项指向安装目录里的 卸载.exe（--silent 支持）
"""
import base64
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import winreg
import zipfile
from tkinter import filedialog, messagebox, ttk

APP_NAME = "车辆数据分析器"
VERSION = "2.0"
UNINSTALLER = "卸载.exe"
DEFAULT_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                           APP_NAME)
FONT = ("Microsoft YaHei", 10)
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\车辆数据分析器"
VERSION_FILE = "version.json"
CONFIG_FILE = "config.json"
CANDIDATE_DIRS = [
    r"C:\车辆数据分析器",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), APP_NAME),
    os.path.join(os.environ.get("APPDATA", ""), APP_NAME),
    os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), APP_NAME),
    os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), APP_NAME),
    os.path.join(os.path.expanduser("~"), "Desktop", APP_NAME),
    r"D:\车辆数据分析器",
]
KEYWORDS = ("车辆数据分析器", "beamng_road_tool", "roadprofile")
SKIP_NAMES = {"windows", "$recycle.bin", "system volume information", "programdata",
              "recovery", "onedrivetemp", "node_modules", "__pycache__", ".git",
              "perflogs", "inetpub", "appdata", "temp", "microsoft", "packages",
              "winsxs", "driverstore", "installer", "assembly"}
SKIP_PATHS = {"c:\\windows", "c:\\programdata", "c:\\$recycle.bin",
              "c:\\system volume information", "c:\\recovery"}


def vshow(ver):
    s = str(ver or "?").strip()
    if s.lower().startswith("v") or not s[:1].isdigit():
        return s
    return "v" + s


def payload_path():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "app.zip")


def log(msg):
    try:
        with open(os.path.join(os.environ.get("TEMP", "."), "dsh_installer.log"),
                  "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:  # noqa: BLE001
        pass


def dir_looks_like_app(d):
    if os.path.exists(os.path.join(d, APP_NAME + ".exe")):
        return True
    if os.path.exists(os.path.join(d, "beamng_road_tool.exe")):
        return True
    if os.path.exists(os.path.join(d, "beamng_road_tool.py")):
        return True
    if (os.path.exists(os.path.join(d, "roadProfileUI.zip"))
            and os.path.exists(os.path.join(d, "roadProfile.lua"))):
        return True
    return False


def dir_version(d):
    vf = os.path.join(d, VERSION_FILE)
    if os.path.exists(vf):
        try:
            with open(vf, encoding="utf-8") as f:
                return json.load(f).get("version", "?")
        except Exception:  # noqa: BLE001
            return "?"
    if (os.path.exists(os.path.join(d, "beamng_road_tool.py"))
            or os.path.exists(os.path.join(d, "beamng_road_tool.exe"))):
        return "v1.x（旧版）"
    return "旧版本（无版本号）"


def detect_by_registry():
    found, seen = [], set()
    keys = [(winreg.HKEY_CURRENT_USER,
             r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")]
    for hive, path in keys:
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(root, i)
                i += 1
            except OSError:
                break
            try:
                with winreg.OpenKey(root, sub) as k:
                    name, _ = winreg.QueryValueEx(k, "DisplayName")
                    if not any(kw.lower() in str(name).lower() for kw in KEYWORDS):
                        continue
                    try:
                        loc, _ = winreg.QueryValueEx(k, "InstallLocation")
                    except OSError:
                        loc = ""
                    try:
                        ver, _ = winreg.QueryValueEx(k, "DisplayVersion")
                    except OSError:
                        ver = "?"
                    if loc and os.path.isdir(loc) and loc not in seen:
                        seen.add(loc)
                        found.append((loc, ver, "注册表"))
            except OSError:
                continue
    return found


def detect_by_dirs():
    return [(d, dir_version(d), "常见目录") for d in CANDIDATE_DIRS
            if d and os.path.isdir(d) and dir_looks_like_app(d)]


def detect_by_shortcuts():
    found = []
    ps = ("$out = @(); "
          "$dirs = @([Environment]::GetFolderPath('Desktop'), "
          "[Environment]::GetFolderPath('Programs')); "
          "foreach ($d in $dirs) { if (Test-Path $d) { "
          "Get-ChildItem -Path $d -Recurse -Filter *.lnk -ErrorAction SilentlyContinue | "
          "ForEach-Object { $ws = New-Object -ComObject WScript.Shell; "
          "$t = $ws.CreateShortcut($_.FullName).TargetPath; "
          "if ($t -match '车辆数据分析器|beamng_road_tool') { "
          "$out += (Split-Path $t -Parent) } } } } ; $out | Select-Object -Unique")
    enc = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-EncodedCommand", enc], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=90)
        for line in (r.stdout or "").splitlines():
            d = line.strip()
            if d and os.path.isdir(d):
                found.append((d, dir_version(d), "快捷方式"))
    except Exception:  # noqa: BLE001
        pass
    return found


def _scan(root, depth, out, seen):
    if depth < 0:
        return
    try:
        entries = list(os.scandir(root))
    except OSError:
        return
    for e in entries:
        try:
            if not e.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        p, name = e.path, e.name.lower()
        if name in SKIP_NAMES or p.lower() in SKIP_PATHS:
            continue
        if dir_looks_like_app(p):
            ap = os.path.abspath(p)
            if ap not in seen:
                seen.add(ap)
                out.append((ap, dir_version(ap), "磁盘扫描"))
            continue
        _scan(p, depth - 1, out, seen)


def detect_by_scan():
    found, seen, roots = [], set(), []
    for d in ("C:\\", "D:\\", "E:\\", "F:\\"):
        if os.path.isdir(d):
            roots.append((d, 2))
    home = os.path.expanduser("~")
    for sub in ("Desktop", "Downloads", "Documents"):
        d = os.path.join(home, sub)
        if os.path.isdir(d):
            roots.append((d, 3))
    for root, depth in roots:
        _scan(root, depth, found, seen)
    return found


def detect_existing():
    seen, order = {}, []
    for d, ver, src in (detect_by_registry() + detect_by_dirs()
                        + detect_by_shortcuts() + detect_by_scan()):
        ap = os.path.abspath(d)
        if ap in seen:
            if seen[ap][0] in ("?", "", "旧版本（无版本号）", "v1.x（旧版）") \
                    and ver not in ("?", "", "旧版本（无版本号）", "v1.x（旧版）"):
                seen[ap] = [ver, seen[ap][1] + "/" + src]
            continue
        low = ap.lower()
        if "\\installer_build" in low or "\\_pack\\" in low or "\\pkgwork\\" in low:
            continue
        if os.path.basename(low) in ("system32", "windows", "programdata"):
            continue
        seen[ap] = [ver, src]
        order.append(ap)
    return [(ap, seen[ap][0], seen[ap][1]) for ap in order]


def is_current(ver):
    return str(ver).lower().lstrip("v").startswith(VERSION)


def write_version_file(d):
    try:
        with open(os.path.join(d, VERSION_FILE), "w", encoding="utf-8") as f:
            json.dump({"name": APP_NAME, "version": VERSION,
                       "installed_at": time.strftime("%Y-%m-%d %H:%M:%S")},
                      f, ensure_ascii=False, indent=1)
    except Exception as e:  # noqa: BLE001
        log("version file fail " + repr(e))


def register_uninstall(d):
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, "v" + VERSION)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, d)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "DSH")
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ,
                          os.path.join(d, "app.ico"))
        ui = os.path.join(d, UNINSTALLER)
        if os.path.exists(ui):
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, '"%s"' % ui)
            winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ,
                              '"%s" --silent' % ui)
        else:
            uninst = ("powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "
                      "\"Remove-Item -LiteralPath '%s' -Recurse -Force -ErrorAction "
                      "SilentlyContinue\"" % d)
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, uninst)
            winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ, uninst)
        winreg.CloseKey(key)
        log("registry written, uninstaller=%s" % ui)
    except Exception as e:  # noqa: BLE001
        log("registry fail " + repr(e))


def make_shortcut(target, workdir):
    ps = ("$ws = New-Object -ComObject WScript.Shell; "
          "$desktop = [Environment]::GetFolderPath('Desktop'); "
          "$lnk = $ws.CreateShortcut($desktop + '\\%s.lnk'); "
          "$lnk.TargetPath = '%s'; $lnk.WorkingDirectory = '%s'; "
          "$lnk.IconLocation = '%s'; $lnk.Description = '%s v%s'; $lnk.Save()"
          % (APP_NAME, target, workdir, os.path.join(workdir, "app.ico"),
             APP_NAME, VERSION))
    enc = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-EncodedCommand", enc], capture_output=True, timeout=90)


class Installer(tk.Tk):
    def __init__(self, auto_dir=None):
        super().__init__()
        self.auto_dir = auto_dir
        self.existing = [] if auto_dir else detect_existing()
        log("detected: %r" % (self.existing,))
        default = DEFAULT_DIR
        if self.existing:
            olds = [e for e in self.existing if not is_current(e[1])]
            default = olds[0][0] if olds else self.existing[0][0]
        self.title("%s v%s 安装程序" % (APP_NAME, VERSION))
        self.geometry("640x500")
        self.resizable(False, False)
        self.configure(bg="#f2f6fa")
        self.var_dir = tk.StringVar(value=auto_dir or default)
        self.var_shortcut = tk.BooleanVar(value=not bool(auto_dir))
        self.var_run = tk.BooleanVar(value=not bool(auto_dir))
        self._build()
        if auto_dir:
            self.withdraw()
            self.after(200, self.do_install)

    def _build(self):
        head = tk.Frame(self, bg="#12303f", height=80)
        head.pack(fill="x")
        tk.Label(head, text="车辆数据分析器 v%s" % VERSION, bg="#12303f", fg="#ffffff",
                 font=("Microsoft YaHei", 16, "bold")).pack(anchor="w", padx=18, pady=(14, 0))
        tk.Label(head, text="BeamNG 跑图数据采集 · 悬挂调校助手", bg="#12303f",
                 fg="#a9c3d6", font=("Microsoft YaHei", 9)).pack(anchor="w", padx=18)
        body = tk.Frame(self, bg="#f2f6fa", padx=18, pady=12)
        body.pack(fill="both", expand=True)
        if self.existing:
            tk.Label(body, text="检测到 %d 处已安装的版本（点选要覆盖/升级的目标）："
                     % len(self.existing), bg="#f2f6fa", fg="#b05a2a",
                     font=("Microsoft YaHei", 9, "bold")).pack(anchor="w")
            self.lst = tk.Listbox(body, height=min(5, max(2, len(self.existing))),
                                  font=("Microsoft YaHei", 9), activestyle="none")
            self.lst.pack(fill="x", pady=(4, 0))
            for d, ver, src in self.existing:
                tag = "（当前版本）" if is_current(ver) else "（旧版本）"
                self.lst.insert("end", "%s  %s  %s   [%s]" % (vshow(ver), tag, d, src))
            self.lst.selection_set(0)
            self.lst.bind("<<ListboxSelect>>", self._on_pick)
            tk.Label(body, text="提示：选旧版本目录就是覆盖升级；config.json 的路径配置会保留。",
                     bg="#f2f6fa", fg="#5c7288",
                     font=("Microsoft YaHei", 8)).pack(anchor="w", pady=(2, 0))
        else:
            tk.Label(body, text="未检测到旧版本，将进行全新安装。", bg="#f2f6fa",
                     fg="#4f7a5e", font=("Microsoft YaHei", 9)).pack(anchor="w")
        tk.Label(body, text="安装位置（建议不要带空格）", bg="#f2f6fa", fg="#274156",
                 font=("Microsoft YaHei", 10, "bold")).pack(anchor="w", pady=(8, 0))
        row = tk.Frame(body, bg="#f2f6fa")
        row.pack(fill="x", pady=(4, 0))
        tk.Entry(row, textvariable=self.var_dir, font=FONT, relief="solid",
                 bd=1).pack(side="left", fill="x", expand=True, ipady=2)
        tk.Button(row, text="浏览...", command=self.browse,
                  font=("Microsoft YaHei", 9)).pack(side="left", padx=(8, 0))
        tk.Checkbutton(body, text="创建/更新桌面快捷方式", variable=self.var_shortcut,
                       bg="#f2f6fa", activebackground="#f2f6fa",
                       font=("Microsoft YaHei", 9)).pack(anchor="w", pady=(6, 0))
        tk.Checkbutton(body, text="安装完成后启动", variable=self.var_run,
                       bg="#f2f6fa", activebackground="#f2f6fa",
                       font=("Microsoft YaHei", 9)).pack(anchor="w")
        self.pb = ttk.Progressbar(body, mode="determinate", maximum=100)
        self.pb.pack(fill="x", pady=(10, 4))
        self.lbl = tk.Label(body, text="准备就绪", bg="#f2f6fa", fg="#5c7288",
                            font=("Microsoft YaHei", 9), anchor="w")
        self.lbl.pack(fill="x")
        foot = tk.Frame(self, bg="#f2f6fa", pady=10)
        foot.pack(fill="x", side="bottom")
        self.btn = tk.Button(foot, text="覆盖安装" if self.existing else "开始安装",
                             command=self.do_install, bg="#7FB2D6", fg="#12303f",
                             relief="flat", font=("Microsoft YaHei", 11, "bold"), width=14)
        self.btn.pack(side="right", padx=18)
        tk.Button(foot, text="退出", command=self.destroy, relief="flat",
                  font=("Microsoft YaHei", 10), width=8).pack(side="right")

    def _on_pick(self, _evt=None):
        sel = self.lst.curselection()
        if sel:
            self.var_dir.set(self.existing[sel[0]][0])

    def browse(self):
        d = filedialog.askdirectory(initialdir=os.path.dirname(self.var_dir.get()))
        if d:
            self.var_dir.set(d)

    def do_install(self):
        target = self.var_dir.get().strip()
        if not target:
            messagebox.showwarning("提示", "请选择安装位置")
            return
        if " " in target and not self.auto_dir:
            messagebox.showwarning(
                "路径含空格",
                "安装路径里有空格。\n\n.NET 运行时在带空格路径下可能加载失败，"
                "建议改成不含空格的路径，例如：C:\\车辆数据分析器")
        if not os.path.exists(payload_path()):
            messagebox.showerror("错误", "安装包数据缺失（app.zip）")
            return
        self.btn.configure(state="disabled")
        threading.Thread(target=self._work, args=(target,), daemon=True).start()

    def _work(self, target):
        try:
            os.makedirs(target, exist_ok=True)
            self.after(0, self._set_progress, 2, "正在关闭旧版本进程")
            subprocess.run(["taskkill", "/F", "/IM", APP_NAME + ".exe"],
                           capture_output=True, timeout=30)
            time.sleep(0.8)
            cfg_path = os.path.join(target, CONFIG_FILE)
            old_cfg = None
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "rb") as f:
                        old_cfg = f.read()
                except OSError:
                    old_cfg = None
            self.after(0, self._set_progress, 6, "正在清理旧版本文件")
            import shutil
            keep = {CONFIG_FILE, "抓包数据"}
            for name in os.listdir(target):
                if name in keep:
                    continue
                p = os.path.join(target, name)
                try:
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        os.remove(p)
                except OSError:
                    pass
            zf = zipfile.ZipFile(payload_path())
            names = zf.namelist()
            total = max(1, len(names))
            for i, n in enumerate(names):
                zf.extract(n, target)
                if i % 20 == 0 or i == total - 1:
                    self.after(0, self._set_progress,
                               10 + int((i + 1) * 80 / total),
                               "正在安装文件 %d/%d" % (i + 1, total))
            zf.close()
            if old_cfg:
                with open(cfg_path, "wb") as f:
                    f.write(old_cfg)
            exe = os.path.join(target, APP_NAME + ".exe")
            if not os.path.exists(exe):
                raise RuntimeError("安装后找不到主程序：%s" % exe)
            self.after(0, self._set_progress, 93, "正在写安装信息")
            write_version_file(target)
            register_uninstall(target)
            with open(os.path.join(target, "卸载说明.txt"), "w", encoding="utf-8") as f:
                f.write("卸载方式：\n"
                        "1. 设置 → 应用 → %s → 卸载；\n"
                        "2. 或双击安装目录里的「%s」；\n"
                        "3. 或删除本文件夹 + 桌面快捷方式。\n" % (APP_NAME, UNINSTALLER))
            if self.var_shortcut.get():
                self.after(0, self._set_progress, 96, "正在创建桌面快捷方式")
                make_shortcut(exe, target)
            self.after(0, self._set_progress, 100, "安装完成")
            log("installed v%s to %s" % (VERSION, target))
            self.after(0, self._done, target, exe)
        except Exception as e:  # noqa: BLE001
            log("ERROR " + repr(e))
            self.after(0, lambda: messagebox.showerror("安装失败", str(e)))
            self.after(0, lambda: self.btn.configure(state="normal"))

    def _set_progress(self, pct, text):
        self.pb["value"] = pct
        self.lbl.configure(text=text)

    def _done(self, target, exe):
        if not self.auto_dir:
            messagebox.showinfo("安装完成",
                                "已安装到：\n%s\n\n桌面快捷方式已更新；\n"
                                "卸载可用安装目录里的「%s」。" % (target, UNINSTALLER))
        if self.var_run.get():
            subprocess.Popen([exe], cwd=target)
        self.destroy()


def main():
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--auto":
        Installer(auto_dir=args[1]).mainloop()
    elif len(args) >= 2 and args[0] == "--uninstall":
        # 兼容旧调用：交给安装目录里的 卸载.exe
        d = args[1]
        ui = os.path.join(d, UNINSTALLER)
        if os.path.exists(ui):
            subprocess.Popen([ui, "--silent"], cwd=d)
    else:
        Installer().mainloop()


if __name__ == "__main__":
    main()
