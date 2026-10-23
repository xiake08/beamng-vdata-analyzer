-- 自动加载「路面数据抓包」扩展（对所有车生效，不改任何车辆文件）
-- BeamNG 启动时会执行 scripts/ 下所有 modScript.lua，这里把扩展挂起来。
-- 注意：只加载，不自动开始记录 —— 由面板的「开始」按钮或外部程序触发 start()
extensions.load('roadProfile')
