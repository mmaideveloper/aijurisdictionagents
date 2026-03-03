const baseUrlInput = document.getElementById("baseUrl");
const apiKeyInput = document.getElementById("apiKey");
const countryInput = document.getElementById("country");
const languageInput = document.getElementById("language");
const discussionTypeInput = document.getElementById("discussionType");
const sessionStatus = document.getElementById("sessionStatus");
const instructionInput = document.getElementById("instruction");
const questionTimeoutInput = document.getElementById("questionTimeout");
const maxDiscussionInput = document.getElementById("maxDiscussion");
const documentsInput = document.getElementById("documents");
const streamLog = document.getElementById("streamLog");
const agentQuestionsLog = document.getElementById("agentQuestionsLog");
const messagesEl = document.getElementById("messages");
const resultEl = document.getElementById("result");
const chatTranscriptEl = document.getElementById("chatTranscript");
const chatReplyForm = document.getElementById("chatReplyForm");
const userReplyInput = document.getElementById("userReplyInput");
const userSimulationModeInput = document.getElementById("userSimulationMode");
const communicationMinutesInput = document.getElementById("communicationMinutes");
const defaultsUrl = "/static/default-inputs.json";
const defaultLanguageCode = "SK";
const welcomeMessagesByLanguage = {
  SK: "Ahoj, som Jurisdicta. Pomozem vam s vasim pripadom. Popiste svoj problem a nahrajte relevantnu dokumentaciu.",
  EN: "Hello, I am Jurisdicta. I can help you with your case. Please describe your problem and upload relevant documentation.",
  GE: "Hallo, ich bin Jurisdicta. Ich kann Ihnen bei Ihrem Fall helfen. Bitte beschreiben Sie Ihr Problem und laden Sie relevante Unterlagen hoch.",
};

let sessionId = null;
let pdfRequestedByUser = false;
let thankYouDetected = false;
let autoPdfDownloaded = false;
let documentRequestedByUser = false;

function normalizeLanguageCode(languageCode) {
  const normalized = String(languageCode || "").trim().toUpperCase();
  if (normalized === "DE") return "GE";
  if (normalized === "SK" || normalized === "EN" || normalized === "GE") {
    return normalized;
  }
  return defaultLanguageCode;
}

function welcomeMessageForLanguage(languageCode) {
  const normalized = normalizeLanguageCode(languageCode);
  return welcomeMessagesByLanguage[normalized] || welcomeMessagesByLanguage[defaultLanguageCode];
}

function clearAgentQuestionsLog() {
  if (!agentQuestionsLog) return;
  agentQuestionsLog.textContent = "No AI agent questions yet.";
}

function appendAgentQuestion(question) {
  if (!agentQuestionsLog) return;
  const text = String(question || "").trim();
  if (!text) return;
  if (agentQuestionsLog.textContent === "No AI agent questions yet.") {
    agentQuestionsLog.textContent = text;
    return;
  }
  agentQuestionsLog.textContent += `\n${text}`;
  agentQuestionsLog.scrollTop = agentQuestionsLog.scrollHeight;
}

function extractAgentQuestion(text) {
  const raw = String(text || "");
  if (!raw.includes("?")) return "";
  const lines = raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => line.includes("?"));
  if (!lines.length) return "";
  const nonPdf = lines.filter((line) => !line.toLowerCase().includes("pdf"));
  const target = nonPdf.length ? nonPdf[nonPdf.length - 1] : lines[lines.length - 1];
  const fragments = target.match(/[^?]*\?/g);
  if (fragments && fragments.length) {
    return fragments[fragments.length - 1].trim();
  }
  return target;
}

function getBaseUrl() {
  return baseUrlInput.value.trim();
}

function ensureChatPlaceholder() {
  if (chatTranscriptEl.childElementCount > 0) return;
  const placeholder = document.createElement("p");
  placeholder.className = "chat-placeholder";
  placeholder.textContent = "No chat messages yet. Start a stream or refresh messages.";
  chatTranscriptEl.appendChild(placeholder);
}

function clearChatPlaceholder() {
  const placeholder = chatTranscriptEl.querySelector(".chat-placeholder");
  if (placeholder) placeholder.remove();
}

function createWelcomeMessage() {
  const normalizedLanguage = normalizeLanguageCode(languageInput.value);
  languageInput.value = normalizedLanguage;
  return {
    role: "assistant",
    content: welcomeMessageForLanguage(normalizedLanguage),
    agent_name: "Jurisdicta",
    _welcome: true,
  };
}

function isWelcomeOnlyTranscript() {
  const chatMessages = chatTranscriptEl.querySelectorAll(".chat-message");
  return chatMessages.length === 1 && chatMessages[0].dataset.welcome === "true";
}

function renderWelcomeMessage() {
  pdfRequestedByUser = false;
  thankYouDetected = false;
  documentRequestedByUser = false;
  chatTranscriptEl.innerHTML = "";
  clearAgentQuestionsLog();
  appendChatMessage(createWelcomeMessage());
}

function messageSpeaker(message) {
  if (message.role === "user") return "End user";
  if (message.agent_name) return `Core (${message.agent_name})`;
  return "Core system";
}

function isUserMessage(message) {
  return message.role === "user";
}

function hasPdfIntent(text) {
  const normalized = String(text || "").toLowerCase();
  return normalized.includes("pdf");
}

function hasDocumentIntent(text) {
  const normalized = String(text || "").toLowerCase();
  return (
    normalized.includes("vzor") ||
    normalized.includes("template") ||
    normalized.includes("zmluv") ||
    normalized.includes("contract") ||
    normalized.includes("dokument") ||
    normalized.includes("document") ||
    normalized.includes("draft")
  );
}

function hasThankYou(text) {
  const normalized = String(text || "").toLowerCase();
  return (
    normalized.includes("thank you") ||
    normalized.includes("thanks") ||
    normalized.includes("dakujem") ||
    normalized.includes("danke")
  );
}

function trackUserSignals(message) {
  if (!message || message.role !== "user") return;
  if (hasPdfIntent(message.content)) pdfRequestedByUser = true;
  if (hasDocumentIntent(message.content)) documentRequestedByUser = true;
  if (hasThankYou(message.content)) thankYouDetected = true;
}

function buildChatMessageNode(message) {
  const article = document.createElement("article");
  article.className = `chat-message ${isUserMessage(message) ? "user" : "core"}`;
  if (message && message._welcome === true) {
    article.dataset.welcome = "true";
  }

  const meta = document.createElement("span");
  meta.className = "chat-meta";
  meta.textContent = messageSpeaker(message);

  const body = document.createElement("p");
  body.textContent = message.content;

  article.append(meta, body);
  return article;
}

function appendChatMessage(message) {
  trackUserSignals(message);
  if (message && message.role === "assistant") {
    appendAgentQuestion(extractAgentQuestion(message.content));
  }
  clearChatPlaceholder();
  chatTranscriptEl.appendChild(buildChatMessageNode(message));
  chatTranscriptEl.scrollTop = chatTranscriptEl.scrollHeight;
}

function renderChatMessages(messages) {
  pdfRequestedByUser = false;
  thankYouDetected = false;
  documentRequestedByUser = false;
  chatTranscriptEl.innerHTML = "";
  clearAgentQuestionsLog();
  if (!Array.isArray(messages) || messages.length === 0) {
    appendChatMessage(createWelcomeMessage());
    return;
  }
  for (const message of messages) {
    trackUserSignals(message);
    if (message && message.role === "assistant") {
      appendAgentQuestion(extractAgentQuestion(message.content));
    }
    chatTranscriptEl.appendChild(buildChatMessageNode(message));
  }
  ensureChatPlaceholder();
  chatTranscriptEl.scrollTop = chatTranscriptEl.scrollHeight;
}

async function maybeAutoDownloadPdf() {
  if (autoPdfDownloaded) return;
  if (!pdfRequestedByUser || !thankYouDetected) return;
  try {
    await downloadResult("pdf", "summary");
    if (documentRequestedByUser) {
      await downloadResult("pdf", "document");
    }
    autoPdfDownloaded = true;
    appendStream("auto_download: PDF export(s) downloaded after user PDF request and thank you.");
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    appendStream(`auto_download_error: ${message}`);
  }
}

async function applyDefaultInputs() {
  try {
    const response = await fetch(defaultsUrl, { cache: "no-store" });
    if (!response.ok) return;
    const defaults = await response.json();

    if (typeof defaults.language === "string") {
      languageInput.value = normalizeLanguageCode(defaults.language);
    }
    if (typeof defaults.instruction === "string") {
      instructionInput.value = defaults.instruction;
    }
  } catch {
    // Keep current values if defaults file is missing or invalid.
  }
  if (!languageInput.value.trim()) {
    languageInput.value = defaultLanguageCode;
  }
  languageInput.value = normalizeLanguageCode(languageInput.value);
}

function requestHeaders(includeContentType = true) {
  const headers = { "x-api-key": apiKeyInput.value.trim() };
  if (includeContentType) headers["Content-Type"] = "application/json";
  return headers;
}

function requireSession() {
  if (!sessionId) throw new Error("Create a session first.");
}

function appendStream(text) {
  if (streamLog.textContent === "No stream started yet.") {
    streamLog.textContent = text;
    return;
  }
  streamLog.textContent += `\n${text}`;
  streamLog.scrollTop = streamLog.scrollHeight;
}

async function parseResponse(response) {
  const body = await response.json();
  if (!response.ok) throw new Error(JSON.stringify(body));
  return body;
}

async function createSession() {
  const normalizedLanguage = normalizeLanguageCode(languageInput.value);
  languageInput.value = normalizedLanguage;
  const payload = {
    country: countryInput.value.trim() || "SK",
    language: normalizedLanguage,
    discussion_type: discussionTypeInput.value,
  };
  const response = await fetch(`${getBaseUrl()}/v1/chat/sessions`, {
    method: "POST",
    headers: requestHeaders(),
    body: JSON.stringify(payload),
  });
  const body = await parseResponse(response);
  sessionId = body.id;
  pdfRequestedByUser = false;
  thankYouDetected = false;
  autoPdfDownloaded = false;
  documentRequestedByUser = false;
  sessionStatus.textContent = JSON.stringify(body, null, 2);
  await refreshMessages();
}

async function readSelectedDocuments() {
  const files = Array.from(documentsInput.files || []);
  const docs = [];
  for (const file of files) {
    const content = await file.text();
    docs.push({
      doc_id: file.name,
      path: file.name,
      content,
    });
  }
  return docs;
}

function parseSseChunk(rawChunk) {
  const events = [];
  const blocks = rawChunk.split("\n\n");
  for (const block of blocks) {
    const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
    if (!lines.length) continue;
    const eventLine = lines.find((line) => line.startsWith("event:"));
    const dataLine = lines.find((line) => line.startsWith("data:"));
    if (!eventLine || !dataLine) continue;
    const event = eventLine.slice(6).trim();
    const dataText = dataLine.slice(5).trim();
    try {
      events.push({ event, data: JSON.parse(dataText) });
    } catch {
      events.push({ event, data: dataText });
    }
  }
  return events;
}

async function startStream() {
  requireSession();
  const instruction = instructionInput.value.trim();
  if (!instruction) throw new Error("Case instruction is required.");

  streamLog.textContent = "Starting stream...";
  const payload = {
    instruction,
    documents: await readSelectedDocuments(),
    question_timeout_seconds: Number(questionTimeoutInput.value || 300),
    max_discussion_minutes: Number(maxDiscussionInput.value || 15),
    communication_minutes: Number(communicationMinutesInput.value || 3),
    user_simulation_mode: userSimulationModeInput.value || "AIUserSimulatorAgent",
  };

  const response = await fetch(`${getBaseUrl()}/v1/chat/sessions/${sessionId}/stream`, {
    method: "POST",
    headers: requestHeaders(),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Failed to stream, status=${response.status}`);
  }
  if (!response.body) {
    throw new Error("Streaming body is not available in this browser.");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  const reader = response.body.getReader();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const split = buffer.split("\n\n");
    buffer = split.pop() || "";

    for (const block of split) {
      const events = parseSseChunk(`${block}\n\n`);
      for (const eventItem of events) {
        appendStream(`${eventItem.event}: ${JSON.stringify(eventItem.data)}`);
        if (eventItem.event === "message" && eventItem.data && typeof eventItem.data === "object") {
          appendChatMessage(eventItem.data);
        }
        if (eventItem.event === "done") {
          await maybeAutoDownloadPdf();
        }
      }
    }
  }

  if (buffer.trim()) {
    const trailingEvents = parseSseChunk(buffer);
    for (const eventItem of trailingEvents) {
      appendStream(`${eventItem.event}: ${JSON.stringify(eventItem.data)}`);
      if (eventItem.event === "message" && eventItem.data && typeof eventItem.data === "object") {
        appendChatMessage(eventItem.data);
      }
      if (eventItem.event === "done") {
        await maybeAutoDownloadPdf();
      }
    }
  }

  await refreshMessages();
  await maybeAutoDownloadPdf();
}

async function refreshMessages() {
  requireSession();
  const response = await fetch(`${getBaseUrl()}/v1/chat/sessions/${sessionId}/messages`, {
    headers: requestHeaders(false),
  });
  const body = await parseResponse(response);
  messagesEl.textContent = JSON.stringify(body, null, 2);
  renderChatMessages(body);
}

async function sendUserReply() {
  requireSession();
  const content = userReplyInput.value.trim();
  if (!content) throw new Error("End user answer is required.");

  const response = await fetch(`${getBaseUrl()}/v1/chat/sessions/${sessionId}/reply`, {
    method: "POST",
    headers: requestHeaders(),
    body: JSON.stringify({ content }),
  });

  const lawyerReply = await parseResponse(response);
  appendChatMessage({ role: "user", content, agent_name: "User" });
  appendChatMessage(lawyerReply);
  userReplyInput.value = "";
  appendStream(`user_reply: ${content}`);
  await refreshMessages();
}

async function getResult() {
  requireSession();
  const response = await fetch(`${getBaseUrl()}/v1/chat/sessions/${sessionId}/result`, {
    headers: requestHeaders(false),
  });
  const body = await parseResponse(response);
  resultEl.textContent = JSON.stringify(body, null, 2);
}

async function downloadResult(format, kind = "summary") {
  requireSession();
  const url = `${getBaseUrl()}/v1/chat/sessions/${sessionId}/export?format=${format}&kind=${encodeURIComponent(kind)}`;
  const response = await fetch(url, {
    headers: requestHeaders(false),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }

  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  const headerName = extractFilenameFromContentDisposition(response.headers.get("Content-Disposition"));
  if (headerName) {
    anchor.download = headerName;
  } else {
    anchor.download = createFallbackFilename(kind, format);
  }
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}

function extractFilenameFromContentDisposition(value) {
  const header = String(value || "");
  if (!header) return "";
  const match = header.match(/filename="([^"]+)"/i);
  if (match && match[1]) return match[1];
  return "";
}

function createFallbackFilename(kind, format) {
  const now = new Date();
  const yyyy = String(now.getFullYear());
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  const hh = String(now.getHours()).padStart(2, "0");
  const mi = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  const ts = `${yyyy}${mm}${dd}${hh}${mi}${ss}`;
  const docName = kind === "document" ? "final-document" : "discussion-summary";
  return `${sessionId}-${ts}-${docName}.${format}`;
}

function clearSession() {
  sessionId = null;
  pdfRequestedByUser = false;
  thankYouDetected = false;
  autoPdfDownloaded = false;
  documentRequestedByUser = false;
  sessionStatus.textContent = "No session created yet.";
  streamLog.textContent = "No stream started yet.";
  clearAgentQuestionsLog();
  messagesEl.textContent = "[]";
  resultEl.textContent = "No result fetched yet.";
  renderWelcomeMessage();
  userReplyInput.value = "";
}

function bind(id, fn) {
  document.getElementById(id).addEventListener("click", async () => {
    try {
      await fn();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      appendStream(`error: ${message}`);
      sessionStatus.textContent = message;
    }
  });
}

bind("createSession", createSession);
bind("startStream", startStream);
bind("refreshMessages", refreshMessages);
bind("getResult", getResult);
bind("downloadJson", async () => downloadResult("json"));
bind("downloadPdf", async () => downloadResult("pdf", "summary"));
const downloadDocumentButton = document.getElementById("downloadDocumentPdf");
if (downloadDocumentButton) {
  downloadDocumentButton.addEventListener("click", async () => {
    try {
      await downloadResult("pdf", "document");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      appendStream(`error: ${message}`);
      sessionStatus.textContent = message;
    }
  });
}
bind("clearSession", async () => clearSession());

chatReplyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await sendUserReply();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    appendStream(`error: ${message}`);
    sessionStatus.textContent = message;
  }
});

userSimulationModeInput.addEventListener("change", () => {
  const readUserMode = userSimulationModeInput.value === "ReadUser";
  userReplyInput.required = readUserMode;
  userReplyInput.disabled = !readUserMode;
});
languageInput.addEventListener("input", () => {
  languageInput.value = normalizeLanguageCode(languageInput.value);
  if (!sessionId || isWelcomeOnlyTranscript()) {
    renderWelcomeMessage();
  }
});

async function initializeSimulator() {
  await applyDefaultInputs();
  renderWelcomeMessage();
  userSimulationModeInput.dispatchEvent(new Event("change"));
}

initializeSimulator();
