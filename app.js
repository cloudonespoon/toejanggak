/* 퇴장각 — 올림픽공원 공연 퇴장 가이드 (정적 웹, 데이터: data.js) */
(function () {
  "use strict";
  const SHOWS = (window.SHOWS || []).slice().sort((a, b) => a.date < b.date ? 1 : -1);
  const MODEL = window.MODEL || {};
  const INSIGHT = window.INSIGHT || {};
  const GATES = ["동2문", "남2문", "북2문"];
  const GVAR = { "동2문": "--g-east", "남2문": "--g-south", "북2문": "--g-north" };
  const $ = (s, el = document) => el.querySelector(s);

  // ---------- 유틸 ----------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const nf = (n) => Number(n).toLocaleString("ko-KR");
  const toMin = (hhmm) => { const [h, m] = hhmm.split(":").map(Number); return h * 60 + m; };
  const fromMin = (m) => { m = ((Math.round(m) % 1440) + 1440) % 1440; return String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0"); };
  const addMin = (hhmm, d) => fromMin(toMin(hhmm) + d);
  const dateLabel = (d, w) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))} (${w})`;
  const bucketOf = (aud) => aud >= 10000 ? "big" : aud >= 5000 ? "mid" : "small";

  // ---------- 테마 ----------
  try { const t = localStorage.getItem("theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* ignore */ }
  $("#themeBtn").addEventListener("click", () => {
    const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch (e) { /* ignore */ }
    rerender();
  });

  // ---------- 탭 ----------
  const tabs = [...document.querySelectorAll(".tab")];
  function selectTab(tab) {
    tabs.forEach((t) => {
      const on = t === tab;
      t.setAttribute("aria-selected", on);
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    });
    // 숨겨진 상태에서 그린 그래프는 폭이 0이라, 탭을 열 때 그 탭 내용을 다시 그림
    if (tab.id === "tab-insight") renderInsight();
    if (tab.id === "tab-find" && currentShow) showResult(currentShow);
    if (tab.id === "tab-now" && lastPred) { renderResult($("#pResult"), lastPred, "predict"); renderLive(); }
    try { history.replaceState(null, "", "#" + tab.id.replace("tab-", "")); } catch (e) { /* ignore */ }
  }
  window.addEventListener("hashchange", () => {
    const h = location.hash.slice(1) === "predict" ? "now" : location.hash.slice(1);
    const t = tabs.find((x) => x.id === "tab-" + h);
    if (t) selectTab(t);
  });
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => selectTab(t));
    t.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        const n = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
        n.focus(); selectTab(n);
      }
    });
  });

  // ---------- 선 그래프 (SVG, 크로스헤어 툴팁) ----------
  function lineChart(host, opt) {
    // opt: {labels:[], series:[{name, color, values, width?}], markers:[{i,label}], yTitle, height}
    host.innerHTML = "";
    const W = Math.max(300, Math.round(host.clientWidth || 760));
    const small = W < 520;
    const H = opt.height || (small ? 250 : 300), M = { l: 40, r: small ? 40 : 52, t: 26, b: 34 };
    const iw = W - M.l - M.r, ih = H - M.t - M.b;
    const n = opt.labels.length;
    const ymaxRaw = Math.max(1, ...opt.series.flatMap((s) => s.values));
    const step = niceStep(ymaxRaw / 4);
    const ymax = Math.ceil(ymaxRaw / step) * step;
    const x = (i) => M.l + (n === 1 ? iw / 2 : (i * iw) / (n - 1));
    const y = (v) => M.t + ih - (v / ymax) * ih;
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", opt.aria || "선 그래프");
    svg.tabIndex = 0;
    const mk = (tag, attrs, parent = svg) => { const e = document.createElementNS(ns, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); parent.appendChild(e); return e; };
    const grid = css("--grid"), axis = css("--axis"), muted = css("--text-muted"), sec = css("--text-secondary");
    // 격자 + y축
    for (let v = 0; v <= ymax + 1e-9; v += step) {
      mk("line", { x1: M.l, x2: W - M.r, y1: y(v), y2: y(v), stroke: v === 0 ? axis : grid, "stroke-width": 1 });
      const t = mk("text", { x: M.l - 8, y: y(v) + 4, "text-anchor": "end", "font-size": 12, fill: muted });
      t.textContent = nf(v);
    }
    if (opt.yTitle) { const t = mk("text", { x: M.l - 8, y: M.t - 10, "text-anchor": "end", "font-size": 12, fill: muted }); t.textContent = opt.yTitle; }
    // x축 라벨
    const maxTicks = Math.max(3, Math.floor(iw / 62));
    let every = opt.xEvery || Math.max(1, Math.round(n / 7));
    while (Math.ceil(n / every) > maxTicks) every += opt.xEvery || 1;
    opt.labels.forEach((lb, i) => {
      if (i % every !== 0 && i !== n - 1) return;
      if (i === n - 1 && i % every !== 0 && (n - 1) % every < every * 0.6) return;
      const t = mk("text", { x: x(i), y: H - 10, "text-anchor": "middle", "font-size": 12, fill: muted });
      t.textContent = lb;
    });
    // 마커 (종료 추정 등) — 실선 헤어라인 + 라벨
    (opt.markers || []).forEach((m, mi) => {
      if (m.i < 0 || m.i > n - 1) return;
      if (m.now) { // '지금' 표시: 강조색 점선, 라벨은 그래프 안쪽 위에 둬서 다른 라벨과 겹치지 않게
        const acc = css("--accent");
        mk("line", { x1: x(m.i), x2: x(m.i), y1: M.t, y2: M.t + ih, stroke: acc, "stroke-width": 2, "stroke-dasharray": "4 3" });
        const right = x(m.i) < M.l + iw - 40;
        const t = mk("text", { x: x(m.i) + (right ? 5 : -5), y: M.t + 14, "text-anchor": right ? "start" : "end", "font-size": 12, fill: acc, "font-weight": 700 });
        t.textContent = m.label;
        return;
      }
      mk("line", { x1: x(m.i), x2: x(m.i), y1: M.t - 4, y2: M.t + ih, stroke: sec, "stroke-width": 1, opacity: 0.6 });
      const left = mi === 0 && (opt.markers || []).length > 1; // 첫 마커는 선 왼쪽, 나머지는 오른쪽에 라벨
      const t = mk("text", { x: x(m.i) + (left ? -4 : 4), y: M.t - 8, "text-anchor": left ? "end" : "start", "font-size": 12, fill: sec, "font-weight": 600 });
      t.textContent = m.label;
    });
    // 영역(첫 시리즈만 옅게) + 선
    opt.series.forEach((s, si) => {
      const d = s.values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
      if (opt.area && si === 0) mk("path", { d: d + `L${x(n - 1)},${y(0)}L${x(0)},${y(0)}Z`, fill: s.color, opacity: 0.1 });
      mk("path", { d, fill: "none", stroke: s.color, "stroke-width": s.width || 2, "stroke-linejoin": "round", "stroke-linecap": "round" });
    });
    // 끝점 직접 라벨 (4개 이하, 겹치면 생략)
    if (opt.series.length <= 4 && opt.endLabels !== false) {
      const ends = opt.series.map((s) => ({ s, yy: y(s.values[n - 1]) })).sort((a, b) => a.yy - b.yy);
      let last = -99;
      ends.forEach(({ s, yy }) => {
        if (yy - last < 14) return;
        last = yy;
        const t = mk("text", { x: W - M.r + 4, y: yy + 4, "font-size": 12, fill: sec });
        t.textContent = s.short || s.name;
      });
    }
    // 크로스헤어
    const cross = mk("line", { x1: 0, x2: 0, y1: M.t, y2: M.t + ih, stroke: sec, "stroke-width": 1, opacity: 0 });
    const dots = opt.series.map((s) => mk("circle", { r: 4.5, fill: s.color, stroke: css("--surface-1"), "stroke-width": 2, opacity: 0 }));
    const hit = mk("rect", { x: M.l, y: M.t, width: iw, height: ih, fill: "transparent" });
    host.style.position = "relative";
    host.appendChild(svg);
    const tip = document.createElement("div");
    tip.className = "tip";
    host.appendChild(tip);
    let cur = -1;
    function show(i) {
      cur = Math.max(0, Math.min(n - 1, i));
      cross.setAttribute("x1", x(cur)); cross.setAttribute("x2", x(cur)); cross.setAttribute("opacity", 0.5);
      dots.forEach((d, si) => { d.setAttribute("cx", x(cur)); d.setAttribute("cy", y(opt.series[si].values[cur])); d.setAttribute("opacity", 1); });
      tip.textContent = "";
      const h = document.createElement("div"); h.className = "h"; h.textContent = (opt.tipTitle ? opt.tipTitle(cur) : opt.labels[cur]); tip.appendChild(h);
      opt.series.slice().sort((a, b) => b.values[cur] - a.values[cur]).forEach((s) => {
        const r = document.createElement("div"); r.className = "r";
        const k = document.createElement("i"); k.className = "k"; k.style.background = s.color;
        const nm = document.createElement("span"); nm.textContent = s.name;
        const v = document.createElement("b"); v.textContent = nf(s.values[cur]) + (opt.unit || "");
        r.append(k, nm, v); tip.appendChild(r);
      });
      const rect = svg.getBoundingClientRect();
      const px = (x(cur) / W) * rect.width;
      tip.classList.add("on");
      const tw = tip.offsetWidth;
      tip.style.left = Math.min(rect.width - tw, Math.max(0, px + (px > rect.width / 2 ? -tw - 12 : 12))) + "px";
      tip.style.top = "8px";
    }
    function hide() { cross.setAttribute("opacity", 0); dots.forEach((d) => d.setAttribute("opacity", 0)); tip.classList.remove("on"); }
    hit.addEventListener("pointermove", (e) => {
      const rect = svg.getBoundingClientRect();
      const sx = ((e.clientX - rect.left) / rect.width) * W;
      show(Math.round(((sx - M.l) / iw) * (n - 1)));
    });
    hit.addEventListener("pointerleave", hide);
    svg.addEventListener("focus", () => show(cur < 0 ? (opt.focusIndex ?? 0) : cur));
    svg.addEventListener("blur", hide);
    svg.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight") { show(cur + 1); e.preventDefault(); }
      if (e.key === "ArrowLeft") { show(cur - 1); e.preventDefault(); }
    });
  }
  function niceStep(raw) {
    const p = Math.pow(10, Math.floor(Math.log10(raw)));
    const f = raw / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
  }
  function legend(items, box) {
    return `<div class="legend">${items.map((s) => `<span><i class="${box ? "box" : ""}" style="background:${s.color}"></i>${esc(s.name)}</span>`).join("")}</div>`;
  }

  // ---------- 결과 화면 (실제 공연/예측 공통) ----------
  function bestGate(wait, share) {
    // 종료 후 출차까지 걸린 시간 중앙값이 가장 짧은 출구 (표본 30대 이상)
    const cand = GATES.filter((g) => wait[g] && wait[g].median != null && (wait[g].n == null || wait[g].n >= 30));
    if (!cand.length) return null;
    return cand.reduce((a, b) => (wait[a].median <= wait[b].median ? a : b));
  }

  function renderResult(host, r, mode) {
    // r: {title, dateText, t0, curve:{total, 동2문..}, curveStart, t80, calm, excess, peak5, gates:{g:{share}}, wait:{g:{median}}, aud}
    const i0 = 12; // 곡선에서 t0 위치 (60분/5분)
    const totals = r.curve.total;
    let pk = i0; for (let i = i0; i < totals.length; i++) if (totals[i] > totals[pk]) pk = i;
    const peakTime = addMin(r.t0, (pk - i0) * 5);
    const calmTime = addMin(r.t0, r.calm);
    const best = bestGate(r.wait, r.gates);
    const worst = GATES.reduce((a, b) => (r.gates[a].share >= r.gates[b].share ? a : b));
    const others = GATES.filter((g) => g !== best && r.wait[g] && r.wait[g].median != null);
    const avgOther = others.length ? others.reduce((s, g) => s + r.wait[g].median, 0) / others.length : null;
    const gain = best && avgOther != null ? Math.max(0, Math.round(avgOther - r.wait[best].median)) : null;
    const labels = totals.map((_, i) => addMin(r.curveStart, i * 5));
    const isPred = mode === "predict";

    host.innerHTML = `
      <div class="card" aria-live="polite">
        <div class="verdict">
          <div class="eyebrow">${isPred ? "예측 결과" : "실제 기록"} · ${esc(r.dateText)}</div>
          <h2 style="margin:0">${esc(r.title)}</h2>
          ${r.names && r.names.length > 1 ? `<p class="muted" style="margin:0">같은 날 공원 안 공연: ${r.names.map(esc).join(" · ")}</p>` : ""}
          ${best ? `<div class="big"><span class="key" style="background:var(${GVAR[best]})"></span>${best} 출구로 나가세요</div>
          <p>${isPred ? "비슷한 규모 공연에서" : "이날"} ${best} 출구 이용 차량은 공연이 끝나고 보통 <b>${r.wait[best].median}분</b> 만에 빠져나갔어요${gain ? ` (다른 출구보다 평균 <b>${gain}분</b> 빠름)` : ""}.</p>` : ""}
        </div>
        <div class="timeline" aria-label="퇴장 타임라인">
          <div class="step on"><div class="t">${r.t0}</div><div class="c">공연 종료${isPred ? "" : "(추정)"}</div></div>
          <div class="step on"><div class="t">${peakTime}</div><div class="c">출차 가장 몰림</div></div>
          <div class="step"><div class="t">${calmTime}</div><div class="c">이때부터 한산 (피크의 35% 이하)</div></div>
        </div>
        <div class="tiles">
          <div class="tile"><div class="l">공연 끝나고 몰린 차</div><div class="v">${nf(r.excess)}대</div><div class="s">평소보다 더 나간 차량</div></div>
          <div class="tile"><div class="l">80%가 빠지는 데</div><div class="v">${r.t80}분</div><div class="s">종료 기준</div></div>
          <div class="tile"><div class="l">가장 붐빈 출구</div><div class="v">${worst} ${Math.round(r.gates[worst].share * 100)}%</div><div class="s">3개 출구 중 비율</div></div>
        </div>
      </div>
      <div class="card">
        <h3>출구별 5분당 출차 대수</h3>
        <p class="sub">${isPred ? "2025년 비슷한 규모 공연들의 평균 패턴을 이번 공연에 맞춰 그렸어요." : "세로선은 출차가 급증하기 시작한 시점(공연 종료 추정)과 한산해지는 시점이에요."}${!isPred && r.frac && r.frac < 0.99 ? ` 이날은 전체 출차 기록 중 약 ${Math.round(r.frac * 100)}%만 확보돼 그 비율로 대수를 보정했어요(출구 비율·시간은 영향 없음).` : ""}</p>
        ${legend(GATES.map((g) => ({ name: g + " 출구", color: css(GVAR[g]) })))}
        <div class="chart" id="${mode}-line"></div>
        <details class="table-view"><summary>표로 보기</summary>
          <div class="tbl-scroll"><table class="tbl"><thead><tr><th>시각</th>${GATES.map((g) => `<th>${g}</th>`).join("")}<th>전체</th></tr></thead>
          <tbody>${labels.map((lb, i) => `<tr><td>${lb}</td>${GATES.map((g) => `<td>${nf(r.curve[g][i])}</td>`).join("")}<td>${nf(totals[i])}</td></tr>`).join("")}</tbody></table></div>
        </details>
      </div>
      <div class="card">
        <h3>출구별 비교</h3>
        <p class="sub">공연 종료 후 출차까지 걸린 시간 (중앙값, 공연 전에 들어온 차 기준) · 막대 옆 괄호는 출차 비율</p>
        <div class="gate-bars">${gateBars(r)}</div>
      </div>
      <div class="card">
        <h3>이렇게 해보세요</h3>
        <ul class="advice">
          ${best ? `<li><span class="ic">1</span><span><b>${best} 출구</b>를 노리세요. 동2문·남2문·북2문 주차장은 안에서 이어져 있어 들어온 문과 다른 문으로도 나갈 수 있어요.</span></li>` : ""}
          <li><span class="ic">2</span><span><b>${peakTime} 전후</b>가 가장 막혀요. 급하지 않다면 <b>${calmTime} 이후</b>에 출발하면 훨씬 덜 기다려요.</span></li>
          <li><span class="ic">3</span><span>기다리는 동안 굿즈 정리나 근처 식사로 시간을 보내보세요. ${r.t80}분 정도면 차량 80%가 빠져나가요.</span></li>
          <li><span class="ic">4</span><span>차 없이 왔다면: 올림픽공원역(5·9호선), 몽촌토성역(8호선), 한성백제역(9호선)으로 흩어서 이동하면 덜 붐벼요.</span></li>
        </ul>
      </div>`;
    drawResultChart($(`#${mode}-line`, host), r, mode);
  }

  function drawResultChart(host, r, mode) {
    if (!host) return;
    const i0 = 12;
    const labels = r.curve.total.map((_, i) => addMin(r.curveStart, i * 5));
    let pk = i0; for (let i = i0; i < r.curve.total.length; i++) if (r.curve.total[i] > r.curve.total[pk]) pk = i;
    const maxI = Math.min(labels.length - 1, Math.round(r.calm / 5) + i0);
    const markers = [{ i: i0, label: mode === "predict" ? "종료" : "종료(추정)" }, { i: maxI, label: "한산" }];
    if (r.nowIdx != null && r.nowIdx >= 0 && r.nowIdx <= labels.length - 1) markers.push({ i: r.nowIdx, label: "지금", now: true });
    lineChart(host, {
      labels,
      series: GATES.map((g) => ({ name: g + " 출구", short: g, color: css(GVAR[g]), values: r.curve[g] })),
      markers,
      yTitle: "대/5분",
      unit: "대",
      xEvery: 6,
      focusIndex: r.nowIdx != null && r.nowIdx >= 0 && r.nowIdx < labels.length ? r.nowIdx : pk,
      aria: `${r.title} 출구별 5분당 출차 대수 그래프`,
    });
  }

  function gateBars(r) {
    const vals = GATES.map((g) => (r.wait[g] && r.wait[g].median != null ? r.wait[g].median : null));
    const mx = Math.max(1, ...vals.filter((v) => v != null));
    const best = bestGate(r.wait, r.gates);
    return GATES.map((g, i) => {
      const v = vals[i];
      const w = v == null ? 0 : Math.max(2, (v / mx) * 100);
      return `<div class="gbar ${g === best ? "best" : ""}" title="${g}: ${v ?? "-"}분, 출차 비율 ${Math.round(r.gates[g].share * 100)}%">
        <span class="name"><i style="background:var(${GVAR[g]})"></i>${g}</span>
        <span class="track"><span class="fill" style="display:block;width:${w}%;background:var(${GVAR[g]})"></span></span>
        <span class="val">${v == null ? "-" : v + "분"} <span class="muted">(${Math.round(r.gates[g].share * 100)}%)</span></span>
      </div>`;
    }).join("");
  }

  // ---------- 1. 공연 찾기 ----------
  let sizeFilter = "all", query = "", currentShow = null;
  function renderList() {
    const q = query.trim().toLowerCase();
    const items = SHOWS.filter((s) => (sizeFilter === "all" || bucketOf(s.aud) === sizeFilter) &&
      (!q || s.names.join(" ").toLowerCase().includes(q) || s.date.includes(q) || s.date.slice(5).includes(q)));
    const ul = $("#showList");
    ul.textContent = "";
    items.forEach((s) => {
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.type = "button";
      if (currentShow && currentShow.date === s.date) b.setAttribute("aria-current", "true");
      const d = document.createElement("span"); d.className = "d"; d.textContent = dateLabel(s.date, s.weekday);
      // 검색어가 같은 날 다른 공연 이름에 걸렸으면 그 이름을 앞에 보여줌 (예: 'DAY6' 검색 → KAI 공연 날도 DAY6로 표시)
      const shown = (q && s.names.find((x) => x.toLowerCase().includes(q))) || s.name;
      const n = document.createElement("span"); n.className = "n"; n.textContent = shown + (s.names.length > 1 ? ` 외 ${s.names.length - 1}건` : "");
      const a = document.createElement("span"); a.className = "a"; a.textContent = nf(s.aud) + "명";
      b.append(d, n, a);
      b.addEventListener("click", () => { currentShow = s; renderList(); showResult(s); $("#result").scrollIntoView({ behavior: "smooth", block: "start" }); });
      li.appendChild(b); ul.appendChild(li);
    });
    $("#listCount").textContent = items.length ? `${items.length}개 공연일` : "";
    if (!items.length) { const li = document.createElement("li"); li.className = "empty"; li.textContent = "검색 결과가 없어요."; ul.appendChild(li); }
  }
  function showResult(s) {
    renderResult($("#result"), {
      title: s.name + (s.names.length > 1 ? ` 외 ${s.names.length - 1}건` : ""),
      dateText: `2025. ${dateLabel(s.date, s.weekday)} · 공원 전체 관람객 ${nf(s.aud)}명`,
      names: s.names,
      t0: s.t0, curve: s.curve, curveStart: s.curve_start, t80: s.t80, calm: s.calm_after,
      excess: s.excess, peak5: s.peak5, gates: s.gates, wait: s.wait, aud: s.aud, frac: s.frac,
    }, "find");
  }
  $("#q").addEventListener("input", (e) => { query = e.target.value; renderList(); });
  document.querySelectorAll("#sizeFilter .chip").forEach((c) => c.addEventListener("click", () => {
    sizeFilter = c.dataset.size;
    document.querySelectorAll("#sizeFilter .chip").forEach((x) => x.setAttribute("aria-pressed", x === c));
    renderList();
  }));

  // ---------- 지금 퇴장 가이드 (실시간) ----------
  let pDay = "weekend", lastPred = null, endAt = null;
  const pad2 = (v) => String(v).padStart(2, "0");
  const hhmm = (d) => pad2(d.getHours()) + ":" + pad2(d.getMinutes());
  const isWeekendDate = (d) => d.getDay() === 0 || d.getDay() === 6;
  function setDay(v) {
    pDay = v;
    document.querySelectorAll("#pDay button").forEach((x) => x.setAttribute("aria-pressed", x.dataset.v === v));
  }
  document.querySelectorAll("#pDay button").forEach((b) => b.addEventListener("click", () => { setDay(b.dataset.v); if (lastPred) runGuide(false); }));
  $("#pSize").addEventListener("change", () => { if (lastPred) runGuide(false); });
  function endFromInput() {
    const [h, m] = ($("#pEnd").value || "21:00").split(":").map(Number);
    const now = new Date();
    const e = new Date(now.getTime()); e.setHours(h, m, 0, 0);
    const diff = (e - now) / 60000;
    if (diff > 6 * 60) e.setDate(e.getDate() - 1);        // 새벽에 '23:30' 입력 → 어젯밤 공연
    else if (diff < -18 * 60) e.setDate(e.getDate() + 1);
    return e;
  }
  function fmtDur(min) {
    min = Math.max(0, Math.round(min));
    const h = Math.floor(min / 60), m = min % 60;
    return h ? `${h}시간${m ? ` ${m}분` : ""}` : `${m}분`;
  }
  function runGuide(scroll) {
    if (!endAt) endAt = endFromInput();
    predict();
    renderLive();
    if (scroll) $("#live").scrollIntoView({ behavior: "smooth", block: "start" });
  }
  $("#pNow").addEventListener("click", () => {
    const n = new Date(); n.setSeconds(0, 0);
    $("#pEnd").value = hhmm(n);
    setDay(isWeekendDate(n) ? "weekend" : "weekday");
    endAt = n;
    runGuide(true);
  });
  $("#pRun").addEventListener("click", () => { endAt = endFromInput(); runGuide(true); });

  function renderLive() {
    const r = lastPred;
    if (!r || !endAt) return;
    const now = new Date();
    const e = (now - endAt) / 60000; // 공연 종료 후 지난 분 (음수면 종료 전)
    const i0 = 12, totals = r.curve.total;
    let pk = i0; for (let i = i0; i < totals.length; i++) if (totals[i] > totals[pk]) pk = i;
    const peakMin = (pk - i0) * 5, calm = r.calm;
    const best = bestGate(r.wait, r.gates);
    const at = (min) => hhmm(new Date(endAt.getTime() + min * 60000));
    const bestTxt = best ? `${best} 출구` : "덜 붐비는 출구";
    let badge, state, sub, prog = null;
    if (e < 0) {
      badge = "공연 중";
      state = `공연 종료까지 ${fmtDur(-e)}`;
      sub = `끝나면 ${at(peakMin)}쯤 가장 몰리고, ${at(calm)}부터 한산해져요. 미리 ${bestTxt} 쪽으로 나갈 동선을 생각해 두세요.`;
    } else if (e < calm) {
      const rush = e < peakMin + 10;
      badge = rush ? "가장 붐빔" : "붐빔";
      state = rush ? "지금 나가면 막혀요" : "아직 붐벼요";
      sub = `${at(calm)}(약 ${fmtDur(calm - e)} 뒤)부터 한산해져요. 지금 출발해야 한다면 ${bestTxt}로 나가세요.`;
      prog = e / calm;
    } else if (e < 150) {
      badge = "한산";
      state = "지금 나가도 괜찮아요";
      sub = `가장 몰리는 시간은 지났어요. 그래도 ${bestTxt}가 가장 빨랐어요.`;
      prog = 1;
    } else {
      badge = "평소 수준";
      state = "주차장은 평소 수준이에요";
      sub = `공연이 끝난 지 ${fmtDur(e)}이 지나 퇴장 러시는 끝났어요.`;
    }
    const idx = i0 + Math.floor(e / 5);
    const inCurve = e >= -60 && idx >= 0 && idx < totals.length;
    const curNow = inCurve ? totals[idx] : null;
    const peakV = Math.max(1, totals[pk]);
    r.nowIdx = inCurve ? idx : null;
    $("#live").innerHTML = `
      <div class="card live">
        <div class="clock">지금 ${hhmm(now)} 기준 · 공연 종료 ${hhmm(endAt)} · 30초마다 갱신</div>
        <div class="state"><span class="badge">${badge}</span>${esc(state)}<small>${esc(sub)}</small></div>
        ${prog != null ? `<div class="bar" role="img" aria-label="한산해질 때까지 진행률 ${Math.round(prog * 100)}%"><span style="width:${(prog * 100).toFixed(1)}%"></span></div>
        <div class="bar-l"><span>종료 ${hhmm(endAt)}</span><span>피크 ${at(peakMin)}</span><span>한산 ${at(calm)}</span></div>` : ""}
        <div class="tiles now-tiles">
          <div class="tile"><div class="l">지금 5분 동안 나가는 차 (예상)</div><div class="v">${curNow != null ? nf(curNow) + "대" : "-"}</div><div class="s">${curNow != null ? `가장 붐빌 때의 ${Math.round((curNow / peakV) * 100)}%` : "그래프 범위 밖"}</div></div>
          <div class="tile"><div class="l">추천 출구</div><div class="v">${best || "-"}</div><div class="s">종료 후 출차가 가장 빨랐던 출구</div></div>
          <div class="tile"><div class="l">한산해지는 시각</div><div class="v">${at(calm)}</div><div class="s">${e < calm ? `약 ${fmtDur(calm - e)} 뒤` : "이미 지났어요"}</div></div>
        </div>
        <p class="muted" style="margin:10px 0 0">실시간 주차 데이터가 아직 공개되지 않아, 2025년 비슷한 규모·요일 공연 ${r.poolN}회의 실제 퇴장 기록에 지금 시각을 맞춰 안내해요.</p>
      </div>`;
    if (!$("#panel-now").hidden) drawResultChart($("#predict-line"), r, "predict");
  }
  setInterval(() => { if (lastPred && endAt && !document.hidden && !$("#panel-now").hidden) renderLive(); }, 30000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden && lastPred && endAt && !$("#panel-now").hidden) renderLive(); });

  function predict() {
    const shapes = MODEL.shapes || [];
    if (!shapes.length) return;
    const idx = Math.min(Number($("#pSize").value), shapes.length - 1);
    const sh = shapes[idx];
    const end = endAt ? hhmm(endAt) : ($("#pEnd").value || "21:00");
    const sameDay = SHOWS.filter((s) => s.aud >= sh.lo && s.aud < sh.hi && (pDay === "weekend") === (s.weekday === "토" || s.weekday === "일"));
    const pool = sameDay.length >= 3 ? sameDay : SHOWS.filter((s) => s.aud >= sh.lo && s.aud < sh.hi);
    const med = (arr) => { const a = arr.slice().sort((x, y) => x - y); return a.length ? a[Math.floor(a.length / 2)] : 0; };
    const excess = med(pool.map((s) => s.excess));
    const curve = {};
    ["total", ...GATES].forEach((k) => { curve[k] = sh.shape[k].map((v) => Math.round(v * excess)); });
    const gates = {}, wait = {};
    GATES.forEach((g) => {
      gates[g] = { share: med(pool.map((s) => s.gates[g].share)) };
      const ws = pool.map((s) => s.wait[g].median).filter((v) => v != null);
      wait[g] = { median: ws.length ? Math.round(med(ws) * 10) / 10 : null, n: ws.length >= 3 ? 999 : 0 };
    });
    const labelSize = $("#pSize").selectedOptions[0].textContent.replace(/\s*\(.*\)/, "");
    lastPred = {
      title: `관람객 ${labelSize} 공연 (${pDay === "weekend" ? "주말" : "평일"})`,
      dateText: `2025년 비슷한 공연 ${pool.length}회 기준`,
      t0: end, curve, curveStart: addMin(end, -60), t80: med(pool.map((s) => s.t80)), calm: med(pool.map((s) => s.calm_after)),
      excess, peak5: sh.peak5, gates, wait, poolN: pool.length,
    };
    renderResult($("#pResult"), lastPred, "predict");
  }

  // ---------- 3. 인사이트 ----------
  let cmpMode = "weekend";
  document.querySelectorAll("#cmpFilter .chip").forEach((c) => c.addEventListener("click", () => {
    cmpMode = c.dataset.v;
    document.querySelectorAll("#cmpFilter .chip").forEach((x) => x.setAttribute("aria-pressed", x === c));
    renderInsight();
  }));
  function renderInsight() {
    const hc = INSIGHT.hourly_cmp;
    if (!hc) return;
    const big = hc[`big_show_${cmpMode}`], non = hc[`nonshow_${cmpMode}`];
    const host = $("#cmpChart");
    const S = [
      { name: `관람객 1만 명+ 공연 날 (${hc.n[`big_show_${cmpMode}`]}일 평균)`, short: "공연 날", color: css("--emph"), values: big },
      { name: `공연 없거나 5천 명 미만인 날 (${hc.n[`nonshow_${cmpMode}`]}일 평균)`, short: "평소", color: css("--deemph"), values: non },
    ];
    host.innerHTML = legend(S) + `<div class="chart" id="cmpLine"></div>
      <details class="table-view"><summary>표로 보기</summary><div class="tbl-scroll"><table class="tbl"><thead><tr><th>시간</th><th>공연 날</th><th>평소</th></tr></thead><tbody>
      ${big.map((v, i) => `<tr><td>${i}시</td><td>${nf(Math.round(v))}</td><td>${nf(Math.round(non[i]))}</td></tr>`).join("")}</tbody></table></div></details>`;
    lineChart($("#cmpLine"), {
      labels: big.map((_, i) => i + "시"), series: S.map((s) => ({ ...s, values: s.values.map((v) => Math.round(v)) })),
      yTitle: "대/시간", unit: "대", xEvery: 3, area: true, focusIndex: 21, aria: "공연 날과 평소의 시간대별 출차 비교",
    });
    const share = INSIGHT.big_gate_share || {}, wm = INSIGHT.big_wait_median || {};
    $("#shareBars").innerHTML = `<div class="gate-bars">${gateBars({ gates: Object.fromEntries(GATES.map((g) => [g, { share: share[g] || 0 }])), wait: Object.fromEntries(GATES.map((g) => [g, { median: wm[g] ?? null, n: 999 }])) })}</div>`;
    const k = [
      ["분석한 차량 기록", nf(INSIGHT.records) + "건"],
      ["분석한 공연일", (INSIGHT.show_days || 0) + "일"],
      ["공연 후 80%가 빠지는 데", "중앙값 " + medianOf(SHOWS.map((s) => s.t80)) + "분"],
      ["들어온 문과 다른 문으로 나간 차", Math.round((INSIGHT.cross_exit_ratio || 0) * 100) + "%"],
    ];
    $("#kpis").innerHTML = k.map(([l, v]) => `<div class="tile"><div class="l">${l}</div><div class="v">${v}</div></div>`).join("");
  }

  function medianOf(arr) {
    const a = arr.slice().sort((x, y) => x - y);
    if (!a.length) return 0;
    const m = Math.floor(a.length / 2);
    return a.length % 2 ? a[m] : Math.round((a[m - 1] + a[m]) / 2);
  }

  function rerender() {
    if (currentShow && !$("#panel-find").hidden) showResult(currentShow);
    if (lastPred && !$("#panel-now").hidden) { renderResult($("#pResult"), lastPred, "predict"); renderLive(); }
    if (!$("#panel-insight").hidden) renderInsight();
  }
  let rT; window.addEventListener("resize", () => { clearTimeout(rT); rT = setTimeout(rerender, 200); });
  matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", rerender);

  // ---------- 시작 ----------
  $("#heroRecords").textContent = nf(INSIGHT.records || 0);
  $("#crossPct").textContent = Math.round((INSIGHT.cross_exit_ratio || 0) * 100) + "%";
  // 기록 탭 기본 공연: 기록 60% 이상 확보 · 그날 공연 1개 · 저녁 종료 · 1만 명 이상 중 퇴장 러시가 가장 뚜렷한 날 (기획서 [그림 4]와 같은 규칙)
  const burst = (s) => Math.max(...s.curve.total.slice(12)) / Math.max(1, s.curve.total.slice(0, 8).reduce((a, b) => a + b, 0) / 8);
  const pool0 = SHOWS.filter((s) => (s.frac ?? 1) >= 0.6 && s.names.length === 1 && s.t0 >= "19:00" && s.aud >= 10000);
  const first = (pool0.length ? pool0 : SHOWS).slice().sort((a, b) => burst(b) - burst(a))[0];
  if (first) currentShow = first;
  renderList();
  // 첫 화면: 오늘 요일로 맞추고, 입력된 종료 시각 기준 안내를 바로 보여줌
  setDay(isWeekendDate(new Date()) ? "weekend" : "weekday");
  endAt = endFromInput();
  predict();
  renderLive();
  const h0 = (location.hash || "").slice(1);
  const t = tabs.find((x) => x.id === "tab-" + (h0 === "predict" ? "now" : h0));
  if (t) selectTab(t);
})();
