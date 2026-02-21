const baseUrlInput = document.getElementById("baseUrl");
const apiKeyInput = document.getElementById("apiKey");
const sessionStatus = document.getElementById("sessionStatus");
const messagesEl = document.getElementById("messages");
const roleEl = document.getElementById("role");
const contentEl = document.getElementById("content");

let sessionId = null;

function getBaseUrl() {
  const candidate = baseUrlInput.value.trim();
  return candidate || window.location.origin;
}

function requestHeaders(includeContentType = true) {
  const headers = { "x-api-key": apiKeyInput.value.trim() };
  if (includeContentType) {
    headers["Content-Type"] = "application/json";
  }
  return headers;
}

function requireSession() {
  if (!sessionId) {
    throw new Error("Create a session first.");
  }
}

function requireNonEmptyMessage() {
  if (!contentEl.value.trim()) {
    throw new Error("Message content cannot be empty.");
  }
}

async function parseResponse(response) {
  const body = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(body));
  }
  return body;
}

async function createSession() {
  const response = await fetch(`${getBaseUrl()}/v1/chat/sessions`, {
    method: "POST",
    headers: requestHeaders(),
    body: JSON.stringify({}),
  });

  const body = await parseResponse(response);
  sessionId = body.id;
  sessionStatus.textContent = JSON.stringify(body, null, 2);
  await refreshMessages();
}

async function sendMessage() {
  requireSession();
  requireNonEmptyMessage();

  const response = await fetch(`${getBaseUrl()}/v1/chat/messages`, {
    method: "POST",
    headers: requestHeaders(),
    body: JSON.stringify({
      session_id: sessionId,
      role: roleEl.value,
      content: contentEl.value,
    }),
  });

  await parseResponse(response);
  contentEl.value = "";
  await refreshMessages();
}

async function refreshMessages() {
  requireSession();

  const response = await fetch(`${getBaseUrl()}/v1/chat/sessions/${sessionId}/messages`, {
    headers: requestHeaders(false),
  });

  const body = await parseResponse(response);
  messagesEl.textContent = JSON.stringify(body, null, 2);
}

function clearSession() {
  sessionId = null;
  sessionStatus.textContent = "No session created yet.";
  messagesEl.textContent = "[]";
}

function bind(id, fn) {
  document.getElementById(id).addEventListener("click", async () => {
    try {
      await fn();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      sessionStatus.textContent = message;
    }
  });
}

bind("createSession", createSession);
bind("sendMessage", sendMessage);
bind("refreshMessages", refreshMessages);
bind("clearSession", async () => clearSession());
