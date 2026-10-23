-- ════════════════════════════════════════════════════════════════════════
-- roadProfile —— BeamNG 路面数据采集扩展（重写版）
-- 只做四件事：
--   1) 车辆探针采数据 -> push()
--   2) 存内存 -> dump() 导出 CSV + TXT
--   3) getLive() 给游戏内面板
--   4) 状态文件 / 命令文件 给外部程序通信
-- CSV 列与旧版完全一致，桌面程序不用改
-- ════════════════════════════════════════════════════════════════════════
local M = {}

local F_STATUS = "roadProfile_status.txt"
local F_CMD = "roadProfile_cmd.txt"
local HZ = 10
local MAX_SAMPLES = 60000
local PROBE_TIMER = 1.0 / HZ

local recording = false
local samples, idx, dist = {}, 0, 0
local lastPos = nil
local lastCmd = ""
local lastVehId = nil
local probeErr = 0

local vehInfo = { modelName = "?", model = "?", cfgName = "?", cfgKey = "?" }
local live = nil
local LIVE_BINS = { 0.02, 0.05, 0.10, 0.20, 0.30, 0.50, 0.80, 1.20, 2.00 }

local function writeFile(name, data)
  local f = io.open(name, "w")
  if f then f:write(data) f:close() return true end
  return false
end

local function readFile(name)
  local f = io.open(name, "r")
  if not f then return nil end
  local d = f:read("*a")
  f:close()
  return d
end

local function levelName()
  local ok, lv = pcall(getCurrentLevelIdentifier)
  if ok and type(lv) == "string" and lv ~= "" then return lv end
  return "?"
end

local function playerVeh()
  local ok, veh = pcall(getPlayerVehicle, 0)
  if ok and veh then return veh end
  ok, veh = pcall(function() return be:getPlayerVehicle(0) end)
  if ok then return veh end
  return nil
end

-- ── 实时统计 ────────────────────────────────────────────────────────────
local function resetLive()
  live = { n = 0, vsum = 0, vmax = 0, rmsF = 0, rmsR = 0,
           hFc = {}, hFr = {}, hRc = {}, hRr = {},
           load = { FL = 0, FR = 0, RL = 0, RR = 0 },
           air = { FL = 0, FR = 0, RL = 0, RR = 0 },
           loadNow = { FL = 0, FR = 0, RL = 0, RR = 0 } }
  for i = 1, #LIVE_BINS + 1 do
    live.hFc[i], live.hFr[i], live.hRc[i], live.hRr[i] = 0, 0, 0, 0
  end
end
resetLive()

local function binOf(v)
  for i = 1, #LIVE_BINS do if v < LIVE_BINS[i] then return i end end
  return #LIVE_BINS + 1
end

local function liveUpdate(s)
  if not live then resetLive() end
  live.n = live.n + 1
  live.vsum = live.vsum + s.v
  if s.v > live.vmax then live.vmax = s.v end
  local function sh(k) return (s.s and s.s[k]) or 0 end
  local fl, fr = sh("shock_FL"), sh("shock_FR")
  local rl, rr = sh("shock_RL"), sh("shock_RR")
  live.rmsF = live.rmsF + ((math.abs(fl) + math.abs(fr)) * 0.5) ^ 2
  live.rmsR = live.rmsR + ((math.abs(rl) + math.abs(rr)) * 0.5) ^ 2
  for _, k in ipairs({ "FL", "FR", "RL", "RR" }) do
    local ld = (s.w and s.w[k] and s.w[k].ld) or 0
    live.load[k] = live.load[k] + ld
    live.loadNow[k] = math.floor(ld + 0.5)
    if ld < 500 then live.air[k] = live.air[k] + 1 end
  end
  local function hm(h, v)
    if h then local i = binOf(math.abs(v)) h[i] = (h[i] or 0) + 1 end
  end
  hm(live.hFc, fl)
  hm(live.hFr, fr)
  hm(live.hRc, rl)
  hm(live.hRr, rr)
end

-- ── 车辆探针 ────────────────────────────────────────────────────────────
local PROBE = [[
local function N(x) local v = tonumber(x) if v == nil then return 0 end return v end
local p = obj:getPosition()
local vel = obj:getVelocity()
local r, pi, yw = obj:getRollPitchYaw()
local ra, pa, ya = obj:getRollPitchYawAngularVelocity()
local w, s, gml = {}, {}, {}
for _, wd in pairs(wheels.wheels) do
  w[#w + 1] = string.format('%s,%.3f,%.0f', tostring(wd.name), N(wd.wheelSpeed), N(wd.downForce))
  gml[#gml + 1] = tostring(wd.groundModel or '?')
end
for _, b in pairs(v.data.beams) do
  local n = tostring(b.name or ''):lower()
  if (n:find('shock') or n:find('damper') or n:find('damp')) and (b.beamDamp or 0) > 0.5 then
    local g = nil
    if n:find('fl') then g = 'FL' elseif n:find('fr') then g = 'FR'
    elseif n:find('rl') then g = 'RL' elseif n:find('rr') then g = 'RR' end
    if g then
      local ok, bv = pcall(obj.getBeamVelocity, obj, b.cid)
      s[#s + 1] = string.format('shock_%s,%.4f', g, N((ok and bv) or 0))
    end
  end
end
local ev = (electrics and electrics.values) or {}
-- 刹车输入在不同车/版本里字段名不一样，全试一遍
local brkPa = ev.braking
if brkPa == nil then brkPa = ev.brake end
if brkPa == nil then brkPa = ev.brakeInput end
if brkPa == nil then brkPa = ev.serviceBrake end
local parts = {
  string.format('%.3f', N(p.x)), string.format('%.3f', N(p.y)), string.format('%.3f', N(p.z)),
  string.format('%.4f', math.sqrt(N(vel.x) ^ 2 + N(vel.y) ^ 2 + N(vel.z) ^ 2)),
  string.format('%.4f', N(vel.z)),
  string.format('%.4f', N(ra)), string.format('%.4f', N(pa)), string.format('%.4f', N(ev.steering)),
  string.format('%q', table.concat(w, '|')),
  string.format('%q', table.concat(s, '|')),
  string.format('%.4f', N(ev.throttle)), string.format('%.4f', N(brkPa)),
  string.format('%q', table.concat(gml, '|')),
  string.format('%.1f', N(ev.rpm)), string.format('%.3f', N(ev.engineTorque)), string.format('%.0f', N(ev.gear)),
  "''",
}
obj:queueGameEngineLua('extensions.roadProfile.push(' .. table.concat(parts, ',') .. ')')
]]

-- ── 接收采样点 ──────────────────────────────────────────────────────────
function M.push(x, y, z, speed, vz, ra, pa, steer, wheelStr, shockStr, thr, brk, gmStr, rpm, tq, gear, axStr)
  if not recording then return end
  idx = idx + 1
  if lastPos then
    local dx, dy = x - lastPos[1], y - lastPos[2]
    dist = dist + math.sqrt(dx * dx + dy * dy)
  end
  lastPos = { x, y }
  local w, s = {}, {}
  for part in string.gmatch(wheelStr or "", "[^|]+") do
    local n, sp, ld = part:match("([^,]+),([^,]+),([^,]+)")
    if n then w[n] = { sp = tonumber(sp) or 0, ld = tonumber(ld) or 0 } end
  end
  for part in string.gmatch(shockStr or "", "[^|]+") do
    local n, bv = part:match("([^,]+),([^,]+)")
    if n then s[n] = tonumber(bv) or 0 end
  end
  samples[idx] = {
    t = idx / HZ, d = dist, x = x, y = y, z = z, v = speed, vz = vz,
    ra = ra, pa = pa, st = steer, w = w, s = s,
    thr = tonumber(thr) or 0, brk = tonumber(brk) or 0,
    gm = gmStr or "", rpm = tonumber(rpm) or 0,
    tq = tonumber(tq) or 0, gear = tonumber(gear) or 0, ax = axStr or "",
  }
  liveUpdate(samples[idx])
  if idx > MAX_SAMPLES then
    table.remove(samples, 1)
    idx = idx - 1
  end
end

-- ── 给游戏内面板 ────────────────────────────────────────────────────────
function M.getLive()
  local ok, res = pcall(function()
    if not live then resetLive() end
    local n = math.max(live.n, 1)
    local function pct(h)
      local t = {}
      for i = 1, #LIVE_BINS + 1 do t[i] = math.floor((h[i] or 0) / n * 100 + 0.5) end
      return t
    end
    local avg, air = {}, {}
    for _, k in ipairs({ "FL", "FR", "RL", "RR" }) do
      avg[k] = math.floor(live.load[k] / n + 0.5)
      air[k] = math.floor(live.air[k] / n * 1000 + 0.5) / 10
    end
    return {
      recording = recording and 1 or 0,
      samples = #samples,
      dist = math.floor(dist + 0.5),
      level = levelName(),
      veh = vehInfo.modelName, cfg = vehInfo.cfgName,
      vehKey = vehInfo.model, cfgKey = vehInfo.cfgKey,
      tune = "", n = live.n,
      vAvg = math.floor(live.vsum / n * 10 + 0.5) / 10,
      vMax = math.floor(live.vmax * 10 + 0.5) / 10,
      rmsF = math.floor(math.sqrt(live.rmsF / n) * 1000 + 0.5) / 1000,
      rmsR = math.floor(math.sqrt(live.rmsR / n) * 1000 + 0.5) / 1000,
      hFc = pct(live.hFc), hFr = pct(live.hFr), hRc = pct(live.hRc), hRr = pct(live.hRr),
      bins = LIVE_BINS, load = avg, loadNow = live.loadNow, airPct = air, compSign = 1,
    }
  end)
  if ok and type(res) == "table" then
    -- ★ 关键：把所有字段压成 JSON 字符串放进 tune（旧版唯一被证明能传到面板的格式）
    local enc = jsonEncode and pcall(jsonEncode, res)
    if enc then
      local okj, s = pcall(jsonEncode, res)
      if okj and type(s) == "string" then
        res.tune = s
      end
    end
    if not _rpLiveLogged then
      _rpLiveLogged = true
      local keys = {}
      for k, v in pairs(res) do
        keys[#keys + 1] = k .. "=" .. type(v)
      end
      print("[roadProfile][live] 返回 " .. #keys .. " 个字段: " .. table.concat(keys, " "))
    end
    return res
  end
  return { recording = recording and 1 or 0, samples = #samples, dist = math.floor(dist + 0.5),
           level = "-", veh = "?", cfg = "?", vehKey = "", cfgKey = "", tune = "",
           n = 0, vAvg = 0, vMax = 0, rmsF = 0, rmsR = 0,
           hFc = {}, hFr = {}, hRc = {}, hRr = {}, bins = LIVE_BINS,
           load = {}, loadNow = {}, airPct = {}, compSign = 1 }
end

-- ── 控制 ────────────────────────────────────────────────────────────────
function M.start()
  samples, idx, dist, lastPos = {}, 0, 0, nil
  resetLive()
  recording = true
  print("[roadProfile] 开始记录（10 Hz）")
  return true
end

function M.stop()
  recording = false
  print("[roadProfile] 停止记录，共 " .. #samples .. " 点")
  return true
end

function M.toggle()
  if recording then M.stop() else M.start() end
  return true
end

local function stamp()
  local t = os.date("*t")
  return string.format("%04d%02d%02d_%02d%02d%02d", t.year, t.month, t.day, t.hour, t.min, t.sec)
end

local function vehTag()
  local a = tostring(vehInfo.model or "car"):gsub("[^%w_%-]", "")
  local b = tostring(vehInfo.cfgKey or ""):gsub("[^%w_%-]", "")
  if b == "" then return a end
  return a .. "_" .. b
end

local function dumpImpl(baseName, quiet)
  local n = #samples
  if n < 10 then
    if not quiet then print("[roadProfile] 采样太少，不导出") end
    return nil
  end
  local base = baseName or ("roadProfile_" .. vehTag() .. "_" .. stamp())
  local csv, txt = base .. ".csv", base .. ".txt"

  local c = io.open(csv, "w")
  if not c then
    print("[roadProfile] 无法写文件: " .. csv)
    return nil
  end
  c:write("t,d,x,y,z,v,vz,rollAV,pitchAV,steer,terrainH,FLsp,FLld,FRsp,FRld,RLsp,RLld,RRsp,RRld,FLsv,FRsv,RLsv,RRsv,thr,brk,gm,rpm,tq,gear,ax\n")
  for i = 1, n do
    local s = samples[i]
    local function W(k, f) return (s.w and s.w[k] and s.w[k][f]) or 0 end
    local function S(k) return (s.s and s.s["shock_" .. k]) or 0 end
    c:write(string.format(
      "%.2f,%.1f,%.2f,%.2f,%.2f,%.2f,%.3f,%.4f,%.4f,%.3f,0,%.3f,%.0f,%.3f,%.0f,%.3f,%.0f,%.3f,%.0f,%.4f,%.4f,%.4f,%.4f,%.3f,%.3f,%q,%.1f,%.3f,%.0f,%q\n",
      s.t, s.d, s.x, s.y, s.z, s.v, s.vz, s.ra, s.pa, s.st,
      W("FL", "sp"), W("FL", "ld"), W("FR", "sp"), W("FR", "ld"),
      W("RL", "sp"), W("RL", "ld"), W("RR", "sp"), W("RR", "ld"),
      S("FL"), S("FR"), S("RL"), S("RR"),
      s.thr, s.brk, s.gm, s.rpm, s.tq, s.gear, s.ax))
  end
  c:close()

  local vsum, vmax = 0, 0
  for i = 1, n do
    vsum = vsum + samples[i].v
    if samples[i].v > vmax then vmax = samples[i].v end
  end
  local lines = {
    "=== 路面数据抓包 / 调车摘要 ===",
    string.format("车辆      : %s  (%s)", vehInfo.modelName, vehInfo.model),
    string.format("配置      : %s   [%s]", vehInfo.cfgName, vehInfo.cfgKey),
    "悬挂类型  : 原厂零件(只能换零件/游戏内调校)",
    string.format("地图      : %s", levelName()),
    string.format("采样      : %d 点 @ %d Hz  时长 %.1f s", n, HZ, n / HZ),
    string.format("里程      : %.0f m   车速 平均 %.1f / 最大 %.1f m/s (%.0f / %.0f km/h)",
      dist, vsum / n, vmax, vsum / n * 3.6, vmax * 3.6),
    "",
  }
  writeFile(txt, table.concat(lines, "\n") .. "\n")
  print(string.format("[roadProfile] 已导出: %s | %s", csv, txt))
  return csv
end

function M.dump(baseName, quiet)
  local ok, res = pcall(dumpImpl, baseName, quiet)
  if not ok then
    print("[roadProfile] 导出出错: " .. tostring(res))
    writeFile("roadProfile_error.txt", "dump error: " .. tostring(res) .. "\n")
    return nil
  end
  return res
end

-- ── 云辇控制（面板按钮调用）────────────────────────────────────────────
local YC = {
  jump        = "yunnianJump:trigger()",
  pivot_ccw   = "yunnianTankTurn:toggle(-1)",
  pivot_cw    = "yunnianTankTurn:toggle(1)",
  height_up   = "yunnianSuspension:stepLevel(1)",
  height_down = "yunnianSuspension:stepLevel(-1)",
  height_auto = "yunnianSuspension:autoLevel()",
  dance       = "yunnianSuspension:dance()",
  cdc         = "yunnianCDC:toggleEnabled()",
}

function M.ync(cmd, arg)
  local snippet = YC[cmd]
  if not snippet then
    print("[roadProfile] 未知云辇命令: " .. tostring(cmd))
    return false
  end
  -- 特殊：stepLevel 允许外部传方向
  if cmd == "height_up" or cmd == "height_down" then
    local d = tonumber(arg)
    if d == 0 or (cmd == "height_down" and d and d > 0) then d = -math.abs(d) end
    snippet = "yunnianSuspension:stepLevel(" .. tostring(d or (cmd == "height_up" and 1 or -1)) .. ")"
  end
  local veh = playerVeh()
  if not veh then
    print("[roadProfile] 云辇命令失败：没有玩家车辆")
    return false
  end
  local cmdstr = [[
    local ok, err = pcall(function()
      local c = controller.getControllerSafe(']] .. snippet:match("^([^:]+)") .. [[')
      if not c then error('控制器不存在') end
      c.]] .. snippet:match(":(.+)$") .. [[
    end)
    if not ok then print('[云辇] 执行失败: ' .. tostring(err)) end
  ]]
  pcall(veh.queueLuaCommand, veh, cmdstr)
  print("[roadProfile] 云辇命令: " .. cmd)
  return true
end

-- 当前车是否带云辇：读车辆控制器写的 electrics.values.yunnian_avail
local ynCache, ynCacheT = false, -1
function M.getAvail()
  local nowT = (os and os.clock and os.clock()) or 0
  if nowT - ynCacheT < 0.5 then return ynCache end
  ynCacheT = nowT
  ynCache = false
  local veh = playerVeh()
  if not veh then return false end
  pcall(function()
    local ev = veh:getElectrics()
    if ev and ev.values and (tonumber(ev.values.yunnian_avail) or 0) > 0 then
      ynCache = true
    end
  end)
  return ynCache
end

function M.status()
  return { recording = recording, samples = #samples, dist = dist }
end

-- ── 每帧 ────────────────────────────────────────────────────────────────
local probeTimer, slowTimer = 0, 0

local liveTimer = 0
function M.onUpdate(dtReal, dtSim, dt)
  -- 每 0.3 秒把实时数据推给游戏内面板（比 engineLua 回调可靠）
  liveTimer = liveTimer + (dtReal or 0)
  if liveTimer > 0.3 then
    liveTimer = 0
    pcall(function() guihooks.trigger('roadProfileLive', M.getLive()) end)
  end
  slowTimer = slowTimer + (dtReal or 0)
  if slowTimer > 1.0 then
    slowTimer = 0

    local veh = playerVeh()
    if veh then
      -- ★ 换车检测：连续记录时换了车 -> 先把旧车数据导出，再重新开始记
      pcall(function()
        local vid = veh:getID()
        if lastVehId and vid ~= lastVehId then
          if recording or #samples > 0 then
            print(string.format("[roadProfile] 检测到换车（%s -> %s），导出旧数据并重新记录",
              tostring(vehInfo.model), tostring(vid)))
            if #samples > 200 then pcall(M.dump, nil, true) end
            pcall(M.start)
          end
        end
        lastVehId = vid
      end)

      pcall(function()
        local vid = veh:getID()
        local d = core_vehicles and core_vehicles.getVehicleDetails and core_vehicles.getVehicleDetails(vid)
        if d and d.model then
          vehInfo.model = (d.model and d.model.key) or vehInfo.model
          vehInfo.modelName = (d.model and d.model.Name) or vehInfo.model
          vehInfo.cfgKey = (d.config and d.config.key) or ""
          vehInfo.cfgName = (d.config and d.config.Name) or ""
        end
      end)
    end

    writeFile(F_STATUS, string.format(
      "recording=%d\nsamples=%d\ndist=%.1f\nlevel=%s\ndumped=%d\nprobeerr=%d\nfallback=0\n" ..
      "vehmodel=%s\nvehname=%s\ncfgkey=%s\ncfgname=%s\n",
      recording and 1 or 0, #samples, dist, levelName(), #samples, probeErr,
      tostring(vehInfo.model), tostring(vehInfo.modelName),
      tostring(vehInfo.cfgKey), tostring(vehInfo.cfgName)))

    local cmd = readFile(F_CMD)
    if cmd and cmd ~= "" and cmd ~= lastCmd then
      lastCmd = cmd
      local c = cmd:match("^%d+,(.+)$") or cmd
      c = c:gsub("%s+", "")
      if c == "start" then M.start()
      elseif c == "stop" then M.stop()
      elseif c == "toggle" then M.toggle()
      elseif c == "dump" then M.dump(nil) end
    end
  end

  if not recording then return end
  probeTimer = probeTimer + (dtReal or 0)
  if probeTimer < PROBE_TIMER then return end
  probeTimer = 0
  local veh = playerVeh()
  if not veh then return end
  local ok, err = pcall(veh.queueLuaCommand, veh, PROBE)
  if not ok then
    probeErr = probeErr + 1
    if probeErr <= 3 then print("[roadProfile] 探针下发失败: " .. tostring(err)) end
  end
end

-- ── 退出 ────────────────────────────────────────────────────────────────
local shuttingDown = false
local function shutdown(reason)
  if shuttingDown then return end
  shuttingDown = true
  pcall(function()
    local had = #samples
    if recording and had > 200 then M.dump(nil, true) end
    recording = false
    writeFile(F_STATUS, string.format(
      "recording=0\nsamples=%d\ndist=%.1f\nlevel=%s\nclosed=1\nreason=%s\n",
      had, dist, levelName(), tostring(reason)))
  end)
end

function M.onClientEnd() shutdown("clientEnd") end
function M.onExtensionUnloaded() shutdown("unloaded") end
function M.onExtensionLoaded()
  print("[roadProfile] 路面抓包就绪（重写版）: extensions.roadProfile.start()")
end

return M
