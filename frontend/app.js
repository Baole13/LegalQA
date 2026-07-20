const questionInput = document.getElementById("question");
const askButton = document.getElementById("ask-btn");
const threadElement = document.getElementById("thread");
const requestStateElement = document.getElementById("request-state");
const healthStatusElement = document.getElementById("health-status");
const healthLabelElement = document.getElementById("health-label");
const detailModalElement = document.getElementById("detail-modal");
const detailBackdropElement = document.getElementById("detail-backdrop");
const detailCloseElement = document.getElementById("detail-close");
const detailTitleElement = document.getElementById("detail-title");
const detailMetaElement = document.getElementById("detail-meta");
const detailBodyElement = document.getElementById("detail-body");

let lastResponse = null;

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = `Yêu cầu thất bại (${response.status}).`;
    try {
      const payload = await response.json();
      if (payload?.detail) detail = payload.detail;
    } catch (_error) {
      // Phản hồi lỗi không phải JSON.
    }
    throw new Error(detail);
  }
  return response.json();
}

async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Không thể kết nối (${response.status}).`);
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

function setBusyState(isBusy, label) {
  askButton.disabled = isBusy;
  questionInput.disabled = isBusy;
  requestStateElement.textContent = label;
}

function appendMessage(role, contentHTML, title) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.innerHTML = `
    ${role === "assistant" ? '<div class="avatar" aria-hidden="true">LQ</div>' : ""}
    <div class="message-body">
      <p class="message-author">${escapeHTML(title)}</p>
      <div class="message-content">${contentHTML}</div>
    </div>
  `;
  threadElement.appendChild(article);
  article.scrollIntoView({ behavior: "smooth", block: "end" });
  return article;
}

function citationMeta(item) {
  const parts = [];
  if (item.title) parts.push(item.title);
  if (item.article) parts.push(`Điều ${item.article}`);
  if (item.clause) parts.push(`Khoản ${item.clause}`);
  return parts.join(" · ") || "Căn cứ pháp lý trong kho dữ liệu";
}

function renderList(items) {
  const values = (items || []).map((item) => String(item || "").trim()).filter(Boolean);
  if (!values.length) return "";
  return `<ul>${values.map((item) => `<li>${escapeHTML(item)}</li>`).join("")}</ul>`;
}

function renderCitations(citations) {
  if (!citations?.length) return "<p>Chưa tìm thấy căn cứ pháp lý đủ rõ để hiển thị.</p>";
  return `
    <div class="citation-list">
      ${citations
        .map(
          (item, index) => `
            <button class="citation-button" type="button" data-citation-index="${index}">
              <span>${escapeHTML(item.label || citationMeta(item))}</span>
              <span class="citation-arrow" aria-hidden="true">›</span>
            </button>
          `
        )
        .join("")}
    </div>
  `;
}

function renderEvidence(items) {
  if (!items?.length) return "<p>Không có dữ liệu truy xuất.</p>";
  return `
    <div class="evidence-list">
      ${items
        .map(
          (item, index) => `
            <article class="evidence-item">
              <header>
                <strong>Kết quả ${index + 1}${item.cid ? ` · CID ${escapeHTML(item.cid)}` : ""}</strong>
                <span>Điểm: ${escapeHTML(item.rerank_score ?? item.hybrid_score ?? "-")}</span>
              </header>
              <p>${escapeHTML(item.text || "Không có nội dung.")}</p>
            </article>
          `
        )
        .join("")}
    </div>
  `;
}

function confidenceLabel(value) {
  const labels = { low: "thấp", medium: "trung bình", high: "cao" };
  return labels[String(value || "").toLowerCase()] || value || "chưa xác định";
}

function renderAnswer(data) {
  const missingInfo = (data.missing_info || []).filter((item) => String(item || "").trim());
  const reasoning = String(data.reasoning || "").trim();
  return `
    <div class="answer">
      <div class="answer-meta">
        <span class="meta-badge">Độ tin cậy: ${escapeHTML(confidenceLabel(data.confidence))}</span>
      </div>
      <section class="answer-block">
        <h3>Trả lời</h3>
        <p>${escapeMultiline(data.answer || "Tôi không biết dựa trên các căn cứ hiện có.")}</p>
      </section>
      <section class="answer-block">
        <h3>Căn cứ pháp lý</h3>
        ${data.citations?.length ? renderCitations(data.citations) : renderList(data.legal_basis || []) || "<p>Chưa tìm thấy căn cứ pháp lý đủ rõ để hiển thị.<\/p>"}
      </section>
      ${reasoning ? `<section class="answer-block"><h3>Giải thích ngắn</h3><p>${escapeMultiline(reasoning)}</p></section>` : ""}
      ${missingInfo.length ? `<section class="answer-block"><h3>Thông tin còn thiếu</h3>${renderList(missingInfo)}</section>` : ""}
      <details class="technical-details">
        <summary class="technical-summary">Chi tiết kỹ thuật</summary>
        ${renderEvidence(data.retrieval || [])}
      </details>
    </div>
  `;
}

function openCitation(index) {
  const item = lastResponse?.citations?.[index];
  if (!item) return;
  detailTitleElement.textContent = item.label || citationMeta(item);
  detailMetaElement.textContent = [
    item.title || null,
    item.article ? `Điều ${item.article}` : null,
    item.clause ? `Khoản ${item.clause}` : null,
  ]
    .filter(Boolean)
    .join(" · ") || "Căn cứ pháp lý trong kho dữ liệu";
  const evidence = [...(lastResponse?.evidence || []), ...(lastResponse?.retrieval || [])].find(
    (candidate) => candidate.chunk_id === item.chunk_id || String(candidate.cid) === String(item.cid)
  );
  detailBodyElement.textContent = item.detail_text || item.text || evidence?.text || "Không có nội dung chi tiết.";
  detailModalElement.classList.remove("hidden");
  detailModalElement.setAttribute("aria-hidden", "false");
  detailCloseElement.focus();
}

function closeCitation() {
  detailModalElement.classList.add("hidden");
  detailModalElement.setAttribute("aria-hidden", "true");
}

async function loadHealth() {
  try {
    await getJSON("/health");
    healthStatusElement.classList.add("is-online");
    healthStatusElement.classList.remove("is-error");
    healthLabelElement.textContent = "Đã kết nối";
  } catch (_error) {
    healthStatusElement.classList.add("is-error");
    healthStatusElement.classList.remove("is-online");
    healthLabelElement.textContent = "Mất kết nối";
  }
}

async function askQuestion() {
  const question = questionInput.value.trim();
  if (!question) {
    questionInput.focus();
    return;
  }

  appendMessage("user", `<p>${escapeHTML(question)}</p>`, "Bạn");
  questionInput.value = "";
  questionInput.style.height = "auto";
  setBusyState(true, "Đang xử lý câu hỏi...");
  const placeholder = appendMessage(
    "assistant",
    '<div class="loading-row"><span class="spinner" aria-hidden="true"></span><span>Đang tìm và đối chiếu căn cứ pháp lý...</span></div>',
    "Trợ lý pháp lý"
  );

  try {
    const data = await postJSON("/ask", {
      question,
      top_k: 5,
      force_llm_reasoning: true,
      debug_llm: true,
    });
    lastResponse = data;
    placeholder.querySelector(".message-content").innerHTML = renderAnswer(data);
  } catch (error) {
    placeholder.querySelector(".message-content").innerHTML =
      `<p class="error-message">${escapeHTML(error.message || "Không thể xử lý câu hỏi.")}</p>`;
  } finally {
    setBusyState(false, "Sẵn sàng");
    questionInput.focus();
  }
}

askButton.addEventListener("click", askQuestion);
questionInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") askQuestion();
});
questionInput.addEventListener("input", () => {
  questionInput.style.height = "auto";
  questionInput.style.height = `${Math.min(questionInput.scrollHeight, 144)}px`;
});
threadElement.addEventListener("click", (event) => {
  const button = event.target.closest("[data-citation-index]");
  if (button) openCitation(Number(button.dataset.citationIndex));
});
detailCloseElement.addEventListener("click", closeCitation);
detailBackdropElement.addEventListener("click", closeCitation);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeCitation();
});

loadHealth();
