const baseUrlInput = document.getElementById("baseUrl");
const apiKeyInput = document.getElementById("apiKey");
const countryInput = document.getElementById("country");
const languageInput = document.getElementById("language");
const discussionTypeInput = document.getElementById("discussionType");
const sessionStatus = document.getElementById("sessionStatus");
const caseStatus = document.getElementById("caseStatus");
const workflowWarning = document.getElementById("workflowWarning");
const instructionInput = document.getElementById("instruction");
const questionTimeoutInput = document.getElementById("questionTimeout");
const maxDiscussionInput = document.getElementById("maxDiscussion");
const documentsInput = document.getElementById("documents");
const debugQueryInput = document.getElementById("debugQuery");
const streamLog = document.getElementById("streamLog");
const agentQuestionsLog = document.getElementById("agentQuestionsLog");
const messagesEl = document.getElementById("messages");
const resultEl = document.getElementById("result");
const documentDebugEl = document.getElementById("documentDebug");
const chatTranscriptEl = document.getElementById("chatTranscript");
const chatReplyForm = document.getElementById("chatReplyForm");
const userReplyInput = document.getElementById("userReplyInput");
const userSimulationModeInput = document.getElementById("userSimulationMode");
const sendUserReplyButton = document.getElementById("sendUserReply");
const replyStatus = document.getElementById("replyStatus");
const communicationMinutesInput = document.getElementById("communicationMinutes");
const userPhoneInput = document.getElementById("userPhone");
const userEmailInput = document.getElementById("userEmail");
const userPasswordInput = document.getElementById("userPassword");
const caseTitleInput = document.getElementById("caseTitle");
const defaultsUrl = "/static/default-inputs.json";
const defaultLanguageCode = "SK";
const welcomeMessagesByLanguage = {
  SK: "Ahoj, som Jurisdicta. Pomozem vam s vasim pripadom. Popiste svoj problem a nahrajte relevantnu dokumentaciu.",
  EN: "Hello, I am Jurisdicta. I can help you with your case. Please describe your problem and upload relevant documentation.",
  GE: "Hallo, ich bin Jurisdicta. Ich kann Ihnen bei Ihrem Fall helfen. Bitte beschreiben Sie Ihr Problem und laden Sie relevante Unterlagen hoch.",
};

let sessionId = null;
let currentUserId = null;
let currentCaseId = null;
let currentSessionCaseId = null;
let hasUploadedCaseDocuments = false;
let waitingForManualReply = false;
let streamStartedForSession = false;
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
  return normalizeApiBaseUrl(baseUrlInput.value);
}

function isLoopbackHostname(hostname) {
  const normalized = String(hostname || "").trim().toLowerCase();
  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "[::1]" || normalized === "::1";
}

function defaultApiBaseUrl() {
  const protocol = window.location.protocol === "https:" ? "https:" : "http:";
  const hostname = window.location.hostname || "127.0.0.1";
  const resolvedHost = isLoopbackHostname(hostname) ? hostname : "127.0.0.1";
  return `${protocol}//${resolvedHost}:8080`;
}

function normalizeApiBaseUrl(value) {
  const raw = String(value || "").trim();
  if (!raw) return defaultApiBaseUrl();
  try {
    const parsed = new URL(raw);
    const pageHost = window.location.hostname || "127.0.0.1";
    if (isLoopbackHostname(parsed.hostname) && isLoopbackHostname(pageHost) && parsed.hostname !== pageHost) {
      parsed.hostname = pageHost;
      return parsed.toString().replace(/\/$/, "");
    }
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return raw;
  }
}

function getActiveUserId() {
  return currentUserId;
}

function getActiveCaseId() {
  return currentCaseId;
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

async function safeParseJson(response) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

function updateCaseStatus(payload) {
  caseStatus.textContent = JSON.stringify(payload, null, 2);
}

function setWorkflowWarning(message) {
  workflowWarning.textContent = String(message || "").trim() || "No workflow warnings.";
}

function clearWorkflowWarning() {
  setWorkflowWarning("No workflow warnings.");
}

function setReplyStatus(message) {
  if (!replyStatus) return;
  replyStatus.textContent = String(message || "").trim();
}

function selectedDocumentCount() {
  return Array.from(documentsInput.files || []).length;
}

function hasBoundSessionForCurrentCase() {
  if (!sessionId) return false;
  if (!currentCaseId) return true;
  return currentSessionCaseId === currentCaseId;
}

function invalidateSession(reason) {
  if (!sessionId) {
    if (reason) setWorkflowWarning(reason);
    refreshReplyControls();
    return;
  }
  clearSession();
  if (reason) setWorkflowWarning(reason);
  refreshReplyControls();
}

function requirePersistedWorkflow(step) {
  if (!currentUserId) {
    throw new Error(`Ensure User first before ${step}.`);
  }
  if (!currentCaseId) {
    throw new Error(`Create Case first before ${step}.`);
  }
  if (!hasUploadedCaseDocuments) {
    throw new Error(`Upload To Case first before ${step}.`);
  }
}

function assistantRequestsReply(message) {
  return String(message || "").includes("?");
}

function refreshReplyControls() {
  const readUserMode = userSimulationModeInput.value === "ReadUser";
  const hasSession = Boolean(sessionId);
  const canSendManualReply =
    readUserMode && hasSession && (!streamStartedForSession || waitingForManualReply);

  userReplyInput.disabled = !readUserMode;
  sendUserReplyButton.disabled = !canSendManualReply;

  if (!readUserMode) {
    setReplyStatus("Manual Send answer is available only in ReadUser mode.");
    return;
  }
  if (!hasSession) {
    setReplyStatus("Create Session to enable manual answers.");
    return;
  }
  if (!streamStartedForSession) {
    setReplyStatus("Type an answer and click Send answer. The simulator will start the stream automatically.");
    return;
  }
  if (!waitingForManualReply) {
    setReplyStatus("Manual reply is available after the assistant asks a question.");
    return;
  }
  setReplyStatus("Assistant is waiting. Type an answer and click Send answer.");
}

async function ensureUser() {
  const previousUserId = currentUserId;
  const signUpPayload = {
    phone_number: userPhoneInput.value.trim(),
    email: userEmailInput.value.trim(),
    password: userPasswordInput.value.trim(),
  };
  if (!signUpPayload.phone_number || !signUpPayload.email || !signUpPayload.password) {
    throw new Error("User phone, email, and password are required.");
  }

  const signUpResponse = await fetch(`${getBaseUrl()}/v1/users/sign-up`, {
    method: "POST",
    headers: requestHeaders(),
    body: JSON.stringify(signUpPayload),
  });
  if (signUpResponse.ok) {
    const created = await signUpResponse.json();
    currentUserId = created.user_id;
    if (previousUserId && previousUserId !== currentUserId) {
      currentCaseId = null;
      hasUploadedCaseDocuments = false;
      invalidateSession("User changed. Start again with Create Case, Upload To Case, then Create Session.");
    } else {
      clearWorkflowWarning();
    }
    updateCaseStatus({ mode: "created_user", user: created, case_id: currentCaseId });
    return created;
  }

  const signUpError = await safeParseJson(signUpResponse);
  if (signUpResponse.status !== 409) {
    throw new Error(JSON.stringify(signUpError));
  }

  const phoneSignInResponse = await fetch(`${getBaseUrl()}/v1/users/sign-in/phone`, {
    method: "POST",
    headers: requestHeaders(),
    body: JSON.stringify({ phone_number: signUpPayload.phone_number }),
  });
  if (phoneSignInResponse.ok) {
    const existing = await phoneSignInResponse.json();
    currentUserId = existing.user_id;
    if (previousUserId && previousUserId !== currentUserId) {
      currentCaseId = null;
      hasUploadedCaseDocuments = false;
      invalidateSession("User changed. Start again with Create Case, Upload To Case, then Create Session.");
    } else {
      clearWorkflowWarning();
    }
    updateCaseStatus({ mode: "loaded_user_by_phone", user: existing, case_id: currentCaseId });
    return existing;
  }

  const signInResponse = await fetch(`${getBaseUrl()}/v1/users/sign-in`, {
    method: "POST",
    headers: requestHeaders(),
    body: JSON.stringify({ email: signUpPayload.email, password: signUpPayload.password }),
  });
  const user = await safeParseJson(signInResponse);
  if (!signInResponse.ok) {
    throw new Error(JSON.stringify(user));
  }
  currentUserId = user.user_id;
  if (previousUserId && previousUserId !== currentUserId) {
    currentCaseId = null;
    hasUploadedCaseDocuments = false;
    invalidateSession("User changed. Start again with Create Case, Upload To Case, then Create Session.");
  } else {
    clearWorkflowWarning();
  }
  updateCaseStatus({ mode: "loaded_user_by_email", user, case_id: currentCaseId });
  return user;
}

async function createPersistedCase() {
  if (!getActiveUserId()) {
    await ensureUser();
  }
  const payload = {
    user_id: getActiveUserId(),
    title: caseTitleInput.value.trim() || "Simulator persisted case",
  };
  const response = await fetch(`${getBaseUrl()}/v1/cases`, {
    method: "POST",
    headers: requestHeaders(),
    body: JSON.stringify(payload),
  });
  const body = await parseResponse(response);
  currentCaseId = body.case_id;
  hasUploadedCaseDocuments = false;
  invalidateSession("Case created. Next step: Upload To Case, then Create Session.");
  updateCaseStatus({ mode: "created_case", user_id: currentUserId, case: body });
  return body;
}

async function uploadCaseDocuments() {
  if (!getActiveCaseId() || !getActiveUserId()) {
    throw new Error("Create or load a persisted user and case first.");
  }
  const files = Array.from(documentsInput.files || []);
  if (!files.length) {
    throw new Error("Select at least one document first.");
  }

  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  const response = await fetch(
    `${getBaseUrl()}/v1/cases/${encodeURIComponent(getActiveCaseId())}/documents?user_id=${encodeURIComponent(getActiveUserId())}`,
    {
      method: "POST",
      headers: requestHeaders(false),
      body: formData,
    },
  );
  const body = await parseResponse(response);
  hasUploadedCaseDocuments = true;
  invalidateSession("Documents uploaded to the active case. Create Session again before starting the stream.");
  updateCaseStatus({
    mode: "uploaded_case_documents",
    user_id: currentUserId,
    case_id: currentCaseId,
    upload: body,
  });
  await inspectCaseDocuments();
  return body;
}

async function inspectCaseDocuments() {
  if (!getActiveCaseId() || !getActiveUserId()) {
    throw new Error("Create or load a persisted user and case first.");
  }
  const query =
    debugQueryInput.value.trim() || userReplyInput.value.trim() || instructionInput.value.trim();
  const params = new URLSearchParams({
    user_id: getActiveUserId(),
    query,
  });
  const response = await fetch(
    `${getBaseUrl()}/v1/cases/${encodeURIComponent(getActiveCaseId())}/documents/debug?${params.toString()}`,
    {
      headers: requestHeaders(false),
    },
  );
  const body = await parseResponse(response);
  hasUploadedCaseDocuments = Array.isArray(body.stored_documents) && body.stored_documents.length > 0;
  documentDebugEl.textContent = JSON.stringify(body, null, 2);
  appendStream(
    `document_debug: db_option=${body.db_option} stored_documents=${body.stored_documents.length} selected_prompt_chunks=${body.selected_prompt_chunks.length}`,
  );
  if (!hasUploadedCaseDocuments) {
    setWorkflowWarning("No stored documents found in the active case. Upload To Case before creating a session.");
  }
  return body;
}

async function createSession() {
  if (selectedDocumentCount() > 0 && !currentCaseId) {
    throw new Error("Selected files must be uploaded through Upload To Case first. Follow: Ensure User -> Create Case -> Upload To Case -> Create Session.");
  }
  if (currentCaseId) {
    requirePersistedWorkflow("Create Session");
  }
  const normalizedLanguage = normalizeLanguageCode(languageInput.value);
  languageInput.value = normalizedLanguage;
  const payload = {
    country: countryInput.value.trim() || "SK",
    language: normalizedLanguage,
    discussion_type: discussionTypeInput.value,
  };
  if (getActiveCaseId()) {
    payload.case_id = getActiveCaseId();
  }
  const response = await fetch(`${getBaseUrl()}/v1/chat/sessions`, {
    method: "POST",
    headers: requestHeaders(),
    body: JSON.stringify(payload),
  });
  const body = await parseResponse(response);
  sessionId = body.id;
  currentSessionCaseId = currentCaseId;
  waitingForManualReply = false;
  streamStartedForSession = false;
  pdfRequestedByUser = false;
  thankYouDetected = false;
  autoPdfDownloaded = false;
  documentRequestedByUser = false;
  sessionStatus.textContent = JSON.stringify(body, null, 2);
  clearWorkflowWarning();
  refreshReplyControls();
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
  if (selectedDocumentCount() > 0 && !currentCaseId) {
    throw new Error("Selected files are not persisted. Use Ensure User -> Create Case -> Upload To Case -> Create Session before Start Stream.");
  }
  if (currentCaseId) {
    requirePersistedWorkflow("Start Stream");
  }
  requireSession();
  if (!hasBoundSessionForCurrentCase()) {
    throw new Error("Current session is stale for the active case. Create Session again before Start Stream.");
  }
  const instruction = instructionInput.value.trim();
  if (!instruction) throw new Error("Case instruction is required.");

  waitingForManualReply = false;
  clearWorkflowWarning();
  refreshReplyControls();
  streamLog.textContent = "Starting stream...";
  const persistedCaseId = getActiveCaseId();
  const inlineDocuments = persistedCaseId ? [] : await readSelectedDocuments();
  const payload = {
    instruction,
    documents: inlineDocuments,
    question_timeout_seconds: Number(questionTimeoutInput.value || 300),
    max_discussion_minutes: Number(maxDiscussionInput.value || 15),
    communication_minutes: Number(communicationMinutesInput.value || 3),
    user_simulation_mode: userSimulationModeInput.value || "AIUserSimulatorAgent",
  };
  if (persistedCaseId) {
    appendStream(`case_context: using persisted case ${persistedCaseId} for document retrieval`);
  }

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
  streamStartedForSession = true;
  refreshReplyControls();

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
        if (eventItem.event === "waiting_for_reply") {
          waitingForManualReply = true;
          setWorkflowWarning("Stream paused. Use Send answer to continue the same session.");
          refreshReplyControls();
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
      if (eventItem.event === "waiting_for_reply") {
        waitingForManualReply = true;
        setWorkflowWarning("Stream paused. Use Send answer to continue the same session.");
        refreshReplyControls();
      }
      if (eventItem.event === "done") {
        await maybeAutoDownloadPdf();
      }
    }
  }

  await refreshMessages();
  refreshReplyControls();
  if (persistedCaseId) {
    await inspectCaseDocuments();
  }
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
  if (currentCaseId) {
    requirePersistedWorkflow("Send answer");
  }
  requireSession();
  if (userSimulationModeInput.value !== "ReadUser") {
    throw new Error("Switch Reply mode to ReadUser before using Send answer.");
  }
  if (!hasBoundSessionForCurrentCase()) {
    throw new Error("Current session is stale for the active case. Create Session again before sending an answer.");
  }
  const content = userReplyInput.value.trim();
  if (!content) throw new Error("End user answer is required.");
  if (!streamStartedForSession) {
    await startStream();
  }
  if (!waitingForManualReply) {
    refreshReplyControls();
    throw new Error("Wait for the assistant question before sending an answer.");
  }

  const response = await fetch(`${getBaseUrl()}/v1/chat/sessions/${sessionId}/reply`, {
    method: "POST",
    headers: requestHeaders(),
    body: JSON.stringify({ content }),
  });

  const lawyerReply = await parseResponse(response);
  appendChatMessage({ role: "user", content, agent_name: "User" });
  appendChatMessage(lawyerReply);
  waitingForManualReply = assistantRequestsReply(lawyerReply.content);
  if (waitingForManualReply) {
    setWorkflowWarning("Assistant asked another question. Use Send answer again to continue.");
  } else {
    clearWorkflowWarning();
  }
  userReplyInput.value = "";
  appendStream(`user_reply: ${content}`);
  refreshReplyControls();
  await refreshMessages();
  if (getActiveCaseId()) {
    await inspectCaseDocuments();
  }
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
  currentSessionCaseId = null;
  waitingForManualReply = false;
  streamStartedForSession = false;
  pdfRequestedByUser = false;
  thankYouDetected = false;
  autoPdfDownloaded = false;
  documentRequestedByUser = false;
  sessionStatus.textContent = "No session created yet.";
  streamLog.textContent = "No stream started yet.";
  clearAgentQuestionsLog();
  messagesEl.textContent = "[]";
  resultEl.textContent = "No result fetched yet.";
  documentDebugEl.textContent = "No document debug fetched yet.";
  renderWelcomeMessage();
  userReplyInput.value = "";
  refreshReplyControls();
}

function bind(id, fn) {
  document.getElementById(id).addEventListener("click", async () => {
    try {
      await fn();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      appendStream(`error: ${message}`);
      sessionStatus.textContent = message;
      setWorkflowWarning(message);
    }
  });
}

bind("createSession", createSession);
bind("ensureUser", ensureUser);
bind("createCase", createPersistedCase);
bind("uploadCaseDocuments", uploadCaseDocuments);
bind("inspectCaseDocuments", inspectCaseDocuments);
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
    setWorkflowWarning(message);
  }
});

userSimulationModeInput.addEventListener("change", () => {
  refreshReplyControls();
});
languageInput.addEventListener("input", () => {
  languageInput.value = normalizeLanguageCode(languageInput.value);
  if (!sessionId || isWelcomeOnlyTranscript()) {
    renderWelcomeMessage();
  }
});

async function initializeSimulator() {
  await applyDefaultInputs();
  baseUrlInput.value = normalizeApiBaseUrl(baseUrlInput.value);
  renderWelcomeMessage();
  clearWorkflowWarning();
  refreshReplyControls();
}

initializeSimulator();
