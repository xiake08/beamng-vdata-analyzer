# -*- coding: utf-8 -*-
"""设置页（左下角 ⚙，不属于页面导航）

- 路径配置：游戏用户目录 / 游戏主程序 / 抓包输出目录，可自动探测、浏览、保存
- 保存时写回 config.json，并同步更新 beamng_data 的全局路径，然后整页重载
- 一键把抓包扩展 / 自动加载脚本 / 面板 mod 装进游戏用户目录（等价老版 PathDialog）
"""

KEY = "settings"
LABEL = "设置"
ICON = "sliders"
TITLE = "设置"
BADGE = ""
SUB = "这一页看什么：路径配置 + 抓包 mod 安装。保存后写回 config.json，装 mod 之后重启游戏生效。"
ORDER = 90
UTILITY = True          # 右下角工具按钮，不出现在左侧页面导航里

INSTALL_JOBS = [
    ("lua", "抓包扩展 roadProfile.lua", "lua\\ge\\extensions\\roadProfile.lua"),
    ("script", "自动加载 modScript.lua", "scripts\\roadProfile\\modScript.lua"),
    ("zip", "面板 mod roadProfileUI.zip", "mods\\roadProfileUI.zip"),
]


def build(r, d):
    return d


def _install_status(userpath):
    import os
    out = {}
    for key, _label, rel in INSTALL_JOBS:
        try:
            out[key] = os.path.isfile(os.path.join(userpath, rel))
        except Exception:               # noqa: BLE001
            out[key] = False
    return out


def render(d):
    from .common import chip, esc, head_html

    T = None
    try:
        import beamng_data as T               # noqa: F401
    except Exception:                         # noqa: BLE001
        pass

    userpath = getattr(T, "USERPATH", "") if T else ""
    game_exe = getattr(T, "GAME_EXE", "") if T else ""
    outdir = getattr(T, "OUTDIR", "") if T else ""
    cfg_file = getattr(T, "CFG_FILE", "") if T else ""
    inst = _install_status(userpath)

    chips = chip("folder", "路径配置") + chip("install", "抓包 mod 一键安装")
    head = head_html(d["file"], d["file"], TITLE, BADGE, SUB, chips)

    status_rows = "".join(
        '<div class="kv-row"><dt>%s</dt><dd class="inst" data-key="%s">%s</dd></div>'
        % (esc(label), key,
           '<span class="ok">✓ 已安装</span>' if inst.get(key) else '<span class="no">✗ 未安装</span>')
        for key, label, _rel in INSTALL_JOBS)

    body = """
    <section class="page-body">
      <section class="grid">
        <article class="card page-card">
          <div class="panel-head"><div><h2>路径配置</h2><p>换电脑 / 换安装位置时在这里改，保存后写回 config.json</p></div></div>
          <div class="cfg-form">
            <label>游戏用户目录
              <span>里面要有 mods 和 lua 文件夹（例如 D:\\BeamNG\\current）</span>
            </label>
            <div class="cfg-row">
              <input id="cfg-userpath" value="%(userpath)s" spellcheck="false">
              <button class="cfg-btn ghost" id="cfg-browse-userpath">浏览…</button>
            </div>
            <label>游戏主程序
              <span>BeamNG.drive.x64.exe 的完整路径</span>
            </label>
            <div class="cfg-row">
              <input id="cfg-game-exe" value="%(game_exe)s" spellcheck="false">
              <button class="cfg-btn ghost" id="cfg-browse-game">浏览…</button>
            </div>
            <label>抓包输出目录
              <span>程序读取 / 整理 CSV 的地方</span>
            </label>
            <div class="cfg-row">
              <input id="cfg-outdir" value="%(outdir)s" spellcheck="false">
              <button class="cfg-btn ghost" id="cfg-browse-outdir">浏览…</button>
            </div>
            <div class="cfg-actions">
              <button class="cfg-btn ghost" id="cfg-detect">自动探测</button>
              <button class="cfg-btn" id="cfg-save">保存</button>
              <button class="cfg-btn" id="cfg-save-install">保存并安装到游戏</button>
            </div>
            <p class="hint" id="cfg-hint">保存后界面会自动重载；点「保存并安装」会同时把抓包 mod 装进游戏目录。</p>
            <p class="hint">config.json：%(cfg_file)s</p>
          </div>
        </article>
        <aside class="side">
          <article class="card">
            <div class="panel-head"><div><h2>抓包 mod</h2><p>装进游戏用户目录的三件东西</p></div></div>
            <dl class="kv" style="margin-top:4px">%(status_rows)s</dl>
            <div class="cfg-actions">
              <button class="cfg-btn" id="cfg-install">一键安装 / 修复</button>
            </div>
            <p class="hint">安装到：%(userpath)s</p>
            <p class="hint">装完重启游戏才会加载扩展。</p>
          </article>
          <article class="card">
            <div class="panel-head"><div><h2>说明</h2><p>和老版的关系</p></div></div>
            <div class="tip-text" style="line-height:1.75">
              · 保存路径会同步更新程序里的 <b>USERPATH / GAME_EXE / OUTDIR</b>，不用重启界面。<br>
              · 抓包本身在游戏内进行（扩展写 CSV 到输出目录）；新数据出现后，点右上角「换数据」就能读到。<br>
              · 路径和 mod 安装都只改本机文件，不改游戏本体。
            </div>
          </article>
        </aside>
      </section>
    </section>""" % {
        "userpath": esc(userpath),
        "game_exe": esc(game_exe),
        "outdir": esc(outdir),
        "cfg_file": esc(cfg_file),
        "status_rows": status_rows,
    }
    return ('<section class="page" data-page="%s" data-title="%s">\n%s%s\n</section>'
            % (KEY, TITLE, head, body))


CSS = """
.cfg-form{display:flex;flex-direction:column;gap:6px;margin-top:4px}
.cfg-form label{font-size:12px;font-weight:600;color:var(--ink-2);letter-spacing:.02em;margin-top:8px}
.cfg-form label span{display:block;font-weight:400;font-size:11px;color:var(--muted);margin-top:2px}
.cfg-row{display:flex;gap:10px;align-items:center}
.cfg-row input{flex:1;height:36px;padding:0 12px;border-radius:10px;font-family:inherit;
  font-size:12.4px;color:var(--ink);background:rgba(255,255,255,.78);
  border:1px solid rgba(91,143,185,.2);outline:none;box-shadow:inset 0 1px 3px rgba(60,90,120,.06)}
.cfg-row input:focus{border-color:rgba(91,143,185,.55);box-shadow:0 0 0 3px rgba(91,143,185,.12)}
.cfg-btn{height:34px;padding:0 16px;border:0;border-radius:10px;cursor:pointer;font-family:inherit;
  font-size:12.3px;font-weight:600;color:#fff;background:linear-gradient(150deg,#7FB2D6,#4A7398);
  box-shadow:0 10px 22px -12px rgba(74,115,152,.9);transition:transform .2s var(--ease);white-space:nowrap}
.cfg-btn:hover{transform:translateY(-1px)}
.cfg-btn.ghost{color:var(--blue-3);background:rgba(255,255,255,.78);
  border:1px solid rgba(91,143,185,.24);box-shadow:none}
.cfg-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.inst .ok{color:#2F7D5E;font-weight:600}
.inst .no{color:#B4762F;font-weight:600}
"""

JS = """
window.PAGE_INIT = window.PAGE_INIT || {};
window.PAGE_INIT.settings = function (root, DATA) {
  var $ = function (sel) { return root.querySelector(sel); };
  function api() { return window.pywebview && window.pywebview.api; }
  function can(name) { var a = api(); return !!(a && a[name]); }
  function toast(msg) { if (window.__toast) window.__toast(msg); }
  function val(id) { var el = $(id); return el ? el.value.trim() : ''; }

  function setStatus(installed) {
    Array.prototype.forEach.call(root.querySelectorAll('.inst'), function (el) {
      var ok = !!(installed && installed[el.getAttribute('data-key')]);
      el.innerHTML = ok ? '<span class="ok">✓ 已安装</span>' : '<span class="no">✗ 未安装</span>';
    });
  }

  function detect() {
    if (!can('autodetect_paths')) { toast('真窗口里才能自动探测'); return; }
    api().autodetect_paths().then(function (r) {
      if (!r || !r.ok) { toast('探测失败：' + ((r && r.error) || '')); return; }
      if (r.userpath) $('#cfg-userpath').value = r.userpath;
      if (r.game_exe) $('#cfg-game-exe').value = r.game_exe;
      toast('已自动探测，确认后点「保存」');
    });
  }

  function browse(kind) {
    var target = { userpath: '#cfg-userpath', game: '#cfg-game-exe', outdir: '#cfg-outdir' }[kind];
    var method = kind === 'game' ? 'pick_exe' : 'pick_folder';
    if (!can(method)) { toast('真窗口里才能选择文件夹'); return; }
    api()[method]().then(function (r) {
      if (!r || r.cancelled) return;
      if (!r.ok) { toast('选择失败：' + ((r && r.error) || '')); return; }
      $(target).value = r.path;
    });
  }

  function save(thenInstall) {
    if (!can('save_config')) { toast('真窗口里才能保存'); return; }
    toast('正在保存路径…');
    api().save_config(val('#cfg-userpath'), val('#cfg-game-exe'), val('#cfg-outdir')).then(function (r) {
      if (!r || !r.ok) { toast('保存失败：' + ((r && r.error) || '')); return; }
      if (!thenInstall) return;
      api().install_mod().then(function (m) {
        if (!m || !m.ok) { toast('路径已保存，安装失败：' + ((m && m.error) || ((m && m.msgs) || []).join('; '))); return; }
        toast('已保存并安装 ' + m.done + ' 项，重启游戏后生效');
        if (can('config_info')) {
          api().config_info().then(function (info) { if (info) setStatus(info.installed); });
        }
      });
    });
  }

  var bind = function (sel, fn) { var el = $(sel); if (el) el.addEventListener('click', fn); };
  bind('#cfg-detect', detect);
  bind('#cfg-save', function () { save(false); });
  bind('#cfg-save-install', function () { save(true); });
  bind('#cfg-browse-userpath', function () { browse('userpath'); });
  bind('#cfg-browse-game', function () { browse('game'); });
  bind('#cfg-browse-outdir', function () { browse('outdir'); });
  bind('#cfg-install', function () {
    if (!can('install_mod')) { toast('真窗口里才能安装'); return; }
    toast('正在安装抓包 mod…');
    api().install_mod().then(function (m) {
      if (!m || !m.ok) {
        toast('安装失败：' + ((m && m.error) || ((m && m.msgs) || []).join('; ') || '未知错误'));
        return;
      }
      toast('已安装 ' + m.done + ' 项，重启游戏后生效');
      if (can('config_info')) {
        api().config_info().then(function (info) { if (info) setStatus(info.installed); });
      }
    });
  });

  if (!can('save_config')) {
    var h = root.querySelector('#cfg-hint');
    if (h) h.textContent = '静态预览：这里的按钮不会真的保存，开真窗口才生效。';
  }
};
"""
