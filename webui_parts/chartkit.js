/* ============================================================================
   ChartKit —— 车辆数据分析器 · 共用折线图引擎（canvas，无依赖）
   ----------------------------------------------------------------------------
   用法：
     var chart = ChartKit.mount(document.getElementById('chart-xyz'), {
       series: [
         {name:'高程', color:'#5B8FB9', data:[[d,z],...], fill:true, width:2},
         {name:'车速', color:'#D9A24A', data:[[d,v],...], axis:'y2', dash:true}
       ],
       x:  {label:'里程 (m)', fmt:function(v){return v.toFixed(0)+' m';}},
       y1: {label:'高程 (m)'},
       y2: {label:'车速 (km/h)'},          // 可选，双轴
       gap: 0,                             // 数据有断点时可指定，>gap 断线
       fillTop: 'rgba(91,143,185,.20)',    // 面积填充顶部颜色（fill:true 时）
       fillBottom: 'rgba(91,143,185,0)'    // 面积填充底部颜色
     });
   交互：滚轮缩放（以光标为锚点）、左键拖拽平移、双击复位、悬停十字线 + 数值提示。
   chart.reset() 复位；chart.destroy() 销毁；chart.range() 返回 {x0,x1}。
   ========================================================================== */
(function () {
  'use strict';

  var TIP_ID = 'chart-tip';
  var DEFAULTS = {
    margin: { l: 56, r: 56, t: 16, b: 36 },
    gridColor: 'rgba(91,143,185,.13)',
    axisColor: 'rgba(91,143,185,.35)',
    tickColor: '#8496A7',
    bg: 'rgba(255,255,255,0)',
    hover: true,             // 鼠标跟随读数（十字线 + 数值气泡）
    minSpanRatio: 0.012,     // 最小缩放窗口 = 全长的 1.2%
    wheelFactor: 1.22
  };

  function tipEl() {
    var el = document.getElementById(TIP_ID);
    if (!el) {
      el = document.createElement('div');
      el.id = TIP_ID;
      document.body.appendChild(el);
    }
    return el;
  }

  function fmtNum(v) {
    if (v === null || v === undefined || isNaN(v)) return '–';
    var a = Math.abs(v);
    if (a >= 10000) return (v / 1000).toFixed(0) + 'k';
    if (a >= 1000) return (v / 1000).toFixed(1) + 'k';
    if (Math.abs(v - Math.round(v)) < 1e-9) return String(Math.round(v));
    if (a >= 100) return v.toFixed(0);
    if (a >= 10) return v.toFixed(1);
    if (a >= 1) return v.toFixed(2);
    return v.toFixed(3);
  }

  function padY(min, max) {
    if (!(max > min)) { max = min + 1; }
    var p = (max - min) * 0.10;
    return [min - p, max + p];
  }

  function mount(el, opts) {
    if (!el) return null;
    var o = Object.assign({}, DEFAULTS, opts || {});
    o.series = (o.series || []).filter(function (s) { return s && s.data && s.data.length; });
    if (!o.series.length) return null;
    var self = {};
    function isOwner() { return window.__ckHoverOwner === self; }
    function clearOwner() { if (isOwner()) window.__ckHoverOwner = null; }

    var canvas = document.createElement('canvas');
    canvas.className = 'ck-canvas';
    el.appendChild(canvas);
    var ctx = canvas.getContext('2d');
    var tip = tipEl();

    var dataX = [];
    o.series.forEach(function (s) {
      s.data.forEach(function (p) { if (p && p.length > 1 && isFinite(p[0])) dataX.push(p[0]); });
    });
    if (!dataX.length) return null;
    dataX.sort(function (a, b) { return a - b; });
    var fullX0 = dataX[0], fullX1 = dataX[dataX.length - 1];
    var view = { x0: fullX0, x1: fullX1 };
    var hoverX = null;
    var dragging = false, dragStart = null, dragView = null;
    var W = 0, H = 0, dpr = 1;

    function visibleBounds() {
      var lo = view.x0, hi = view.x1;
      var xr = [Infinity, -Infinity];
      var y1r = [Infinity, -Infinity], y2r = [Infinity, -Infinity];
      o.series.forEach(function (s) {
        var ys = s.axis === 'y2' ? y2r : y1r;
        var arr = s.data;
        for (var i = 0; i < arr.length; i++) {
          var p = arr[i];
          if (!p || !isFinite(p[0]) || !isFinite(p[1])) continue;
          if (p[0] < lo || p[0] > hi) continue;
          if (p[0] < xr[0]) xr[0] = p[0];
          if (p[0] > xr[1]) xr[1] = p[0];
          if (p[1] < ys[0]) ys[0] = p[1];
          if (p[1] > ys[1]) ys[1] = p[1];
        }
      });
      if (!isFinite(y1r[0])) y1r = [0, 1];
      if (!isFinite(y2r[0])) y2r = null;
      return { x: [lo, hi], y1: padY(y1r[0], y1r[1]), y2: y2r ? padY(y2r[0], y2r[1]) : null };
    }

    function resize() {
      var r = el.getBoundingClientRect();
      if (r.width < 40 || r.height < 40) return;
      dpr = window.devicePixelRatio || 1;
      W = Math.round(r.width);
      H = Math.round(r.height);
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      canvas.style.width = W + 'px';
      canvas.style.height = H + 'px';
      draw();
    }

    function xToPx(x, b) {
      var m = o.margin;
      var inner = W - m.l - m.r;
      return m.l + (x - b.x[0]) / (b.x[1] - b.x[0] || 1) * inner;
    }
    function pxToX(px, b) {
      var m = o.margin;
      var inner = W - m.l - m.r;
      return b.x[0] + (px - m.l) / inner * (b.x[1] - b.x[0]);
    }
    function yToPx(y, rg) {
      var m = o.margin;
      var inner = H - m.t - m.b;
      return m.t + (1 - (y - rg[0]) / (rg[1] - rg[0] || 1)) * inner;
    }

    function niceTicks(lo, hi, n) {
      var span = hi - lo;
      if (!(span > 0)) return [lo];
      var step = Math.pow(10, Math.floor(Math.log10(span / n)));
      var err = span / n / step;
      if (err >= 7.5) step *= 10;
      else if (err >= 3.5) step *= 5;
      else if (err >= 1.5) step *= 2;
      var out = [], v = Math.ceil(lo / step) * step;
      for (var i = 0; v <= hi + step * 1e-6 && i < 40; i++, v += step) out.push(v);
      return out;
    }

    function draw() {
      if (!W || !H) return;
      var b = visibleBounds();
      var m = o.margin;
      var innerW = W - m.l - m.r;
      var innerH = H - m.t - m.b;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);

      // ── 网格 + y 轴刻度（左/右）
      var yTicks = niceTicks(b.y1[0], b.y1[1], 4);
      ctx.font = '11px "Microsoft YaHei UI","Segoe UI",sans-serif';
      ctx.textBaseline = 'middle';
      yTicks.forEach(function (v) {
        var py = yToPx(v, b.y1);
        if (py < m.t - 1 || py > H - m.b + 1) return;
        ctx.strokeStyle = o.gridColor;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(m.l, Math.round(py) + .5);
        ctx.lineTo(W - m.r, Math.round(py) + .5);
        ctx.stroke();
        ctx.fillStyle = o.tickColor;
        ctx.textAlign = 'right';
        ctx.fillText(fmtNum(v), m.l - 9, py);
      });
      if (b.y2) {
        var y2Ticks = niceTicks(b.y2[0], b.y2[1], 4);
        y2Ticks.forEach(function (v) {
          var py = yToPx(v, b.y2);
          if (py < m.t - 1 || py > H - m.b + 1) return;
          ctx.fillStyle = o.tickColor;
          ctx.textAlign = 'left';
          ctx.fillText(fmtNum(v), W - m.r + 9, py);
        });
      }
      // ── x 轴刻度
      var xTicks = niceTicks(b.x[0], b.x[1], 6);
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      xTicks.forEach(function (v) {
        var px = xToPx(v, b);
        if (px < m.l - 1 || px > W - m.r + 1) return;
        ctx.strokeStyle = o.gridColor;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(Math.round(px) + .5, m.t);
        ctx.lineTo(Math.round(px) + .5, H - m.b);
        ctx.stroke();
        ctx.fillStyle = o.tickColor;
        ctx.fillText(fmtNum(v), px, H - m.b + 9);
      });
      // ── 轴标签
      ctx.fillStyle = '#8496A7';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';
      if (o.x && o.x.label) ctx.fillText(o.x.label, m.l + innerW / 2, H - 2);
      ctx.save();
      ctx.translate(13, m.t + innerH / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.textBaseline = 'middle';
      if (o.y1 && o.y1.label) ctx.fillText(o.y1.label, 0, 0);
      ctx.restore();
      if (b.y2 && o.y2 && o.y2.label) {
        ctx.save();
        ctx.translate(W - 12, m.t + innerH / 2);
        ctx.rotate(Math.PI / 2);
        ctx.textBaseline = 'middle';
        ctx.fillText(o.y2.label, 0, 0);
        ctx.restore();
      }

      // ── 数据线
      ctx.save();
      ctx.beginPath();
      ctx.rect(m.l, m.t - 3, innerW, innerH + 6);
      ctx.clip();
      o.series.forEach(function (s) {
        var rg = s.axis === 'y2' ? b.y2 : b.y1;
        if (!rg) return;
        var pts = [], lastX = null, broken = false;
        s.data.forEach(function (p) {
          if (!p || !isFinite(p[0]) || !isFinite(p[1])) return;
          if (p[0] < b.x[0] - 1e-9) return;
          if (p[0] > b.x[1] + 1e-9) return;
          if (o.gap && lastX !== null && (p[0] - lastX) > o.gap) broken = true;
          lastX = p[0];
          pts.push([xToPx(p[0], b), yToPx(p[1], rg), broken]);
          broken = false;
        });
        if (pts.length < 2) return;
        ctx.beginPath();
        var started = false;
        pts.forEach(function (q) {
          if (!started || q[2]) { ctx.moveTo(q[0], q[1]); started = true; }
          else ctx.lineTo(q[0], q[1]);
        });
        if (s.dash) {
          ctx.setLineDash([5, 4]);
        }
        ctx.strokeStyle = s.color || '#5B8FB9';
        ctx.lineWidth = s.width || 2;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.stroke();
        ctx.setLineDash([]);
        if (s.fill) {
          // 面积填到 y 轴底部或 0（若 0 在范围内）
          var bottomY = (b.y1[0] <= 0 && b.y1[1] >= 0) ? yToPx(0, rg) : yToPx(rg[0], rg);
          var first = pts[0], last = pts[pts.length - 1];
          ctx.beginPath();
          ctx.moveTo(first[0], bottomY);
          pts.forEach(function (q) { ctx.lineTo(q[0], q[1]); });
          ctx.lineTo(last[0], bottomY);
          ctx.closePath();
          var grad = ctx.createLinearGradient(0, m.t, 0, H - m.b);
          grad.addColorStop(0, s.fillTop || 'rgba(91,143,185,.28)');
          grad.addColorStop(1, s.fillBottom || 'rgba(91,143,185,0)');
          ctx.fillStyle = grad;
          ctx.fill();
        }
      });
      ctx.restore();

      // ── 悬停十字线 & 数值点
      if (hoverX !== null && hoverX >= b.x[0] && hoverX <= b.x[1]) {
        var hx = xToPx(hoverX, b);
        ctx.strokeStyle = 'rgba(31,46,60,.35)';
        ctx.setLineDash([4, 3]);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(hx + .5, m.t);
        ctx.lineTo(hx + .5, H - m.b);
        ctx.stroke();
        ctx.setLineDash([]);
        o.series.forEach(function (s) {
          var rg = s.axis === 'y2' ? b.y2 : b.y1;
          if (!rg) return;
          var p = nearest(s.data, hoverX);
          if (!p) return;
          var py = yToPx(p[1], rg);
          ctx.beginPath();
          ctx.arc(xToPx(p[0], b), py, 3.2, 0, Math.PI * 2);
          ctx.fillStyle = '#fff';
          ctx.fill();
          ctx.strokeStyle = s.color;
          ctx.lineWidth = 2;
          ctx.stroke();
        });
      }
    }

    function nearest(data, x) {
      if (!data || !data.length) return null;
      var lo = 0, hi = data.length - 1;
      if (x <= data[0][0]) return data[0];
      if (x >= data[hi][0]) return data[hi];
      while (hi - lo > 1) {
        var mid = (lo + hi) >> 1;
        if (data[mid][0] < x) lo = mid; else hi = mid;
      }
      return Math.abs(data[lo][0] - x) <= Math.abs(data[hi][0] - x) ? data[lo] : data[hi];
    }

    function unitOf(s) {
      if (s.unit) return ' ' + s.unit;
      var lab = s.axis === 'y2' ? (o.y2 && o.y2.label) : (o.y1 && o.y1.label);
      var m = /[（(]([^）)]+)[）)]\s*$/.exec(lab || '');
      return m ? ' ' + m[1] : '';
    }

    function showTip(clientX, clientY, b) {
      if (!o.hover || hoverX === null) return;
      var lines = o.series.map(function (s) {
        var p = nearest(s.data, hoverX);
        return p ? '<span class="ck-dot" style="background:' + (s.color || '#5B8FB9') + '"></span>' +
          s.name + '：<b>' + fmtNum(p[1]) + '</b>' + unitOf(s) : '';
      }).filter(Boolean);
      if (!lines.length) { tip.style.display = 'none'; return; }
      var xv = (o.x && o.x.fmt) ? o.x.fmt(hoverX) : fmtNum(hoverX);
      tip.innerHTML = '<div class="ck-x">' + xv + '</div>' + lines.join('<br>');
      tip.style.display = 'block';
      var tw = tip.offsetWidth, th = tip.offsetHeight;
      var left = clientX + 16;
      var top = clientY - th - 12;
      if (left + tw > window.innerWidth - 8) left = clientX - tw - 16;
      if (top < 8) top = clientY + 16;
      tip.style.left = left + 'px';
      tip.style.top = top + 'px';
    }

    // ── 事件
    function onWheel(e) {
      e.preventDefault();
      var r = canvas.getBoundingClientRect();
      var b = visibleBounds();
      var mouseX = e.clientX - r.left;
      var anchorX = pxToX(mouseX, b);
      var span = view.x1 - view.x0;
      var minSpan = (fullX1 - fullX0) * o.minSpanRatio;
      var factor = e.deltaY > 0 ? o.wheelFactor : 1 / o.wheelFactor;
      var newSpan = Math.max(minSpan, Math.min(fullX1 - fullX0, span * factor));
      var ratio = (anchorX - view.x0) / span;
      var x0 = anchorX - newSpan * ratio;
      var x1 = x0 + newSpan;
      if (x0 < fullX0) { x0 = fullX0; x1 = fullX0 + newSpan; }
      if (x1 > fullX1) { x1 = fullX1; x0 = fullX1 - newSpan; }
      view.x0 = x0; view.x1 = x1;
      draw();
      if (isOwner()) {
        clearOwner();
        if (tip) tip.style.display = 'none';
      }
    }
    function onDown(e) {
      if (e.button !== 0) return;
      dragging = true;
      dragStart = e.clientX;
      dragView = { x0: view.x0, x1: view.x1 };
      canvas.classList.add('ck-dragging');
      if (isOwner()) {
        clearOwner();
        if (tip) tip.style.display = 'none';
      }
    }
    function hideTip() {
      clearOwner();
      hoverX = null;
      if (tip) tip.style.display = 'none';
      draw();
    }
    function onMove(e) {
      var r = canvas.getBoundingClientRect();
      var inside = e.clientX >= r.left && e.clientX <= r.right &&
                   e.clientY >= r.top && e.clientY <= r.bottom;
      if (dragging && dragStart !== null) {
        var span = dragView.x1 - dragView.x0;
        var delta = (e.clientX - dragStart) / Math.max(1, (W - o.margin.l - o.margin.r)) * span;
        var x0 = dragView.x0 - delta, x1 = dragView.x1 - delta;
        if (x0 < fullX0) { x0 = fullX0; x1 = fullX0 + span; }
        if (x1 > fullX1) { x1 = fullX1; x0 = fullX1 - span; }
        view.x0 = x0; view.x1 = x1;
        draw();
        if (tip) tip.style.display = 'none';
        return;
      }
      // ★ 页面隐藏（切走了）的占位画布不参与，否则会把当前页的读数气泡抢掉
      if (!canvas.isConnected || el.clientWidth < 20 || el.clientHeight < 20) return;
      // ★ 鼠标不在画布上就收起读数（窗口 mousemove 全局监听，必须自己判边界）
      if (!inside) {
        if (isOwner()) hideTip();
        return;
      }
      window.__ckHoverOwner = self;
      var b = visibleBounds();
      hoverX = pxToX(e.clientX - r.left, b);
      draw();
      showTip(e.clientX, e.clientY, b);
    }
    function onUp() {
      dragging = false; dragStart = null; dragView = null;
      canvas.classList.remove('ck-dragging');
    }
    function onLeave() {
      hoverX = null; dragView = null; dragging = false;
      canvas.classList.remove('ck-dragging');
      if (isOwner()) {
        clearOwner();
        if (tip) tip.style.display = 'none';
      }
      draw();
    }
    function onDbl(e) {
      e.preventDefault();
      reset();
    }

    canvas.addEventListener('wheel', onWheel, { passive: false });
    canvas.addEventListener('mousedown', onDown);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    canvas.addEventListener('mouseleave', onLeave);
    canvas.addEventListener('dblclick', onDbl);
    // 鼠标离开整个文档 / 窗口失焦时也收起
    document.addEventListener('mouseleave', onLeave);
    window.addEventListener('blur', onLeave);

    var ro = null;
    if (window.ResizeObserver) {
      ro = new ResizeObserver(function () { resize(); });
      ro.observe(el);
    } else {
      window.addEventListener('resize', resize);
    }

    function reset() {
      view.x0 = fullX0; view.x1 = fullX1;
      hoverX = null;
      clearOwner();
      draw();
      if (tip) tip.style.display = 'none';
    }

    function destroy() {
      clearOwner();
      if (ro) ro.disconnect();
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('mousedown', onDown);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      canvas.removeEventListener('mouseleave', onLeave);
      canvas.removeEventListener('dblclick', onDbl);
      document.removeEventListener('mouseleave', onLeave);
      window.removeEventListener('blur', onLeave);
      if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
    }

    resize();
    // 页面隐藏时尺寸可能为 0，等布局稳定再补一次
    setTimeout(resize, 60);
    return { reset: reset, destroy: destroy, range: function () { return { x0: view.x0, x1: view.x1 }; }, resize: resize };
  }

  window.ChartKit = { mount: mount, fmtNum: fmtNum };
})();
