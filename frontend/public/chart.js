/*
 * (보너스) 라이브러리 없이 SVG로 그리는 그래프
 *  - Charts.renderDaily(): 하루 공부 시간(막대) + 7일 이동평균(선) + 목표선, 마우스/키보드 툴팁
 *  - Charts.renderWeekday(): 요일별 평균(막대)
 */
const Charts = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const WEEK = ["일", "월", "화", "수", "목", "금", "토"];

  function svgEl(tag, attrs = {}, parent) {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    if (parent) parent.appendChild(node);
    return node;
  }

  function text(parent, x, y, str, attrs = {}) {
    const t = svgEl("text", { x, y, ...attrs }, parent);
    t.textContent = str;
    return t;
  }

  /** y축 최댓값과 눈금 간격(분): 60분(1시간) 단위로 깔끔하게 */
  function yScale(maxValue) {
    const step = maxValue > 480 ? 120 : 60;
    return { max: Math.max(step, Math.ceil(maxValue / step) * step), step };
  }

  /** 위쪽만 둥근(4px) 막대 경로 - 바닥은 직각 */
  function barPath(cx, width, yTop, yBase) {
    const x0 = cx - width / 2, x1 = cx + width / 2;
    const r = Math.min(4, width / 2, yBase - yTop);
    return `M${x0},${yBase} V${yTop + r} Q${x0},${yTop} ${x0 + r},${yTop} H${x1 - r} Q${x1},${yTop} ${x1},${yTop + r} V${yBase} Z`;
  }

  function minutesText(m) {
    m = Math.round(m);
    const h = Math.floor(m / 60), r = m % 60;
    if (h && r) return `${h}시간 ${r}분`;
    if (h) return `${h}시간`;
    return `${r}분`;
  }

  // ── 툴팁 (값은 굵게, 이름은 보조) ──
  const tip = () => document.getElementById("chart-tooltip");

  function showTip(clientX, clientY, title, rows, memo) {
    const box = tip();
    box.replaceChildren();
    const d = document.createElement("div");
    d.className = "tt-date";
    d.textContent = title;
    box.appendChild(d);
    for (const row of rows) {
      const r = document.createElement("div");
      r.className = "tt-row";
      if (row.color) {
        const k = document.createElement("i");
        k.className = "tt-key";
        k.style.background = row.color;
        r.appendChild(k);
      }
      const b = document.createElement("b");
      b.textContent = row.value;
      const s = document.createElement("span");
      s.className = "muted";
      s.textContent = row.label;
      r.append(b, s);
      box.appendChild(r);
    }
    if (memo) {
      const m = document.createElement("div");
      m.className = "tt-memo";
      m.textContent = memo;
      box.appendChild(m);
    }
    box.hidden = false;
    const w = box.offsetWidth, h = box.offsetHeight;
    let left = clientX + 14, top = clientY - h - 12;
    if (left + w > window.innerWidth - 8) left = clientX - w - 14;
    if (top < 8) top = clientY + 16;
    box.style.left = `${left}px`;
    box.style.top = `${top}px`;
  }

  function hideTip() {
    tip().hidden = true;
  }

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function empty(container, msg) {
    container.replaceChildren();
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = msg;
    container.appendChild(p);
  }

  /**
   * 하루 공부 시간 그래프
   * @param series [{date, value, ma7}]
   * @param goal 목표(분)
   * @param memos {date: memo}
   */
  function renderDaily(container, series, goal, memos = {}) {
    if (!series.length) return empty(container, "표시할 데이터가 없어요. 데이터 관리 탭에서 기록을 추가해 보세요.");
    container.replaceChildren();
    const W = container.clientWidth, H = container.clientHeight;
    const m = { top: 26, right: 96, bottom: 28, left: 44 };
    const iw = W - m.left - m.right, ih = H - m.top - m.bottom;
    const peak = Math.max(goal, ...series.map((d) => Math.max(d.value, d.ma7)));
    const { max, step } = yScale(peak);
    const y = (v) => m.top + ih - (v / max) * ih;
    const band = iw / series.length;
    const x = (i) => m.left + band * (i + 0.5);
    const bw = Math.max(1, Math.min(24, band - 2)); // 막대 사이 2px 여백

    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `하루 공부 시간 ${series.length}일` }, container);

    // y축 눈금 + 가로 보조선
    for (let v = 0; v <= max; v += step) {
      svgEl("line", { x1: m.left, x2: m.left + iw, y1: y(v), y2: y(v), class: v === 0 ? "baseline" : "grid" }, svg);
      text(svg, m.left - 8, y(v) + 4, v, { "text-anchor": "end" });
    }
    text(svg, m.left - 8, m.top - 14, "(분)", { "text-anchor": "end" });

    // 막대 (하루 공부 시간)
    const bars = series.map((d, i) =>
      d.value > 0 ? svgEl("path", { d: barPath(x(i), bw, y(d.value), y(0)), class: "bar" }, svg) : null
    );

    // 목표선 + 라벨
    svgEl("line", { x1: m.left, x2: m.left + iw, y1: y(goal), y2: y(goal), class: "goal" }, svg);
    text(svg, m.left + iw + 8, y(goal) + 4, `목표 ${goal}분`);

    // 7일 이동평균 선 + 끝점 + 끝 라벨
    const linePath = series.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d.ma7).toFixed(1)}`).join(" ");
    svgEl("path", { d: linePath, class: "ma" }, svg);
    const last = series[series.length - 1];
    svgEl("circle", { cx: x(series.length - 1), cy: y(last.ma7), r: 4, class: "end-dot" }, svg);
    let labelY = y(last.ma7) + 4;
    if (Math.abs(labelY - (y(goal) + 4)) < 14) labelY += labelY > y(goal) ? 10 : -10; // 목표 라벨과 겹치지 않게
    text(svg, m.left + iw + 8, labelY, `7일 평균 ${Math.round(last.ma7)}분`, { class: "val-label" });

    // x축 날짜 라벨 (6개 정도만)
    const every = Math.max(1, Math.ceil(series.length / 6));
    series.forEach((d, i) => {
      if (i % every === 0 || i === series.length - 1) {
        if (i !== series.length - 1 && series.length - 1 - i < every / 2) return; // 마지막 라벨과 겹침 방지
        text(svg, x(i), H - 8, d.date.slice(5).replace("-", "/"), { "text-anchor": "middle" });
      }
    });

    // 십자선 + 마우스 영역
    const cross = svgEl("line", { y1: m.top, y2: m.top + ih, class: "crosshair", visibility: "hidden" }, svg);
    const hit = svgEl("rect", { x: m.left, y: m.top, width: iw, height: ih, fill: "transparent" }, svg);
    let current = -1;

    function focusIndex(i, clientX, clientY) {
      i = Math.max(0, Math.min(series.length - 1, i));
      current = i;
      const d = series[i];
      cross.setAttribute("x1", x(i));
      cross.setAttribute("x2", x(i));
      cross.setAttribute("visibility", "visible");
      bars.forEach((b, j) => b && b.classList.toggle("dim", j !== i));
      const day = WEEK[new Date(d.date + "T00:00:00").getDay()];
      if (clientX === undefined) {
        const rect = svg.getBoundingClientRect();
        clientX = rect.left + (x(i) / W) * rect.width;
        clientY = rect.top + (y(Math.max(d.value, d.ma7)) / H) * rect.height;
      }
      showTip(clientX, clientY, `${d.date} (${day})`, [
        { color: cssVar("--series-1"), value: `${d.value}분`, label: d.value >= 60 ? `하루 공부 · ${minutesText(d.value)}` : "하루 공부" },
        { color: cssVar("--series-2"), value: `${d.ma7}분`, label: "7일 이동평균" },
      ], memos[d.date]);
    }

    function clear() {
      cross.setAttribute("visibility", "hidden");
      bars.forEach((b) => b && b.classList.remove("dim"));
      hideTip();
    }

    hit.addEventListener("pointermove", (e) => {
      const rect = svg.getBoundingClientRect();
      const px = ((e.clientX - rect.left) / rect.width) * W;
      focusIndex(Math.floor((px - m.left) / band), e.clientX, e.clientY);
    });
    hit.addEventListener("pointerleave", clear);
    container.onkeydown = (e) => {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        const next = current < 0 ? series.length - 1 : current + (e.key === "ArrowRight" ? 1 : -1);
        focusIndex(next);
      } else if (e.key === "Escape") clear();
    };
    container.onblur = clear;
  }

  /** 요일별 평균 막대 그래프 (월~일) */
  function renderWeekday(container, weekdayAverage) {
    const entries = Object.entries(weekdayAverage || {});
    if (!entries.length || entries.every(([, v]) => !v)) return empty(container, "표시할 데이터가 없어요.");
    container.replaceChildren();
    const W = container.clientWidth, H = container.clientHeight;
    const m = { top: 24, right: 12, bottom: 28, left: 44 };
    const iw = W - m.left - m.right, ih = H - m.top - m.bottom;
    const { max, step } = yScale(Math.max(...entries.map(([, v]) => v)));
    const y = (v) => m.top + ih - (v / max) * ih;
    const band = iw / entries.length;
    const bw = Math.min(24, band - 2);
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "요일별 평균 공부 시간" }, container);

    for (let v = 0; v <= max; v += step) {
      svgEl("line", { x1: m.left, x2: m.left + iw, y1: y(v), y2: y(v), class: v === 0 ? "baseline" : "grid" }, svg);
      text(svg, m.left - 8, y(v) + 4, v, { "text-anchor": "end" });
    }
    entries.forEach(([day, avg], i) => {
      const cx = m.left + band * (i + 0.5);
      const bar = avg > 0 ? svgEl("path", { d: barPath(cx, bw, y(avg), y(0)), class: "bar" }, svg) : null;
      text(svg, cx, y(avg) - 6, `${Math.round(avg)}`, { "text-anchor": "middle", class: "val-label" });
      text(svg, cx, H - 8, day, { "text-anchor": "middle" });
      // 막대보다 넓은 마우스 영역
      const hit = svgEl("rect", { x: cx - band / 2, y: m.top, width: band, height: ih, fill: "transparent" }, svg);
      hit.addEventListener("pointermove", (e) => {
        if (bar) bar.classList.add("hover");
        showTip(e.clientX, e.clientY, `${day}요일`, [{ color: cssVar("--series-1"), value: `${avg}분`, label: `평균 · ${minutesText(avg)}` }]);
      });
      hit.addEventListener("pointerleave", () => {
        if (bar) bar.classList.remove("hover");
        hideTip();
      });
    });
  }

  return { renderDaily, renderWeekday, minutesText };
})();
