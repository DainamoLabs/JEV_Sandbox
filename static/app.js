"use strict";

const $ = (id) => document.getElementById(id);
let examples = [];
let selected = null;
let busy = false;
let rows = [];

function showError(message = "") {
  $("error").textContent = message;
  $("error").hidden = !message;
}

function resizeQuestion(input) {
  input.style.height = "auto";
  input.style.height = `${input.scrollHeight}px`;
}

function clearResults() {
  for (const row of rows) {
    row.percent.textContent = "—";
    row.percent.classList.add("pending");
    row.verdict.textContent = "";
    row.card.removeAttribute("data-verdict");
    row.fill.style.width = "0%";
    row.meter.removeAttribute("aria-valuenow");
    row.meter.setAttribute("aria-valuetext", "Not evaluated");
  }
  $("elapsed").textContent = "";
  $("announcement").textContent = "";
  $("run-status").textContent = "Ready when you are.";
  showError();
}

function updateContext() {
  $("state").dataset.format = $("format").value;
  $("char-count").textContent = `${$("state").value.length.toLocaleString()} characters`;
  clearResults();
}

function selectExample(id) {
  if (busy) return;
  selected = examples.find((example) => example.id === id);
  if (!selected) return;
  for (const button of $("presets").children) {
    button.setAttribute("aria-pressed", String(button.dataset.id === id));
  }
  const state = selected.request.state;
  $("format").value = typeof state === "string" ? "text" : "json";
  $("state").value = typeof state === "string" ? state : JSON.stringify(state, null, 2);
  $("questions").replaceChildren();
  rows = Object.entries(selected.request.questions).map(([name, question], index) => {
    const card = document.createElement("article");
    card.className = "question-card";
    card.innerHTML = `<div class="question-top"><label class="question-name"><span class="question-number"></span><span class="name"></span></label><span class="verdict"></span></div><div class="question-main"><textarea class="question-input" rows="2" required maxlength="4000"></textarea><output class="probability pending">—</output></div><div class="meter" role="meter" aria-valuemin="0" aria-valuemax="100"><div class="meter-fill"></div></div>`;
    const input = card.querySelector("textarea");
    input.id = `question-${index}`;
    input.value = question.instructions;
    card.querySelector("label").htmlFor = input.id;
    card.querySelector(".question-number").textContent = String(index + 1).padStart(2, "0");
    card.querySelector(".name").textContent = name.replaceAll("_", " ");
    const meter = card.querySelector(".meter");
    meter.setAttribute("aria-label", `Probability of yes: ${name.replaceAll("_", " ")}`);
    input.addEventListener("input", () => { resizeQuestion(input); clearResults(); });
    $("questions").append(card);
    return { name, input, card, meter, percent: card.querySelector("output"), verdict: card.querySelector(".verdict"), fill: card.querySelector(".meter-fill") };
  });
  requestAnimationFrame(() => rows.forEach((row) => resizeQuestion(row.input)));
  $("run").disabled = false;
  $("reset").disabled = false;
  updateContext();
}

function setBusy(value) {
  busy = value;
  $("demo-form").setAttribute("aria-busy", String(value));
  for (const control of document.querySelectorAll("#demo-form textarea, #demo-form select, #run, #reset, .preset")) {
    control.disabled = value;
  }
  $("run-label").textContent = value ? "Thinking…" : "Run decisions";
}

async function readJson(result) {
  const data = await result.json();
  if (!result.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((item) => item.msg).join(" ") : data.detail;
    throw new Error(detail || "The request failed. Please try again.");
  }
  return data;
}

function requestBody() {
  let state = $("state").value;
  if (!state.trim()) throw new Error("Enter some context first.");
  if ($("format").value === "json") {
    try { state = JSON.parse(state); } catch { throw new Error("The context is not valid JSON. Fix it, or switch the format to Text."); }
    if (state === null || typeof state !== "object" || !Object.keys(state).length) {
      throw new Error("JSON context must be a nonempty object or conversation array.");
    }
  }
  const questions = Object.fromEntries(rows.map(({ name, input }) => {
    if (!input.value.trim()) throw new Error("Each decision needs a question.");
    return [name, { type: "noul", instructions: input.value.trim() }];
  }));
  return { state, questions };
}

async function runDecisions() {
  if (busy || !selected) return;
  clearResults();
  let payload;
  try { payload = requestBody(); } catch (error) { showError(error.message); return; }
  setBusy(true);
  $("run-status").textContent = `Evaluating ${rows.length} ${rows.length === 1 ? "question" : "questions"}…`;
  try {
    const result = await fetch("/api/decide", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    const data = await readJson(result);
    const probabilities = rows.map((row) => data.answers?.[row.name]?.noul);
    if (probabilities.some((p) => typeof p !== "number" || !Number.isFinite(p) || p < 0 || p > 1)) {
      throw new Error("The model returned an invalid probability. Please try again.");
    }
    rows.forEach((row, index) => {
      const p = probabilities[index];
      const percent = (p * 100).toFixed(1);
      const verdict = p === 0.5 ? "Even" : p > 0.5 ? "Yes" : "No";
      row.percent.classList.remove("pending");
      row.percent.replaceChildren(document.createTextNode(percent));
      const sign = document.createElement("small");
      sign.textContent = "%";
      row.percent.append(sign);
      row.verdict.textContent = verdict;
      row.card.dataset.verdict = verdict.toLowerCase();
      row.fill.style.width = `${p * 100}%`;
      row.meter.setAttribute("aria-valuenow", String(p * 100));
      row.meter.setAttribute("aria-valuetext", `${percent}% probability of yes`);
    });
    $("run-status").textContent = `${rows.length} ${rows.length === 1 ? "decision" : "decisions"} complete`;
    $("elapsed").textContent = data.elapsed_ms < 1000 ? `${data.elapsed_ms} ms` : `${(data.elapsed_ms / 1000).toFixed(2)} s`;
    $("announcement").textContent = rows.map((row, i) => `${row.input.value} ${(probabilities[i] * 100).toFixed(1)}% yes.`).join(" ");
    setConnection(true);
    return data;
  } catch (error) {
    showError(error.message === "Failed to fetch" ? "The demo server is unavailable. Restart it and try again." : error.message);
    $("run-status").textContent = "Run failed. Your inputs are saved here.";
    void checkConnection();
  } finally {
    setBusy(false);
  }
}

function setConnection(ready) {
  $("connection").dataset.ready = String(ready);
  $("connection-label").textContent = ready ? "Model connected" : "Model offline · retry";
}

async function checkConnection() {
  try {
    const result = await fetch("/api/health");
    const data = await readJson(result);
    setConnection(data.ready === true);
  } catch { setConnection(false); }
}

$("demo-form").addEventListener("submit", (event) => { event.preventDefault(); void runDecisions(); });
$("state").addEventListener("input", updateContext);
$("format").addEventListener("change", updateContext);
$("reset").addEventListener("click", () => { if (selected) selectExample(selected.id); });
$("connection").addEventListener("click", checkConnection);
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); void runDecisions(); }
});
window.addEventListener("resize", () => rows.forEach((row) => resizeQuestion(row.input)));
if (/Mac|iPhone|iPad/.test(navigator.platform)) $("shortcut").textContent = "⌘ ↵";

async function init() {
  void checkConnection();
  try {
    examples = await readJson(await fetch("/api/examples"));
    for (const example of examples) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "preset";
      button.dataset.id = example.id;
      button.textContent = example.label;
      button.addEventListener("click", () => selectExample(example.id));
      $("presets").append(button);
    }
    selectExample("plain");
  } catch { showError("Could not load the examples. Refresh the page to try again."); }
}

void init();

// Optional browser agent access uses the same action and edited inputs as the UI.
if (document.modelContext?.registerTool) {
  const lifecycle = new AbortController();
  window.addEventListener("pagehide", () => lifecycle.abort(), { once: true });
  try {
    Promise.resolve(document.modelContext.registerTool({
      name: "run_decisions", title: "Run decisions",
      description: "Evaluate the context and questions currently shown in the playground and display the probabilities.",
      inputSchema: { type: "object", properties: {}, additionalProperties: false },
      annotations: { readOnlyHint: false },
      execute: async () => {
        if (busy || !selected) throw new Error("The playground is not ready.");
        const result = await runDecisions();
        if (!result) throw new Error($("error").textContent || "Evaluation failed.");
        return result;
      },
    }, { signal: lifecycle.signal })).catch(() => {});
  } catch { /* Browsers without WebMCP still have the full interface. */ }
}
