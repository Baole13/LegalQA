const questionInput = document.getElementById("question");
const askBtn = document.getElementById("ask-btn");
const debugBtn = document.getElementById("debug-btn");
const threadEl = document.getElementById("thread");
const debugEl = document.getElementById("debug");
const requestStateEl = document.getElementById("request-state");
const confidenceBadgeEl = document.getElementById("confidence-badge");
const generatorBadgeEl = document.getElementById("generator-badge");
const healthStatusEl = document.getElementById("health-status");
const healthModeEl = document.getElementById("health-mode");
const healthChunksEl = document.getElementById("health-chunks");
const healthRetrieverEl = document.getElementById("health-retriever");
const healthRerankerEl = document.getElementById("health-reranker");
const exampleButtons = document.querySelectorAll("[data-question]");
const detailModalEl = document.getElementById("detail-modal");
const detailBackdropEl = document.getElementById("detail-backdrop");
const detailCloseEl = document.getElementById("detail-close");
const detailTitleEl = document.getElementById("detail-title");
const detailMetaEl = document.getElementById("detail-meta");
const detailBodyEl = document.getElementById("detail-body");

let lastResponse = null;

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    try {
      const payload = await response.json();
      if (payload?.detail) detail = payload.detail;
    } catch (_error) {
      // ignore
    }
    throw new Error(detail);
  }
  return response.json();
}

async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

function escapeHTML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeMultiline(value) {
  return escapeHTML(value).replaceAll("\n", "<br>");
}

function numberOrDash(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return value.toFixed(3).replace(/\.000$/, "");
  return value;
}

function setBusyState(isBusy, label) {
  askBtn.disabled = isBusy;
  debugBtn.disabled = isBusy;
  requestStateEl.textContent = label;
}

function appendMessage(role, contentHTML, title) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.innerHTML = `
    <div class="avatar">${role === "assistant" ? "LQ" : "U"}</div>
    <div class="bubble ${role === "assistant" ? "assistant-bubble" : "user-bubble"}">
      <p class="message-title">${escapeHTML(title)}</p>
      <div class="message-content">${contentHTML}</div>
    </div>
  `;
  threadEl.appendChild(article);
  threadEl.scrollTop = threadEl.scrollHeight;
  article.scrollIntoView({ behavior: "smooth", block: "end" });
}

function splitSections(answer) {
  const sections = {
    "Ket luan": "",
    "Can cu phap ly": "",
    "Trich dan": "",
    "Luu y ap dung": "",
  };
  let current = null;
  for (const line of String(answer || "").split("\n")) {
    const trimmed = line.trim();
    if (sections[trimmed.replace(":", "")] !== undefined && trimmed.endsWith(":")) {
      current = trimmed.replace(":", "");
      continue;
    }
    if (current) sections[current] += `${line}\n`;
  }
  return sections;
}

function renderSectionBody(text) {
  const lines = String(text || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) return "<p>Khong co du lieu.</p>";
  const listLike = lines.every((line) => line.startsWith("-"));
  if (listLike) {
    return `<ul>${lines.map((line) => `<li>${escapeHTML(line.replace(/^-+\s*/, ""))}</li>`).join("")}</ul>`;
  }
  return `<p>${escapeMultiline(lines.join("\n"))}</p>`;
}

function citationMeta(item) {
  const parts = [];
  if (item.title) parts.push(item.title);
  if (item.article) parts.push(`Dieu ${item.article}`);
  if (item.clause) parts.push(`Khoan ${item.clause}`);
  return parts.join(" | ") || "Can cu phap ly trong corpus";
}

function renderCitationList(citations) {
  if (!citations?.length) return "<p>Khong co can cu phap ly duoc hien thi.</p>";
  return `
    <div class="citation-list">
      ${citations
        .map(
          (item, index) => `
            <button class="citation-link" type="button" data-detail-kind="citation" data-detail-index="${index}">
              <strong>${escapeHTML(item.label || citationMeta(item))}</strong>
              <span>${escapeHTML(item.article || item.clause ? "Bam de xem chi tiet dieu khoan." : "Bam de xem doan can cu.")}</span>
            </button>
          `
        )
        .join("")}
    </div>
  `;
}

function renderQuoteList(quotes) {
  if (!quotes?.length) return "<p>Khong co trich dan du manh de hien thi.</p>";
  return `
    <div class="quote-list">
      ${quotes
        .map(
          (item, index) => `
            <button class="quote-card" type="button" data-detail-kind="quote" data-detail-index="${index}">
              <strong>${escapeHTML(item.label || citationMeta(item))}</strong>
              <span>"${escapeHTML(item.text || "")}"</span>
            </button>
          `
        )
        .join("")}
    </div>
  `;
}

function renderAssistantAnswer(data) {
  const sections = splitSections(data.answer || "");
  const sourcePills = (data.citations || [])
    .slice(0, 3)
    .map((item) => `<span class="source-pill">${escapeHTML(item.label || citationMeta(item))}</span>`)
    .join("");

  return `
    <div class="answer-sections">
      <section class="answer-section">
        <h4>Ket luan</h4>
        ${renderSectionBody(sections["Ket luan"])}
      </section>
      <section class="answer-section">
        <h4>Can cu phap ly</h4>
        ${renderCitationList(data.citations || [])}
      </section>
      <section class="answer-section">
        <h4>Trich dan</h4>
        ${renderQuoteList(data.quotes || [])}
      </section>
      <section class="answer-section">
        <h4>Luu y ap dung</h4>
        ${renderSectionBody(sections["Luu y ap dung"])}
      </section>
      <div class="source-strip">${sourcePills || '<span class="source-pill">Khong co citation.</span>'}</div>
    </div>
  `;
}

function renderDebug(data) {
  if (!data?.length) return "Chua co du lieu.";
  return data
    .map(
      (item) => `
        <div class="card">
          <div class="card-header">
            <strong>${escapeHTML(item.chunk_id || "Result")}</strong>
            <span class="meta-pill">${escapeHTML(item.question_intent || "general")}</span>
          </div>
          <p>${escapeHTML(item.text || "")}</p>
          <div class="meta-row">
            <span class="meta-pill">CID: ${escapeHTML(item.cid || "?")}</span>
            <span class="meta-pill">Hybrid: ${escapeHTML(numberOrDash(item.hybrid_score))}</span>
            <span class="meta-pill">Rerank: ${escapeHTML(numberOrDash(item.rerank_score))}</span>
            <span class="meta-pill">Direct: ${escapeHTML(numberOrDash(item.direct_answer_score))}</span>
            <span class="meta-pill">Noise: ${escapeHTML(numberOrDash(item.procedural_noise))}</span>
          </div>
        </div>
      `
    )
    .join("");
}

function openDetail(kind, index) {
  if (!lastResponse) return;
  const source = kind === "quote" ? lastResponse.quotes || [] : lastResponse.citations || [];
  const item = source[index];
  if (!item) return;

  detailTitleEl.textContent = item.label || citationMeta(item);
  detailMetaEl.textContent = [
    item.title || null,
    item.article ? `Dieu ${item.article}` : null,
    item.clause ? `Khoan ${item.clause}` : null,
  ]
    .filter(Boolean)
    .join(" | ") || "Can cu phap ly trong corpus";
  detailBodyEl.textContent = item.detail_text || item.text || "Khong co noi dung chi tiet.";
  detailModalEl.classList.remove("hidden");
  detailModalEl.setAttribute("aria-hidden", "false");
}

function closeDetail() {
  detailModalEl.classList.add("hidden");
  detailModalEl.setAttribute("aria-hidden", "true");
}

async function loadHealth() {
  try {
    const data = await getJSON("/health");
    healthStatusEl.textContent = (data.status || "unknown").toUpperCase();
    healthModeEl.textContent = `${data.llm_loaded ? "LLM da nap" : "LLM chua nap"} | QA memory an khoi can cu cuoi`;
    healthChunksEl.textContent = data.chunks ?? "-";
    healthRetrieverEl.textContent = data.retriever_mode || "-";
    healthRerankerEl.textContent = data.reranker_mode || "-";
  } catch (error) {
    healthStatusEl.textContent = "ERROR";
    healthModeEl.textContent = error.message;
  }
}

async function askQuestion() {
  const question = questionInput.value.trim();
  if (!question) return;
  appendMessage("user", `<p>${escapeHTML(question)}</p>`, "Ban");
  questionInput.value = "";
  setBusyState(true, "Dang xu ly");
  appendMessage("assistant", "<p>Dang phan tich cau hoi, doi chieu can cu va chon dieu khoan phu hop...</p>", "Tro ly phap ly");
  const placeholder = threadEl.lastElementChild;

  try {
    const data = await postJSON("/ask", { question, top_k: 5 });
    lastResponse = data;
    confidenceBadgeEl.textContent = `Do tin cay: ${data.confidence || "-"}`;
    generatorBadgeEl.textContent = `Generator: ${data.generator_mode || "-"}`;
    placeholder.querySelector(".message-content").innerHTML = renderAssistantAnswer(data);
    debugEl.innerHTML = renderDebug(data.retrieval || []);
  } catch (error) {
    confidenceBadgeEl.textContent = "Do tin cay: loi";
    generatorBadgeEl.textContent = "Generator: -";
    placeholder.querySelector(".message-content").innerHTML = `<p>${escapeHTML(error.message)}</p>`;
  } finally {
    setBusyState(false, "San sang");
  }
}

async function debugRetrieval() {
  const question = questionInput.value.trim() || lastResponse?.question;
  if (!question) return;
  setBusyState(true, "Dang debug");
  debugEl.innerHTML = "Dang truy xuat retrieval...";
  try {
    const data = await postJSON("/retrieval_debug", { question, top_k: 10 });
    debugEl.innerHTML = renderDebug(data.results || []);
  } catch (error) {
    debugEl.textContent = error.message;
  } finally {
    setBusyState(false, "San sang");
  }
}

askBtn.addEventListener("click", askQuestion);
debugBtn.addEventListener("click", debugRetrieval);
questionInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") askQuestion();
});
exampleButtons.forEach((button) => {
  button.addEventListener("click", () => {
    questionInput.value = button.dataset.question || "";
    questionInput.focus();
  });
});
threadEl.addEventListener("click", (event) => {
  const button = event.target.closest("[data-detail-kind]");
  if (!button) return;
  openDetail(button.dataset.detailKind, Number(button.dataset.detailIndex));
});
detailCloseEl.addEventListener("click", closeDetail);
detailBackdropEl.addEventListener("click", closeDetail);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDetail();
});

loadHealth();
