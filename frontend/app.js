const questionInput = document.getElementById("question");
const askBtn = document.getElementById("ask-btn");
const debugBtn = document.getElementById("debug-btn");

const answerEl = document.getElementById("answer");
const citationsEl = document.getElementById("citations");
const evidenceEl = document.getElementById("evidence");
const debugEl = document.getElementById("debug");

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function renderList(items, formatter) {
  if (!items || !items.length) return "<p class='muted'>Không có dữ liệu.</p>";
  return items.map(formatter).join("");
}

async function askQuestion() {
  const question = questionInput.value.trim();
  if (!question) return;
  answerEl.innerHTML = "<p class='muted'>Đang xử lý truy vấn...</p>";
  try {
    const data = await postJSON("/ask", { question, top_k: 5 });
    answerEl.innerHTML = `
      <div class="card">
        <strong>Độ tin cậy: ${data.confidence || "unknown"}</strong>
        <p>${data.answer || "Không có câu trả lời."}</p>
      </div>
    `;
    citationsEl.innerHTML = renderList(
      data.citations,
      (item) =>
        `<div class="card"><strong>${item.title || "Citation"}</strong><p>CID: ${item.cid || "?"} | Điều: ${item.article || "?"} | Khoản: ${item.clause || "?"}</p></div>`
    );
    evidenceEl.innerHTML = renderList(
      data.evidence,
      (item) =>
        `<div class="card"><strong>${item.chunk_id}</strong><p>Score: ${item.score || 0} | Keyword: ${item.keyword_coverage || 0} | Phrase: ${item.phrase_coverage || 0}</p><p>${item.text}</p></div>`
    );
    debugEl.innerHTML = renderList(
      data.retrieval,
      (item) =>
        `<div class="card"><strong>${item.chunk_id}</strong><p>BM25: ${item.bm25_score || 0} | Dense: ${item.dense_score || 0} | QA: ${item.qa_boost || 0} | Hybrid: ${item.hybrid_score || 0} | Rerank: ${item.rerank_score || 0}</p><p>${item.text}</p></div>`
    );
  } catch (error) {
    answerEl.textContent = `Lỗi: ${error.message}`;
  }
}

async function debugRetrieval() {
  const question = questionInput.value.trim();
  if (!question) return;
  debugEl.innerHTML = "<p class='muted'>Đang truy xuất...</p>";
  try {
    const data = await postJSON("/retrieval_debug", { question, top_k: 10 });
    const similarQuestions = renderList(
      data.similar_questions,
      (item) =>
        `<div class="card"><strong>QA memory</strong><p>${item.question}</p><p>CIDs: ${(item.cids || []).join(", ")} | Score: ${item.qa_score || 0}</p></div>`
    );
    const retrievalResults = renderList(
      data.results,
      (item) =>
        `<div class="card"><strong>${item.chunk_id}</strong><p>CID: ${item.cid} | BM25: ${item.bm25_score || 0} | Dense: ${item.dense_score || 0} | QA: ${item.qa_boost || 0} | Hybrid: ${item.hybrid_score || 0}</p><p>${item.text}</p></div>`
    );
    debugEl.innerHTML = similarQuestions + retrievalResults;
  } catch (error) {
    debugEl.textContent = `Lỗi: ${error.message}`;
  }
}

askBtn.addEventListener("click", askQuestion);
debugBtn.addEventListener("click", debugRetrieval);
