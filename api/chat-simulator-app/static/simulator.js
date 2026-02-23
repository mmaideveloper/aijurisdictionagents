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
const messagesEl = document.getElementById("messages");
const resultEl = document.getElementById("result");
const chatTranscriptEl = document.getElementById("chatTranscript");
const chatReplyForm = document.getElementById("chatReplyForm");
const userReplyInput = document.getElementById("userReplyInput");
const defaultsUrl = "/static/default-inputs.json";

let sessionId = null;

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

function messageSpeaker(message) {
  if (message.role === "user") return "End user";
  if (message.agent_name) return `Core (${message.agent_name})`;
  return "Core system";
}

function isUserMessage(message) {
  return message.role === "user";
}

function buildChatMessageNode(message) {
  const article = document.createElement("article");
  article.className = `chat-message ${isUserMessage(message) ? "user" : "core"}`;

  const meta = document.createElement("span");
  meta.className = "chat-meta";
  meta.textContent = messageSpeaker(message);

  const body = document.createElement("p");
  body.textContent = message.content;

  article.append(meta, body);
  return article;
}

function appendChatMessage(message) {
  clearChatPlaceholder();
  chatTranscriptEl.appendChild(buildChatMessageNode(message));
  chatTranscriptEl.scrollTop = chatTranscriptEl.scrollHeight;
}

function renderChatMessages(messages) {
  chatTranscriptEl.innerHTML = "";
  for (const message of messages) {
    chatTranscriptEl.appendChild(buildChatMessageNode(message));
  }
  ensureChatPlaceholder();
  chatTranscriptEl.scrollTop = chatTranscriptEl.scrollHeight;
}

async function applyDefaultInputs() {
  try {
    const response = await fetch(defaultsUrl, { cache: "no-store" });
    if (!response.ok) return;
    const defaults = await response.json();

    if (typeof defaults.language === "string") {
      languageInput.value = defaults.language;
    }
    if (typeof defaults.instruction === "string") {
      instructionInput.value = defaults.instruction;
    }
  } catch {
    // Keep current values if defaults file is missing or invalid.
  }
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
  const payload = {
    country: countryInput.value.trim() || "SK",
    language: languageInput.value.trim() || null,
    discussion_type: discussionTypeInput.value,
  };
  const response = await fetch(`${getBaseUrl()}/v1/chat/sessions`, {
    method: "POST",
    headers: requestHeaders(),
    body: JSON.stringify(payload),
  });
  const body = await parseResponse(response);
  sessionId = body.id;
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
    }
  }

  await refreshMessages();
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

  const response = await fetch(`${getBaseUrl()}/v1/chat/messages`, {
    method: "POST",
    headers: requestHeaders(),
    body: JSON.stringify({
      session_id: sessionId,
      role: "user",
      content,
    }),
  });

  const body = await parseResponse(response);
  appendChatMessage(body);
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

async function downloadResult(format) {
  requireSession();
  const response = await fetch(`${getBaseUrl()}/v1/chat/sessions/${sessionId}/export?format=${format}`, {
    headers: requestHeaders(false),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }

  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = `session-${sessionId}.${format}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}

function clearSession() {
  sessionId = null;
  sessionStatus.textContent = "No session created yet.";
  streamLog.textContent = "No stream started yet.";
  messagesEl.textContent = "[]";
  resultEl.textContent = "No result fetched yet.";
  chatTranscriptEl.innerHTML = "";
  ensureChatPlaceholder();
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
bind("downloadPdf", async () => downloadResult("pdf"));
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

ensureChatPlaceholder();
applyDefaultInputs();
