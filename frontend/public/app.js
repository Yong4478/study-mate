/*
 * 스터디 메이트 프론트엔드 (바닐라 JavaScript)
 *
 *  1. API 호출 도우미 + 서버 깨우기(Render 콜드스타트 대응)
 *  2. 데이터 요약 카드
 *  3. AI 채팅 (로딩 표시, 도구 호출 모드)
 *  4. 대화 기록 (목록 / 불러오기 / 삭제 / 새 대화)
 *  5. 데이터 관리 (추가 / 목록 / 수정 / 삭제 / CSV·JSON 내보내기)
 *  6. 통계·그래프 (보너스)
 *  7. 다크 모드 · 탭 · 초기화
 */
"use strict";

// config.js 에서 넣어준 주소. 없으면 로컬 백엔드.
const API_BASE_URL = ((window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL) || "http://localhost:8000").replace(/\/+$/, "");

const state = {
  conversationId: null, // 지금 보고 있는 대화 ID (없으면 새 대화)
  conversations: [],
  records: [],
  stats: null,
  statsRange: "all",
  sending: false,
  editingId: null, // 수정 중인 기록 ID
};

const $ = (selector) => document.querySelector(selector);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const FIELD_NAMES = { date: "날짜", value: "공부 시간", memo: "메모", message: "메시지", goal: "목표" };
const WEEK = ["일", "월", "화", "수", "목", "금", "토"];

/* ═════════════ 1. API 도우미 ═════════════ */

function formatDetail(detail) {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI 422 검증 에러: [{loc: ["body","value"], msg: "..."}]
    return detail
      .map((d) => {
        const field = (d.loc || []).slice(-1)[0];
        const msg = String(d.msg || "").replace(/^Value error, /, "");
        return field && FIELD_NAMES[field] ? `${FIELD_NAMES[field]}: ${msg}` : msg;
      })
      .join("\n");
  }
  return JSON.stringify(detail);
}

async function api(path, { method = "GET", body, timeout = 70000, raw = false } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  let res;
  try {
    res = await fetch(API_BASE_URL + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (e) {
    throw new Error(
      e.name === "AbortError"
        ? "서버 응답이 너무 늦어요. 잠시 후 다시 시도해 주세요."
        : "서버에 연결할 수 없어요. (API 주소 또는 백엔드 CORS 설정을 확인하세요)"
    );
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    let message = `요청 실패 (${res.status})`;
    try {
      const data = await res.json();
      message = formatDetail(data.detail) || message;
    } catch (_) {}
    const err = new Error(message);
    err.status = res.status;
    throw err;
  }
  if (raw) return res;
  return res.status === 204 ? null : res.json();
}

function setStatus(stateName, label) {
  const pill = $("#server-status");
  pill.dataset.state = stateName;
  pill.querySelector(".label").textContent = label;
}

/** Render 무료 플랜은 15분간 요청이 없으면 잠듭니다. 첫 요청이 느리면 안내 배너를 띄워요. */
async function wakeServer() {
  const banner = $("#wake-banner");
  banner.classList.remove("error");
  $("#wake-retry").hidden = true;
  $("#wake-text").textContent = "무료 서버(Render)를 깨우는 중이에요. 처음 접속하면 최대 1분 정도 걸릴 수 있어요 ☕";
  setStatus("pending", "서버 확인 중");
  const slowTimer = setTimeout(() => {
    banner.hidden = false;
    setStatus("waking", "서버 깨우는 중");
  }, 2500);

  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      await api("/health", { timeout: 60000 });
      clearTimeout(slowTimer);
      banner.hidden = true;
      setStatus("ok", "서버 연결됨");
      return true;
    } catch (_) {
      if (attempt < 3) await sleep(3000);
    }
  }
  clearTimeout(slowTimer);
  banner.hidden = false;
  banner.classList.add("error");
  $("#wake-text").textContent = `서버(${API_BASE_URL})에 연결하지 못했어요. 주소와 서버 상태를 확인해 주세요.`;
  $("#wake-retry").hidden = false;
  setStatus("error", "연결 실패");
  return false;
}

/* ═════════════ 공통 UI 도우미 ═════════════ */

let toastTimer;
function toast(message, type = "ok") {
  const box = $("#toast");
  box.textContent = message;
  box.className = `toast ${type === "error" ? "error" : ""}`;
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (box.hidden = true), type === "error" ? 4000 : 2400);
}

function todayStr() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 10);
}

function daysAgoStr(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 10);
}

function weekday(dateStr) {
  return WEEK[new Date(dateStr + "T00:00:00").getDay()];
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text; // textContent → HTML 주입(XSS) 방지
  return node;
}

/* ═════════════ 2. 데이터 요약 카드 ═════════════ */

function renderSummary(s) {
  const box = $("#summary-box");
  box.replaceChildren();
  if (!s || !s.count) {
    box.appendChild(el("p", "muted", "아직 기록이 없어요. '데이터 관리' 탭에서 공부 시간을 추가해 보세요."));
    return;
  }
  const m = s.metrics;
  const rows = [
    ["기간", s.period],
    ["기록 수", `${s.count}개`],
    ["총 공부", `${m.total.toLocaleString()}분 (${Charts.minutesText(m.total)})`],
    ["하루 평균", `${m.average}분`],
    ["최고", `${m.max}분 · ${m.max_date}`],
    ["최저", `${m.min}분 · ${m.min_date}`],
  ];
  const dl = el("dl");
  for (const [k, v] of rows) dl.append(el("dt", "", k), el("dd", "", v));
  box.appendChild(dl);

  // 추세: 화살표 + 글자로 표시 (색에만 의존하지 않기)
  const [label, ...rest] = s.trend.split(" ");
  const trend = el("div", "trend");
  trend.dataset.dir = s.trend_direction;
  const arrow = { up: "↑", down: "↓", flat: "→" }[s.trend_direction] || "·";
  trend.append(el("span", "arrow", arrow), el("b", "", label), el("span", "", rest.join(" ").replace(/^\(|\)$/g, "")));
  box.appendChild(trend);
}

/** 이번 달 AI 토큰 사용량 / 한도 */
async function loadUsage() {
  try {
    const u = await api("/api/usage");
    $("#token-usage").textContent = u.enabled
      ? `🔋 이번 달 AI 토큰: ${u.used_tokens.toLocaleString()} / ${u.limit_tokens.toLocaleString()}`
      : `🔋 이번 달 AI 토큰: ${u.used_tokens.toLocaleString()} (한도 없음)`;
  } catch (_) {
    $("#token-usage").textContent = "";
  }
}

async function loadSummary() {
  try {
    renderSummary(await api("/api/data/summary"));
  } catch (e) {
    $("#summary-box").replaceChildren(el("p", "muted", `요약을 불러오지 못했어요: ${e.message}`));
  }
}

/* ═════════════ 3. AI 채팅 ═════════════ */

const messagesBox = $("#messages");
const welcomeBox = $("#welcome");

function scrollToBottom() {
  messagesBox.scrollTop = messagesBox.scrollHeight;
}

function appendMessage(role, content, { tools = [], notice = null, time = null } = {}) {
  welcomeBox.hidden = true;
  const wrap = el("div", `msg ${role}`);
  wrap.appendChild(el("div", "bubble", content));
  const meta = el("div", "msg-meta");
  if (time) meta.appendChild(el("span", "", formatTime(time)));
  for (const t of tools) {
    const args = Object.entries(t.arguments || {}).map(([k, v]) => `${k}=${v}`).join(", ");
    const badge = el("span", "tool-badge", `🔧 ${t.name}(${args})`);
    badge.title = t.result_preview || "";
    meta.appendChild(badge);
  }
  if (notice) meta.appendChild(el("span", "", `ℹ️ ${notice}`));
  if (meta.childNodes.length) wrap.appendChild(meta);
  messagesBox.appendChild(wrap);
  scrollToBottom();
  return wrap;
}

function appendTyping() {
  const wrap = el("div", "msg assistant typing");
  const bubble = el("div", "bubble");
  const dots = el("span", "dots");
  dots.append(el("span"), el("span"), el("span"));
  const label = el("span", "", "AI가 내 공부 기록을 분석하고 있어요");
  bubble.append(dots, label);
  wrap.appendChild(bubble);
  messagesBox.appendChild(wrap);
  scrollToBottom();
  // 오래 걸리면 콜드스타트 안내
  const slow = setTimeout(() => (label.textContent = "조금만 기다려 주세요… (서버가 깨어나는 중일 수 있어요)"), 9000);
  return { remove: () => { clearTimeout(slow); wrap.remove(); } };
}

function setSending(on) {
  state.sending = on;
  $("#chat-send").disabled = on;
  $("#chat-send").textContent = on ? "답변 중…" : "보내기";
}

async function sendMessage(text) {
  text = text.trim();
  if (!text || state.sending) return;
  setSending(true);
  const input = $("#chat-input");
  input.value = "";
  autoResize(input);
  appendMessage("user", text);
  const typing = appendTyping();
  try {
    const res = await api("/api/chat", {
      method: "POST",
      body: { message: text, conversation_id: state.conversationId, use_tools: $("#use-tools").checked },
      timeout: 120000,
    });
    typing.remove();
    appendMessage("assistant", res.reply, { tools: res.tool_calls, notice: res.notice });
    state.conversationId = res.conversation_id;
    renderSummary(res.summary); // 답변에 주입된 요약을 그대로 표시
    loadUsage();
    await loadConversations();
    const current = state.conversations.find((c) => c.id === state.conversationId);
    if (current) {
      $("#chat-title").textContent = current.title;
      $("#chat-sub").textContent = `자동 저장됨 · 메시지 ${current.message_count}개`;
    }
  } catch (e) {
    typing.remove();
    appendMessage("error", `⚠️ ${e.message}`);
  } finally {
    setSending(false);
    input.focus();
  }
}

function autoResize(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight, 140)}px`;
}

/* ═════════════ 4. 대화 기록 ═════════════ */

async function loadConversations() {
  try {
    state.conversations = await api("/api/conversations");
    renderConversationList();
  } catch (e) {
    $("#conversation-list").replaceChildren(el("li", "muted", `대화 목록을 불러오지 못했어요: ${e.message}`));
  }
}

function renderConversationList() {
  const list = $("#conversation-list");
  list.replaceChildren();
  if (!state.conversations.length) {
    list.appendChild(el("li", "muted", "아직 저장된 대화가 없어요. 첫 질문을 해보세요!"));
    return;
  }
  for (const c of state.conversations) {
    const li = el("li", `conv-item${c.id === state.conversationId ? " active" : ""}`);
    li.tabIndex = 0;
    li.setAttribute("role", "button");
    li.title = c.last_message;
    const main = el("div", "conv-main");
    main.append(el("div", "conv-title", c.title), el("div", "conv-meta", `${formatTime(c.updated_at)} · 메시지 ${c.message_count}개`));
    const del = el("button", "conv-del", "✕");
    del.type = "button";
    del.setAttribute("aria-label", `${c.title} 대화 삭제`);
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteConversation(c);
    });
    li.append(main, del);
    li.addEventListener("click", () => openConversation(c.id));
    li.addEventListener("keydown", (e) => e.key === "Enter" && openConversation(c.id));
    list.appendChild(li);
  }
}

async function openConversation(id) {
  try {
    const conv = await api(`/api/conversations/${encodeURIComponent(id)}`);
    state.conversationId = conv.id;
    messagesBox.replaceChildren(welcomeBox);
    for (const m of conv.messages) appendMessage(m.role, m.content, { time: m.created_at });
    $("#chat-title").textContent = conv.title;
    $("#chat-sub").textContent = `불러온 대화 · 메시지 ${conv.message_count}개 · 이어서 질문하면 이 대화에 저장돼요`;
    renderConversationList();
    showTab("chat");
  } catch (e) {
    toast(e.message, "error");
  }
}

function newChat() {
  state.conversationId = null;
  messagesBox.replaceChildren(welcomeBox);
  welcomeBox.hidden = false;
  $("#chat-title").textContent = "새 대화";
  $("#chat-sub").textContent = "질문하면 대화가 자동으로 저장돼요.";
  renderConversationList();
  $("#chat-input").focus();
}

async function deleteConversation(c) {
  if (!confirm(`'${c.title}' 대화를 삭제할까요?`)) return;
  try {
    await api(`/api/conversations/${encodeURIComponent(c.id)}`, { method: "DELETE" });
    if (c.id === state.conversationId) newChat();
    await loadConversations();
    toast("대화를 삭제했어요 🗑");
  } catch (e) {
    toast(e.message, "error");
  }
}

/* ═════════════ 5. 데이터 관리 (CRUD) ═════════════ */

async function loadRecords() {
  try {
    state.records = await api("/api/data?order=desc");
    renderRecords();
  } catch (e) {
    const tr = el("tr");
    const td = el("td", "muted", `목록을 불러오지 못했어요: ${e.message}`);
    td.colSpan = 4;
    tr.appendChild(td);
    $("#data-tbody").replaceChildren(tr);
  }
}

function renderRecords(flashId) {
  const tbody = $("#data-tbody");
  tbody.replaceChildren();
  $("#data-count").textContent = state.records.length;
  if (!state.records.length) {
    const tr = el("tr");
    const td = el("td", "muted", "아직 기록이 없어요. 위에서 첫 기록을 추가해 보세요!");
    td.colSpan = 4;
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  for (const r of state.records) {
    const tr = el("tr");
    tr.dataset.id = r.id;
    if (r.id === flashId) tr.classList.add("flash");
    tr.appendChild(el("td", "", `${r.date} (${weekday(r.date)})`));

    if (state.editingId === r.id) {
      tr.classList.add("editing");
      const valueTd = el("td", "num");
      const valueInput = el("input");
      Object.assign(valueInput, { type: "number", min: 0, max: 1440, step: 5, value: r.value });
      valueInput.setAttribute("aria-label", "공부 시간(분)");
      valueTd.appendChild(valueInput);
      const memoTd = el("td");
      const memoInput = el("input");
      Object.assign(memoInput, { type: "text", maxLength: 100, value: r.memo });
      memoInput.setAttribute("aria-label", "메모");
      memoTd.appendChild(memoInput);
      const actions = el("td", "actions");
      const save = el("button", "btn btn-small btn-primary", "저장");
      const cancel = el("button", "btn btn-small", "취소");
      save.onclick = () => updateRecord(r.id, valueInput.value, memoInput.value);
      cancel.onclick = () => { state.editingId = null; renderRecords(); };
      memoInput.onkeydown = valueInput.onkeydown = (e) => e.key === "Enter" && save.click();
      actions.append(save, " ", cancel);
      tr.append(valueTd, memoTd, actions);
      setTimeout(() => valueInput.focus(), 0);
    } else {
      tr.appendChild(el("td", "num", r.value >= 60 ? `${r.value}분 (${Charts.minutesText(r.value)})` : `${r.value}분`));
      tr.appendChild(el("td", "", r.memo));
      const actions = el("td", "actions");
      const edit = el("button", "btn btn-small", "수정");
      const del = el("button", "btn btn-small btn-danger", "삭제");
      edit.onclick = () => { state.editingId = r.id; renderRecords(); };
      del.onclick = () => deleteRecord(r.id);
      actions.append(edit, " ", del);
      tr.appendChild(actions);
    }
    tbody.appendChild(tr);
  }
}

/** 데이터가 바뀌면 목록·요약·통계를 함께 갱신 */
async function afterDataChange(flashId) {
  await loadRecords();
  if (flashId) renderRecords(flashId);
  loadSummary();
  if (state.stats) loadStats();
}

async function createRecord(e) {
  e.preventDefault();
  const body = {
    date: $("#data-date").value,
    value: Number($("#data-value").value),
    memo: $("#data-memo").value.trim(),
  };
  try {
    const saved = await api("/api/data", { method: "POST", body });
    toast(`${saved.date} 기록을 저장했어요 ✅`);
    $("#data-value").value = "";
    $("#data-memo").value = "";
    await afterDataChange(saved.id);
  } catch (err) {
    toast(err.message, "error");
  }
}

async function updateRecord(id, value, memo) {
  if (value === "" || Number(value) < 0 || Number(value) > 1440) {
    toast("공부 시간은 0~1440분 사이로 입력하세요.", "error");
    return;
  }
  try {
    await api(`/api/data/${id}`, { method: "PUT", body: { value: Number(value), memo: memo.trim() } });
    state.editingId = null;
    toast(`${id} 기록을 수정했어요 ✏️`);
    await afterDataChange(id);
  } catch (err) {
    toast(err.message, "error");
  }
}

async function deleteRecord(id) {
  if (!confirm(`${id} 기록을 삭제할까요?`)) return;
  try {
    await api(`/api/data/${id}`, { method: "DELETE" });
    toast(`${id} 기록을 삭제했어요 🗑`);
    await afterDataChange();
  } catch (err) {
    toast(err.message, "error");
  }
}

/** (보너스) CSV / JSON 내보내기 */
async function exportData(format) {
  try {
    const res = await api(`/api/data/export?format=${format}`, { raw: true });
    const url = URL.createObjectURL(await res.blob());
    const a = el("a");
    a.href = url;
    a.download = `study_log_${todayStr()}.${format}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast(`${format.toUpperCase()} 파일을 내려받았어요 ⬇`);
  } catch (err) {
    toast(err.message, "error");
  }
}

/* ═════════════ 6. 통계·그래프 (보너스) ═════════════ */

function goalMinutes() {
  const g = parseInt($("#goal-minutes").value, 10);
  return Number.isFinite(g) ? Math.max(10, Math.min(1440, g)) : 120;
}

async function loadStats() {
  let query = `?goal=${goalMinutes()}`;
  if (state.statsRange !== "all") query += `&start=${daysAgoStr(Number(state.statsRange) - 1)}`;
  try {
    state.stats = await api(`/api/data/statistics${query}`);
    renderStats();
  } catch (e) {
    $("#stat-tiles").replaceChildren(el("p", "muted", `통계를 불러오지 못했어요: ${e.message}`));
  }
}

function tile(label, value, sub) {
  const t = el("div", "tile");
  t.append(el("div", "tile-label", label), el("div", "tile-value", value), el("div", "tile-sub", sub));
  return t;
}

function renderStats() {
  const s = state.stats;
  if (!s) return;
  $("#stat-tiles").replaceChildren(
    tile("목표 달성률", `${s.goal_achievement_rate}%`, `${s.goal_achieved_days}/${s.count}일 · 하루 목표 ${s.goal_minutes}분`),
    tile("현재 연속 공부", `${s.current_streak}일`, `최장 기록 ${s.longest_streak}일`),
    tile("공부한 날", `${s.study_days}일`, `쉰 날 ${s.rest_days}일`),
    tile("중앙값", `${s.median}분`, `표준편차 ${s.std_dev}분 · 최고 요일 ${s.best_weekday || "-"}`)
  );
  renderCharts();
}

function renderCharts() {
  if ($("#tab-stats").hidden || !state.stats) return;
  const memos = Object.fromEntries(state.records.map((r) => [r.date, r.memo]));
  Charts.renderDaily($("#daily-chart"), state.stats.series, state.stats.goal_minutes, memos);
  Charts.renderWeekday($("#weekday-chart"), state.stats.weekday_average);
}

/* ═════════════ 7. 다크 모드 · 탭 · 초기화 ═════════════ */

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  $("#theme-toggle").textContent = theme === "dark" ? "☀️" : "🌙";
  try {
    localStorage.setItem("theme", theme);
  } catch (_) {}
}

function showTab(name) {
  document.querySelectorAll(".tab").forEach((t) => {
    const active = t.dataset.tab === name;
    t.classList.toggle("active", active);
    t.setAttribute("aria-selected", active);
  });
  document.querySelectorAll(".tab-panel").forEach((p) => (p.hidden = p.id !== `tab-${name}`));
  if (name === "stats") state.stats ? renderCharts() : loadStats();
}

function bindEvents() {
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab)));
  $("#theme-toggle").addEventListener("click", () => {
    applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
  });
  $("#wake-retry").addEventListener("click", init);

  // 채팅
  const input = $("#chat-input");
  $("#chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(input.value);
  });
  input.addEventListener("keydown", (e) => {
    // 한글 조합 중(isComposing)일 때 Enter 는 무시 → 두 번 전송되는 문제 방지
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      sendMessage(input.value);
    }
  });
  input.addEventListener("input", () => autoResize(input));
  document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => sendMessage(c.textContent)));
  $("#new-chat").addEventListener("click", newChat);
  $("#summary-refresh").addEventListener("click", loadSummary);

  // 데이터
  $("#data-form").addEventListener("submit", createRecord);
  document.querySelectorAll("[data-export]").forEach((b) => b.addEventListener("click", () => exportData(b.dataset.export)));

  // 통계
  document.querySelectorAll("[data-range]").forEach((b) =>
    b.addEventListener("click", () => {
      document.querySelectorAll("[data-range]").forEach((x) => x.classList.toggle("active", x === b));
      state.statsRange = b.dataset.range;
      loadStats();
    })
  );
  $("#goal-minutes").addEventListener("change", loadStats);
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(renderCharts, 150);
  });
}

async function init() {
  $("#data-date").value = todayStr();
  $("#data-date").max = todayStr();
  const ok = await wakeServer();
  if (!ok) return;
  await Promise.all([loadSummary(), loadConversations(), loadRecords(), loadUsage()]);
}

applyTheme(document.documentElement.getAttribute("data-theme") || "light");
bindEvents();
init();
