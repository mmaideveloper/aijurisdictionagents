const baseUrlInput = document.getElementById("baseUrl");
const apiKeyInput = document.getElementById("apiKey");
const preparedCaseInput = document.getElementById("preparedCase");
const preparedCasesDataEl = document.getElementById("preparedCasesData");
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
const processingStatus = document.getElementById("processingStatus");
const communicationMinutesInput = document.getElementById("communicationMinutes");
const userPhoneInput = document.getElementById("userPhone");
const userEmailInput = document.getElementById("userEmail");
const userPasswordInput = document.getElementById("userPassword");
const userFirstNameInput = document.getElementById("userFirstName");
const userLastNameInput = document.getElementById("userLastName");
const userAddressInput = document.getElementById("userAddress");
const caseTitleInput = document.getElementById("caseTitle");
const existingCaseInput = document.getElementById("existingCase");
const createCaseButton = document.getElementById("createCase");
const refreshExistingCasesButton = document.getElementById("refreshExistingCases");
const uploadCaseDocumentsButton = document.getElementById("uploadCaseDocuments");
const inspectCaseDocumentsButton = document.getElementById("inspectCaseDocuments");
const createSessionButton = document.getElementById("createSession");
const clearSessionButton = document.getElementById("clearSession");
const caseHistoryEl = document.getElementById("caseHistory");
const caseDocumentsListEl = document.getElementById("caseDocumentsList");
const documentViewerEl = document.getElementById("documentViewer");
const documentTemplatesListEl = document.getElementById("documentTemplatesList");
const refreshDocumentTemplatesButton = document.getElementById("refreshDocumentTemplates");
const defaultsUrl = "/static/default-inputs.json";
const defaultLanguageCode = "SK";
const MESSAGE_PREVIEW_LIMIT = 256;
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
let pendingInitialInstructionContent = "";
let preparedCases = [];
let persistedCases = [];
let currentCaseHistoryMessages = [];
let currentCaseDocuments = [];
let documentTemplates = [];
let activeDocumentViewUrl = null;
let processingStatusTimerId = null;
let processingStatusBaseMessage = "";
let processingStatusStartedAt = 0;
let activeCaseSelectionMode = null;

function decodeBase64ToBytes(base64Value) {
  const normalized = String(base64Value || "").trim();
  if (!normalized) return new Uint8Array();
  const binary = atob(normalized);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function applyPreparedCaseDocuments(documents) {
  if (!documentsInput) return;
  const preparedDocuments = Array.isArray(documents) ? documents : [];
  if (typeof DataTransfer === "undefined" || typeof File === "undefined") {
    return;
  }
  const transfer = new DataTransfer();
  for (const document of preparedDocuments) {
    const fileName = String(document?.fileName || document?.sourcePath || "document").trim();
    const mimeType = String(document?.mimeType || "application/octet-stream").trim();
    const contentBase64 = String(document?.contentBase64 || "").trim();
    if (!fileName || !contentBase64) continue;
    const bytes = decodeBase64ToBytes(contentBase64);
    const file = new File([bytes], fileName, { type: mimeType });
    transfer.items.add(file);
  }
  documentsInput.files = transfer.files;
}

function selectedPreparedCase() {
  const selectedId = String(preparedCaseInput?.value || "").trim();
  if (!selectedId) return null;
  return preparedCases.find((item) => item.id === selectedId) || null;
}

function buildPreparedCaseFile(document) {
  const fileName = String(document?.fileName || document?.sourcePath || "document").trim();
  const mimeType = String(document?.mimeType || "application/octet-stream").trim();
  const contentBase64 = String(document?.contentBase64 || "").trim();
  if (!fileName || !contentBase64 || typeof File === "undefined") return null;
  const bytes = decodeBase64ToBytes(contentBase64);
  return new File([bytes], fileName, { type: mimeType });
}

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

function updateExistingCaseStatus() {
  if (!existingCaseInput) return;
  existingCaseInput.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  if (!currentUserId) {
    placeholder.textContent = "Ensure User first to load existing cases...";
  } else if (!persistedCases.length) {
    placeholder.textContent = "No existing cases found for this user.";
  } else {
    placeholder.textContent = "Select existing case...";
  }
  existingCaseInput.appendChild(placeholder);

  for (const caseItem of persistedCases) {
    const option = document.createElement("option");
    option.value = String(caseItem.case_id || "").trim();
    option.textContent = formatExistingCaseLabel(caseItem);
    existingCaseInput.appendChild(option);
  }

  if (currentCaseId && persistedCases.some((item) => String(item.case_id || "").trim() === currentCaseId)) {
    existingCaseInput.value = currentCaseId;
  } else {
    existingCaseInput.value = "";
  }
}

function formatExistingCaseLabel(caseItem) {
  const title = String(caseItem?.title || caseItem?.case_id || "Untitled case").trim();
  const status = String(caseItem?.status || "").trim();
  const updatedAt = String(caseItem?.updated_at || "").trim();
  const parts = [title];
  if (status) parts.push(status);
  if (updatedAt) parts.push(updatedAt);
  return parts.join(" | ");
}

function setCaseHistoryPlaceholder(message = "No existing case selected yet.") {
  if (!caseHistoryEl) return;
  caseHistoryEl.textContent = String(message || "").trim();
}

function renderCaseHistory(messages) {
  currentCaseHistoryMessages = Array.isArray(messages) ? messages : [];
  if (!caseHistoryEl) return;
  if (!currentCaseHistoryMessages.length) {
    setCaseHistoryPlaceholder("Selected case has no stored history yet.");
    return;
  }
  const lines = currentCaseHistoryMessages.map((message) => {
    const role = String(message?.role || "unknown").trim();
    const agentName = String(message?.agent_name || "").trim();
    const speaker = role === "user" ? "User" : agentName || "Assistant";
    const createdAt = String(message?.created_at || "").trim();
    const content = String(message?.content || "").trim();
    return `[${createdAt || "unknown time"}] ${speaker}: ${content}`;
  });
  caseHistoryEl.textContent = lines.join("\n\n");
}

function revokeDocumentViewUrl() {
  if (!activeDocumentViewUrl) return;
  URL.revokeObjectURL(activeDocumentViewUrl);
  activeDocumentViewUrl = null;
}

function setDocumentViewerPlaceholder(message = "Select View on a case document to preview it here.") {
  if (!documentViewerEl) return;
  revokeDocumentViewUrl();
  documentViewerEl.innerHTML = "";
  const placeholder = document.createElement("p");
  placeholder.className = "empty-state";
  placeholder.textContent = String(message || "").trim();
  documentViewerEl.appendChild(placeholder);
}

function setDocumentTemplatesPlaceholder(message = "No document templates loaded yet.") {
  if (!documentTemplatesListEl) return;
  documentTemplatesListEl.innerHTML = "";
  const placeholder = document.createElement("p");
  placeholder.className = "empty-state";
  placeholder.textContent = String(message || "").trim();
  documentTemplatesListEl.appendChild(placeholder);
}

function renderDocumentTemplates(templates) {
  documentTemplates = Array.isArray(templates) ? templates : [];
  if (!documentTemplatesListEl) return;
  documentTemplatesListEl.innerHTML = "";
  if (!documentTemplates.length) {
    setDocumentTemplatesPlaceholder("No document templates returned by the API.");
    return;
  }

  for (const template of documentTemplates) {
    const card = document.createElement("article");
    card.className = "document-template-card";

    const title = document.createElement("h3");
    title.textContent = String(template?.title || template?.template_key || "Template").trim();

    const meta = document.createElement("p");
    meta.className = "document-template-meta";
    meta.textContent = [
      `Key: ${String(template?.template_key || "").trim() || "n/a"}`,
      `Kind: ${String(template?.template_kind || "").trim() || "n/a"}`,
      `Category: ${String(template?.category || "").trim() || "n/a"}`,
      `Jurisdiction: ${String(template?.jurisdiction || "").trim() || "n/a"}`,
      `Language: ${String(template?.language || "").trim() || "n/a"}`,
    ].join("\n");

    const actions = document.createElement("div");
    actions.className = "case-document-actions";

    const generateButton = document.createElement("button");
    generateButton.type = "button";
    generateButton.className = "secondary";
    generateButton.textContent = "Generate PDF";
    generateButton.addEventListener("click", async () => {
      try {
        await generateTemplatePdf(template);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        appendStream(`error: ${message}`);
        setWorkflowWarning(message);
        finishProcessingStatus(`Error: ${message}`);
      }
    });

    actions.append(generateButton);
    card.append(title, meta, actions);
    documentTemplatesListEl.appendChild(card);
  }
}

function renderCaseDocuments(documents) {
  currentCaseDocuments = Array.isArray(documents) ? documents : [];
  if (!caseDocumentsListEl) return;
  caseDocumentsListEl.innerHTML = "";
  if (!currentCaseDocuments.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No case documents loaded yet.";
    caseDocumentsListEl.appendChild(empty);
    setDocumentViewerPlaceholder("No case document selected yet.");
    return;
  }

  for (const documentItem of currentCaseDocuments) {
    const card = document.createElement("article");
    card.className = "case-document-card";

    const title = document.createElement("h3");
    title.textContent = String(documentItem?.original_filename || documentItem?.doc_id || "Document").trim();

    const meta = document.createElement("p");
    meta.className = "case-document-meta";
    meta.textContent = [
      `Document ID: ${String(documentItem?.doc_id || "").trim() || "n/a"}`,
      `Kind: ${String(documentItem?.kind || "").trim() || "n/a"}`,
      `Version: ${String(documentItem?.version ?? "").trim() || "n/a"}`,
      `Status: ${String(documentItem?.processing_status || "").trim() || "n/a"}`,
      `Processed at: ${String(documentItem?.processed_at || "").trim() || "pending"}`,
    ].join("\n");

    const actions = document.createElement("div");
    actions.className = "case-document-actions";

    const viewButton = document.createElement("button");
    viewButton.type = "button";
    viewButton.className = "secondary";
    viewButton.textContent = "View";
    viewButton.addEventListener("click", async () => {
      try {
        await viewCaseDocument(String(documentItem?.doc_id || "").trim());
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        appendStream(`error: ${message}`);
        setWorkflowWarning(message);
        finishProcessingStatus(`Error: ${message}`);
      }
    });

    const downloadButton = document.createElement("button");
    downloadButton.type = "button";
    downloadButton.className = "secondary";
    downloadButton.textContent = "Download";
    downloadButton.addEventListener("click", async () => {
      try {
        await downloadCaseDocument(String(documentItem?.doc_id || "").trim());
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        appendStream(`error: ${message}`);
        setWorkflowWarning(message);
        finishProcessingStatus(`Error: ${message}`);
      }
    });

    actions.append(viewButton, downloadButton);
    card.append(title, meta, actions);
    caseDocumentsListEl.appendChild(card);
  }
}

function resetLoadedCaseData() {
  currentCaseHistoryMessages = [];
  currentCaseDocuments = [];
  setCaseHistoryPlaceholder();
  if (caseDocumentsListEl) {
    caseDocumentsListEl.innerHTML = "";
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No case documents loaded yet.";
    caseDocumentsListEl.appendChild(empty);
  }
  setDocumentViewerPlaceholder();
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
  pendingInitialInstructionContent = "";
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
  if (message && message._pendingInstruction === true) {
    article.dataset.pendingInstruction = "true";
  }
  if (message && message._thinkingPlaceholder === true) {
    article.dataset.thinkingPlaceholder = "true";
  }

  const meta = document.createElement("span");
  meta.className = "chat-meta";
  meta.textContent = messageSpeaker(message);

  const body = buildExpandableMessageBody(message.content);

  article.append(meta, body);
  return article;
}

function buildExpandableMessageBody(content) {
  const text = String(content || "").trim();
  const body = document.createElement("p");
  body.className = "chat-body";
  if (text.length <= MESSAGE_PREVIEW_LIMIT) {
    body.textContent = text;
    return body;
  }

  let expanded = false;
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "chat-expand-toggle";

  const render = () => {
    body.textContent = "";
    if (expanded) {
      body.textContent = text;
      toggle.textContent = "menej";
      body.append(" ");
      body.append(toggle);
      return;
    }
    body.textContent = text.slice(0, MESSAGE_PREVIEW_LIMIT).trimEnd();
    toggle.textContent = "viac...";
    body.append(" ");
    body.append(toggle);
  };

  toggle.addEventListener("click", () => {
    expanded = !expanded;
    render();
  });

  render();
  return body;
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

function localizedThinkingMessage() {
  const country = String(countryInput?.value || "").trim().toUpperCase();
  const language = String(languageInput?.value || "").trim().toLowerCase();
  if (country === "SK" || language.startsWith("sk")) {
    return "Premyslam...";
  }
  if (country === "CZ" || language.startsWith("cs") || language.startsWith("cz")) {
    return "Premyslim...";
  }
  if (["AT", "DE", "CH"].includes(country) || language.startsWith("de") || language.startsWith("ge")) {
    return "Ich denke nach...";
  }
  return "Thinking...";
}

function appendThinkingPlaceholder() {
  const message = localizedThinkingMessage();
  const thinkingMessage = {
    role: "assistant",
    content: message,
    agent_name: "System",
    _thinkingPlaceholder: true,
  };
  appendChatMessage(thinkingMessage);
  appendMessagePreview({
    role: "assistant",
    content: message,
    agent_name: "System",
  });
  appendStream(`processing:thinking: ${message}`);
  updateProcessingStatus("Backend is processing your request...");
}

function removeThinkingPlaceholders() {
  const placeholders = chatTranscriptEl.querySelectorAll('.chat-message[data-thinking-placeholder="true"]');
  placeholders.forEach((node) => node.remove());
}

function appendMessagePreview(message) {
  let currentMessages = [];
  try {
    const parsed = JSON.parse(messagesEl.textContent);
    if (Array.isArray(parsed)) {
      currentMessages = parsed;
    }
  } catch {
    currentMessages = [];
  }

  const lastMessage = currentMessages[currentMessages.length - 1];
  if (
    lastMessage &&
    lastMessage.role === message.role &&
    String(lastMessage.content || "").trim() === String(message.content || "").trim()
  ) {
    return;
  }

  currentMessages.push({
    role: message.role,
    agent_name: message.agent_name || null,
    content: message.content,
  });
  messagesEl.textContent = JSON.stringify(currentMessages, null, 2);
}

function appendInitialInstructionMessage(instruction) {
  const normalizedInstruction = String(instruction || "").trim();
  if (!normalizedInstruction) return;
  appendChatMessage({
    role: "user",
    content: normalizedInstruction,
    agent_name: "User",
    _pendingInstruction: true,
  });
  appendMessagePreview({
    role: "user",
    content: normalizedInstruction,
    agent_name: "User",
  });
  pendingInitialInstructionContent = normalizedInstruction;
}

function resolvePendingInstructionMessage(message) {
  const normalizedContent = String(message && message.content ? message.content : "").trim();
  if (
    !pendingInitialInstructionContent ||
    !message ||
    message.role !== "user" ||
    normalizedContent !== pendingInitialInstructionContent
  ) {
    return false;
  }
  const pendingNode = chatTranscriptEl.querySelector('.chat-message.user[data-pending-instruction="true"]');
  if (pendingNode) {
    pendingNode.removeAttribute("data-pending-instruction");
  }
  pendingInitialInstructionContent = "";
  return true;
}

function renderChatMessages(messages) {
  pdfRequestedByUser = false;
  thankYouDetected = false;
  documentRequestedByUser = false;
  pendingInitialInstructionContent = "";
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

function renderPreparedCases() {
  if (!preparedCaseInput) return;
  preparedCaseInput.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = preparedCases.length
    ? "Select prepared case..."
    : "No prepared cases found in /testcases";
  preparedCaseInput.appendChild(placeholder);

  for (const testCase of preparedCases) {
    const option = document.createElement("option");
    option.value = testCase.id;
    option.textContent = testCase.title || testCase.filename || testCase.id;
    preparedCaseInput.appendChild(option);
  }
}

function applyPreparedCaseSelection(testCaseId) {
  const selectedCase = preparedCases.find((item) => item.id === testCaseId);
  if (!selectedCase) {
    applyPreparedCaseDocuments([]);
    return;
  }
  instructionInput.value = selectedCase.instruction || "";
  if (caseTitleInput && selectedCase.title) {
    caseTitleInput.value = selectedCase.title;
  }
  applyPreparedCaseDocuments(selectedCase.documents || []);
}

async function loadPreparedCases() {
  if (!preparedCaseInput) return;
  try {
    const inlineData = preparedCasesDataEl ? preparedCasesDataEl.textContent || "[]" : "[]";
    const body = JSON.parse(inlineData);
    preparedCases = Array.isArray(body) ? body : [];
  } catch {
    preparedCases = [];
  }
  renderPreparedCases();
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

function formatStreamEvent(eventItem) {
  const data = eventItem?.data;
  if (eventItem?.event === "processing" && data && typeof data === "object") {
    const prefix = data.tool_name
      ? `tool:${data.tool_name}`
      : `processing:${data.stage || "step"}`;
    return `${prefix}: ${data.message || JSON.stringify(data)}`;
  }
  return `${eventItem.event}: ${JSON.stringify(data)}`;
}

function appendProcessingMessage(data) {
  if (!data || typeof data !== "object") return;
  const text = String(data.message || "").trim();
  if (!text) return;
  removeThinkingPlaceholders();
  const stage = String(data.stage || "").trim().toLowerCase();
  const toolName = String(data.tool_name || "").trim();
  if (["document_ready", "document_package_ready", "document_status"].includes(stage)) {
    const processingMessage = {
      role: "assistant",
      content: text,
      agent_name: toolName ? `System/${toolName}` : "System",
    };
    appendChatMessage(processingMessage);
    appendMessagePreview(processingMessage);
  }
  updateProcessingStatus(`Backend is processing: ${text}`);
}

async function handleStreamLifecycleEvent(eventItem, waitingMessage) {
  if (eventItem.event === "waiting_for_reply") {
    waitingForManualReply = true;
    setWorkflowWarning(waitingMessage);
    refreshReplyControls();
    finishProcessingStatus("Assistant is waiting for your answer.");
    return;
  }
  if (eventItem.event === "done") {
    finishProcessingStatus(
      waitingForManualReply
        ? "Assistant is waiting for your answer."
        : "Stream completed. You can ask a follow-up question or document status.",
    );
    await maybeAutoDownloadPdf();
    return;
  }
  if (eventItem.event === "error") {
    const message = String(eventItem?.data?.message || "Stream error").trim();
    setWorkflowWarning(message);
    finishProcessingStatus(`Stream error: ${message}`);
  }
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

async function refreshExistingCases({ selectedCaseId = "", preserveSelection = true } = {}) {
  if (!currentUserId) {
    persistedCases = [];
    updateExistingCaseStatus();
    refreshPersistedCaseControls();
    return [];
  }
  const response = await fetch(
    `${getBaseUrl()}/v1/cases?user_id=${encodeURIComponent(currentUserId)}`,
    { headers: requestHeaders(false) },
  );
  const body = await parseResponse(response);
  persistedCases = Array.isArray(body) ? body : [];
  updateExistingCaseStatus();
  refreshPersistedCaseControls();

  const targetCaseId = String(selectedCaseId || (preserveSelection ? currentCaseId || "" : "")).trim();
  if (targetCaseId && persistedCases.some((item) => String(item?.case_id || "").trim() === targetCaseId)) {
    existingCaseInput.value = targetCaseId;
  } else if (currentCaseId && !persistedCases.some((item) => String(item?.case_id || "").trim() === currentCaseId)) {
    currentCaseId = null;
    hasUploadedCaseDocuments = false;
    resetLoadedCaseData();
    invalidateSession("Previously selected case is no longer available. Pick another existing case or create a new one.");
    updateExistingCaseStatus();
  }
  return persistedCases;
}

async function selectExistingCase(caseId) {
  const normalizedCaseId = String(caseId || "").trim();
  if (!normalizedCaseId) {
    currentCaseId = null;
    activeCaseSelectionMode = null;
    hasUploadedCaseDocuments = false;
    resetLoadedCaseData();
    updateExistingCaseStatus();
    refreshPersistedCaseControls();
    invalidateSession("Existing case selection cleared.");
    updateCaseStatus({ mode: "cleared_selected_case", user_id: currentUserId });
    return null;
  }
  if (!currentUserId) {
    throw new Error("Ensure User first before selecting an existing case.");
  }
  const selectedCase = persistedCases.find((item) => String(item?.case_id || "").trim() === normalizedCaseId);
  if (!selectedCase) {
    throw new Error("Selected existing case is no longer available. Refresh Existing Cases first.");
  }

  currentCaseId = normalizedCaseId;
  activeCaseSelectionMode = "existing";
  if (caseTitleInput) {
    caseTitleInput.value = String(selectedCase?.title || caseTitleInput.value || "").trim() || "Simulator persisted case";
  }
  updateExistingCaseStatus();
  invalidateSession("Existing case loaded. Click Create Session to continue this conversation on the selected case.");

  const params = new URLSearchParams({
    user_id: currentUserId,
    limit: "20",
  });
  const response = await fetch(
    `${getBaseUrl()}/v1/cases/${encodeURIComponent(normalizedCaseId)}/history?${params.toString()}`,
    { headers: requestHeaders(false) },
  );
  const body = await parseResponse(response);
  const messages = Array.isArray(body?.messages) ? body.messages : [];
  const documents = Array.isArray(body?.documents) ? body.documents : [];
  hasUploadedCaseDocuments = documents.length > 0;
  renderCaseHistory(messages);
  renderCaseDocuments(documents);
  updateCaseStatus({
    mode: "selected_existing_case",
    user_id: currentUserId,
    case: selectedCase,
    history_message_count: messages.length,
    document_count: documents.length,
  });
  refreshPersistedCaseControls();
  appendStream(`existing_case_loaded: ${normalizedCaseId} messages=${messages.length} documents=${documents.length}`);
  if (!documents.length) {
    setWorkflowWarning("Existing case loaded, but it has no stored documents yet.");
  } else {
    clearWorkflowWarning();
  }
  return body;
}

async function fetchCaseDocument(docId) {
  const normalizedDocId = String(docId || "").trim();
  if (!currentUserId || !currentCaseId) {
    throw new Error("Select an existing case first.");
  }
  if (!normalizedDocId) {
    throw new Error("Case document ID is required.");
  }
  const response = await fetch(
    `${getBaseUrl()}/v1/cases/${encodeURIComponent(currentCaseId)}/documents/${encodeURIComponent(normalizedDocId)}?user_id=${encodeURIComponent(currentUserId)}`,
    { headers: requestHeaders(false) },
  );
  if (!response.ok) {
    const body = await safeParseJson(response);
    throw new Error(JSON.stringify(body));
  }
  const blob = await response.blob();
  const contentType = String(response.headers.get("Content-Type") || "").trim().toLowerCase();
  const filename = extractFilenameFromContentDisposition(response.headers.get("Content-Disposition"))
    || normalizedDocId;
  return { blob, contentType, filename };
}

function triggerBlobDownload({ blob, filename }) {
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(href), 1000);
}

async function viewCaseDocument(docId) {
  const { blob, contentType, filename } = await fetchCaseDocument(docId);
  revokeDocumentViewUrl();
  documentViewerEl.innerHTML = "";

  const title = document.createElement("p");
  title.className = "case-document-meta";
  title.textContent = `Viewing: ${filename} (${contentType || "application/octet-stream"})`;
  documentViewerEl.appendChild(title);

  if (contentType.includes("pdf")) {
    activeDocumentViewUrl = URL.createObjectURL(blob);
    const frame = document.createElement("iframe");
    frame.className = "document-viewer-frame";
    frame.src = activeDocumentViewUrl;
    frame.title = filename;
    documentViewerEl.appendChild(frame);
    return;
  }

  if (contentType.startsWith("text/") || contentType.includes("json") || contentType.includes("xml")) {
    const text = await blob.text();
    const pre = document.createElement("pre");
    pre.className = "document-viewer-pre";
    pre.textContent = text;
    documentViewerEl.appendChild(pre);
    return;
  }

  activeDocumentViewUrl = URL.createObjectURL(blob);
  const note = document.createElement("p");
  note.className = "empty-state";
  note.textContent = "Inline preview is not available for this document type. Use the link below to open it.";
  const link = document.createElement("a");
  link.className = "document-viewer-link";
  link.href = activeDocumentViewUrl;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = `Open ${filename}`;
  documentViewerEl.append(note, link);
}

async function downloadCaseDocument(docId) {
  const { blob, filename } = await fetchCaseDocument(docId);
  triggerBlobDownload({ blob, filename });
  appendStream(`case_document_downloaded: ${filename}`);
  finishProcessingStatus(`Document downloaded: ${filename}`);
}

async function refreshDocumentTemplates() {
  const country = String(countryInput?.value || "SK").trim() || "SK";
  const params = new URLSearchParams({
    include_deleted: "false",
    jurisdiction: country,
  });
  const response = await fetch(`${getBaseUrl()}/v1/document-templates?${params.toString()}`, {
    headers: requestHeaders(false),
  });
  const body = await parseResponse(response);
  renderDocumentTemplates(Array.isArray(body?.items) ? body.items : []);
  appendStream(`document_templates_loaded: ${documentTemplates.length}`);
}

async function generateTemplatePdf(template) {
  const templateKey = String(template?.template_key || "").trim();
  if (!templateKey) {
    throw new Error("Document template key is required.");
  }
  const jurisdiction = String(template?.jurisdiction || countryInput?.value || "SK").trim() || "SK";
  const params = new URLSearchParams({ jurisdiction });
  const url = `${getBaseUrl()}/v1/document-templates/${encodeURIComponent(templateKey)}/preview/pdf?${params.toString()}`;
  const response = await fetch(url, {
    headers: requestHeaders(false),
  });
  if (!response.ok) {
    const body = await safeParseJson(response);
    throw new Error(JSON.stringify(body));
  }
  const blob = await response.blob();
  const filename = extractFilenameFromContentDisposition(response.headers.get("Content-Disposition"))
    || `${templateKey.replace(/[^A-Za-z0-9._-]+/g, "_")}-preview.pdf`;
  triggerBlobDownload({ blob, filename });
  appendStream(`template_pdf_generated: ${filename}`);
  finishProcessingStatus(`Template PDF generated: ${filename}`);
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

function setProcessingStatus(message) {
  if (!processingStatus) return;
  processingStatus.textContent = String(message || "").trim() || "Idle.";
}

function renderProcessingStatusTimer() {
  if (!processingStatusStartedAt) return;
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - processingStatusStartedAt) / 1000));
  setProcessingStatus(`${processingStatusBaseMessage} (${elapsedSeconds}s)`);
}

function startProcessingStatus(message) {
  if (processingStatusTimerId) {
    window.clearInterval(processingStatusTimerId);
  }
  processingStatusBaseMessage = String(message || "").trim() || "Backend is processing...";
  processingStatusStartedAt = Date.now();
  renderProcessingStatusTimer();
  processingStatusTimerId = window.setInterval(renderProcessingStatusTimer, 1000);
}

function updateProcessingStatus(message) {
  const normalized = String(message || "").trim();
  if (!normalized) return;
  if (!processingStatusTimerId) {
    setProcessingStatus(normalized);
    return;
  }
  processingStatusBaseMessage = normalized;
  renderProcessingStatusTimer();
}

function finishProcessingStatus(message = "Idle.") {
  if (processingStatusTimerId) {
    window.clearInterval(processingStatusTimerId);
    processingStatusTimerId = null;
  }
  processingStatusBaseMessage = "";
  processingStatusStartedAt = 0;
  setProcessingStatus(message);
}

function refreshPersistedCaseControls() {
  if (createCaseButton) {
    createCaseButton.disabled = !currentUserId;
  }
  if (refreshExistingCasesButton) {
    refreshExistingCasesButton.disabled = !currentUserId;
  }
  if (existingCaseInput) {
    existingCaseInput.disabled = !currentUserId || !persistedCases.length;
  }
  if (uploadCaseDocumentsButton) {
    uploadCaseDocumentsButton.disabled = !currentCaseId;
  }
  if (inspectCaseDocumentsButton) {
    inspectCaseDocumentsButton.disabled = !currentCaseId;
  }
  if (createSessionButton) {
    createSessionButton.disabled = !currentCaseId;
  }
  if (clearSessionButton) {
    clearSessionButton.disabled = !sessionId;
  }
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
    refreshPersistedCaseControls();
    return;
  }
  clearSession();
  if (reason) setWorkflowWarning(reason);
  refreshReplyControls();
  refreshPersistedCaseControls();
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
  const canSendManualReply = readUserMode && hasSession;

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
    setReplyStatus("Type an answer and click Send answer to continue the session or ask for document status.");
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
    first_name: userFirstNameInput.value.trim(),
    last_name: userLastNameInput.value.trim(),
    address: userAddressInput.value.trim(),
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
      resetLoadedCaseData();
      invalidateSession("User changed. Start again with Create Case, Upload To Case, then Create Session.");
    } else {
      clearWorkflowWarning();
    }
    await refreshExistingCases({ preserveSelection: true });
    updateCaseStatus({ mode: "created_user", user: created, case_id: currentCaseId });
    refreshPersistedCaseControls();
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
      resetLoadedCaseData();
      invalidateSession("User changed. Start again with Create Case, Upload To Case, then Create Session.");
    } else {
      clearWorkflowWarning();
    }
    await refreshExistingCases({ preserveSelection: true });
    updateCaseStatus({ mode: "loaded_user_by_phone", user: existing, case_id: currentCaseId });
    refreshPersistedCaseControls();
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
    resetLoadedCaseData();
    invalidateSession("User changed. Start again with Create Case, Upload To Case, then Create Session.");
  } else {
    clearWorkflowWarning();
  }
  await refreshExistingCases({ preserveSelection: true });
  updateCaseStatus({ mode: "loaded_user_by_email", user, case_id: currentCaseId });
  refreshPersistedCaseControls();
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
  if (response.status === 409) {
    const body = await safeParseJson(response);
    const detail = String(body.detail || "Maximum number of cases reached.");
    throw new Error(`${detail} Use Delete All Cases or remove one existing case first.`);
  }
  const body = await parseResponse(response);
  currentCaseId = body.case_id;
  activeCaseSelectionMode = "new";
  hasUploadedCaseDocuments = false;
  resetLoadedCaseData();
  invalidateSession("Case created. You can Create Session immediately, or use Upload To Case first for persisted document retrieval.");
  await refreshExistingCases({ selectedCaseId: currentCaseId, preserveSelection: false });
  updateCaseStatus({ mode: "created_case", user_id: currentUserId, case: body });
  refreshPersistedCaseControls();
  return body;
}

async function deleteAllCases() {
  const response = await fetch("/internal/delete-user-cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      api_base_url: getBaseUrl(),
      api_key: apiKeyInput.value.trim(),
      user_id: getActiveUserId(),
      phone_number: userPhoneInput.value.trim(),
      email: userEmailInput.value.trim(),
      password: userPasswordInput.value.trim(),
      first_name: userFirstNameInput.value.trim(),
      last_name: userLastNameInput.value.trim(),
      address: userAddressInput.value.trim(),
    }),
  });
  const body = await parseResponse(response);
  const userId = String(body.user_id || getActiveUserId() || "").trim();
  const deletedCaseIds = Array.isArray(body.deleted_case_ids) ? body.deleted_case_ids : [];
  const failedDeletes = Array.isArray(body.failed_deletes) ? body.failed_deletes : [];
  currentUserId = userId || currentUserId;

  currentCaseId = null;
  hasUploadedCaseDocuments = false;
  resetLoadedCaseData();
  invalidateSession("All user cases were cleared. Create Case before using persisted case flow again.");
  await refreshExistingCases({ preserveSelection: false });
  updateCaseStatus({
    mode: "deleted_all_cases",
    user_id: userId,
    deleted_count: deletedCaseIds.length,
    deleted_case_ids: deletedCaseIds,
    failed_deletes: failedDeletes,
  });
  refreshPersistedCaseControls();

  if (failedDeletes.length) {
    throw new Error(`Deleted ${deletedCaseIds.length} case(s), but ${failedDeletes.length} delete request(s) failed.`);
  }

  if (!deletedCaseIds.length) {
    setWorkflowWarning("No user cases were found to delete.");
    return [];
  }

  clearWorkflowWarning();
  appendStream(`deleted_all_cases: ${deletedCaseIds.length} case(s) removed for user ${userId}`);
  return deletedCaseIds;
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
  await refreshExistingCases({ selectedCaseId: currentCaseId, preserveSelection: true });
  updateCaseStatus({
    mode: "uploaded_case_documents",
    user_id: currentUserId,
    case_id: currentCaseId,
    upload: body,
  });
  refreshPersistedCaseControls();
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
  if (!currentUserId) {
    throw new Error("Ensure User first before Create Session.");
  }
  if (!currentCaseId) {
    throw new Error("Create Case first before Create Session.");
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
  refreshPersistedCaseControls();
  await preloadPreparedCaseDocumentsToActiveCase();
  await refreshMessages();
}

async function preloadPreparedCaseDocumentsToActiveCase() {
  if (!currentCaseId || !currentUserId) return;
  if (activeCaseSelectionMode === "existing") return;
  if (hasUploadedCaseDocuments) return;
  const preparedCase = selectedPreparedCase();
  const preparedDocuments = Array.isArray(preparedCase?.documents) ? preparedCase.documents : [];
  if (!preparedDocuments.length) return;

  const files = preparedDocuments
    .map((document) => buildPreparedCaseFile(document))
    .filter((file) => file !== null);
  if (!files.length) return;

  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  const response = await fetch(
    `${getBaseUrl()}/v1/cases/${encodeURIComponent(currentCaseId)}/documents?user_id=${encodeURIComponent(currentUserId)}`,
    {
      method: "POST",
      headers: requestHeaders(false),
      body: formData,
    },
  );
  await parseResponse(response);
  hasUploadedCaseDocuments = true;
  appendStream(`prepared_case_documents_preloaded: case=${currentCaseId} count=${files.length}`);
  setWorkflowWarning("Prepared testcase documents were preloaded to this case.");
  await inspectCaseDocuments();
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

async function startStream({ instructionOverride = "" } = {}) {
  requireSession();
  if (!hasBoundSessionForCurrentCase()) {
    throw new Error("Current session is stale for the active case. Create Session again before Start Stream.");
  }
  const instruction = String(instructionOverride || instructionInput.value).trim();
  if (!instruction) throw new Error("Case instruction is required.");

  waitingForManualReply = false;
  clearWorkflowWarning();
  refreshReplyControls();
  streamLog.textContent = "Starting stream...";
  appendInitialInstructionMessage(instruction);
  appendThinkingPlaceholder();
  startProcessingStatus("Backend is processing your request...");
  try {
    const persistedCaseId = getActiveCaseId();
    const inlineDocuments = persistedCaseId ? [] : await readSelectedDocuments();
    const payload = {
      instruction,
      documents: inlineDocuments,
      question_timeout_seconds: Number(questionTimeoutInput.value || 300),
      max_discussion_minutes: Number(maxDiscussionInput.value || 60),
      communication_minutes: Number(communicationMinutesInput.value || 30),
      user_simulation_mode: userSimulationModeInput.value || "ReadUser",
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
          appendStream(formatStreamEvent(eventItem));
          if (eventItem.event === "processing" && eventItem.data && typeof eventItem.data === "object") {
            appendProcessingMessage(eventItem.data);
          }
          if (eventItem.event === "message" && eventItem.data && typeof eventItem.data === "object") {
            removeThinkingPlaceholders();
            if (!resolvePendingInstructionMessage(eventItem.data)) {
              appendChatMessage(eventItem.data);
            }
            if (String(eventItem.data.role || "").trim().toLowerCase() === "assistant") {
              finishProcessingStatus("Assistant replied.");
            }
          }
          await handleStreamLifecycleEvent(eventItem, "Stream paused. Use Send answer to continue the same session.");
        }
      }
    }

    if (buffer.trim()) {
      const trailingEvents = parseSseChunk(buffer);
      for (const eventItem of trailingEvents) {
        appendStream(formatStreamEvent(eventItem));
        if (eventItem.event === "processing" && eventItem.data && typeof eventItem.data === "object") {
          appendProcessingMessage(eventItem.data);
        }
        if (eventItem.event === "message" && eventItem.data && typeof eventItem.data === "object") {
          removeThinkingPlaceholders();
          if (!resolvePendingInstructionMessage(eventItem.data)) {
            appendChatMessage(eventItem.data);
          }
          if (String(eventItem.data.role || "").trim().toLowerCase() === "assistant") {
            finishProcessingStatus("Assistant replied.");
          }
        }
        await handleStreamLifecycleEvent(eventItem, "Stream paused. Use Send answer to continue the same session.");
      }
    }

    await refreshMessages();
    refreshReplyControls();
    if (persistedCaseId) {
      await inspectCaseDocuments();
    }
    await maybeAutoDownloadPdf();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    finishProcessingStatus(`Stream failed: ${message}`);
    throw error;
  } finally {
    removeThinkingPlaceholders();
  }
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
  if (userSimulationModeInput.value !== "ReadUser") {
    throw new Error("Switch Reply mode to ReadUser before using Send answer.");
  }
  if (!hasBoundSessionForCurrentCase()) {
    throw new Error("Current session is stale for the active case. Create Session again before sending an answer.");
  }
  const content = userReplyInput.value.trim();
  if (!content) throw new Error("End user answer is required.");
  if (!streamStartedForSession) {
    userReplyInput.value = "";
    await startStream({ instructionOverride: content });
    return;
  }

  userReplyInput.value = "";
  appendChatMessage({ role: "user", content, agent_name: "User" });
  appendStream(`user_reply: ${content}`);
  waitingForManualReply = false;
  refreshReplyControls();
  appendThinkingPlaceholder();
  startProcessingStatus("Backend is processing your reply...");
  try {
    appendStream("manual_reply_stream: sending ReadUser turn through /stream");
    const payload = {
      instruction: content,
      documents: [],
      question_timeout_seconds: Number(questionTimeoutInput.value || 300),
      max_discussion_minutes: Number(maxDiscussionInput.value || 60),
      communication_minutes: Number(communicationMinutesInput.value || 30),
      user_simulation_mode: "ReadUser",
    };
    const response = await fetch(`${getBaseUrl()}/v1/chat/sessions/${sessionId}/stream`, {
      method: "POST",
      headers: requestHeaders(),
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const body = await response.text();
      throw new Error(body || `Failed to stream reply, status=${response.status}`);
    }
    if (!response.body) {
      throw new Error("Streaming body is not available in this browser.");
    }

    const decoder = new TextDecoder();
    let buffer = "";
    const reader = response.body.getReader();
    let skippedEchoedUser = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const split = buffer.split("\n\n");
      buffer = split.pop() || "";

      for (const block of split) {
        const events = parseSseChunk(`${block}\n\n`);
        for (const eventItem of events) {
          appendStream(formatStreamEvent(eventItem));
          if (eventItem.event === "processing" && eventItem.data && typeof eventItem.data === "object") {
            appendProcessingMessage(eventItem.data);
          }
          if (eventItem.event === "message" && eventItem.data && typeof eventItem.data === "object") {
            const role = String(eventItem.data.role || "").trim().toLowerCase();
            const echoed = String(eventItem.data.content || "").trim();
            if (!skippedEchoedUser && role === "user" && echoed === content) {
              skippedEchoedUser = true;
            } else {
              removeThinkingPlaceholders();
              appendChatMessage(eventItem.data);
              if (role === "assistant") {
                finishProcessingStatus("Assistant replied.");
              }
            }
          }
          await handleStreamLifecycleEvent(eventItem, "Assistant asked another question. Use Send answer again to continue.");
        }
      }
    }

    if (buffer.trim()) {
      const trailingEvents = parseSseChunk(buffer);
      for (const eventItem of trailingEvents) {
        appendStream(formatStreamEvent(eventItem));
        if (eventItem.event === "processing" && eventItem.data && typeof eventItem.data === "object") {
          appendProcessingMessage(eventItem.data);
        }
        if (eventItem.event === "message" && eventItem.data && typeof eventItem.data === "object") {
          const role = String(eventItem.data.role || "").trim().toLowerCase();
          const echoed = String(eventItem.data.content || "").trim();
          if (!skippedEchoedUser && role === "user" && echoed === content) {
            skippedEchoedUser = true;
          } else {
            removeThinkingPlaceholders();
            appendChatMessage(eventItem.data);
            if (role === "assistant") {
              finishProcessingStatus("Assistant replied.");
            }
          }
        }
        await handleStreamLifecycleEvent(eventItem, "Assistant asked another question. Use Send answer again to continue.");
      }
    }
    await refreshMessages();
    if (getActiveCaseId()) {
      await inspectCaseDocuments();
    }
    await maybeAutoDownloadPdf();
    if (!waitingForManualReply) {
      clearWorkflowWarning();
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    finishProcessingStatus(`Stream reply failed: ${message}`);
    throw error;
  } finally {
    removeThinkingPlaceholders();
    refreshReplyControls();
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
  const contentType = String(response.headers.get("Content-Type") || "").trim().toLowerCase();
  const headerName = extractFilenameFromContentDisposition(response.headers.get("Content-Disposition"));
  if (headerName) {
    anchor.download = headerName;
  } else {
    anchor.download = createFallbackFilename(kind, format, contentType);
  }
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
  const confirmation = exportConfirmationMessage({
    kind,
    contentType,
    filename: anchor.download,
  });
  appendStream(`download_ready: ${anchor.download}`);
  appendChatMessage({
    role: "assistant",
    content: confirmation,
    agent_name: "System/Export",
  });
  finishProcessingStatus(confirmation);
}

function extractFilenameFromContentDisposition(value) {
  const header = String(value || "");
  if (!header) return "";
  const match = header.match(/filename="([^"]+)"/i);
  if (match && match[1]) return match[1];
  return "";
}

function createFallbackFilename(kind, format, contentType = "") {
  const now = new Date();
  const yyyy = String(now.getFullYear());
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  const hh = String(now.getHours()).padStart(2, "0");
  const mi = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  const ts = `${yyyy}${mm}${dd}${hh}${mi}${ss}`;
  const docName = kind === "document" ? "final-document" : "discussion-summary";
  const extension = String(contentType || "").includes("zip") ? "zip" : format;
  return `${sessionId}-${ts}-${docName}.${extension}`;
}

function exportConfirmationMessage({ kind, contentType, filename }) {
  const normalizedLanguage = normalizeLanguageCode(languageInput?.value || defaultLanguageCode);
  const exportedName = String(filename || "").trim() || createFallbackFilename(kind, "pdf", contentType);
  const isZip = String(contentType || "").includes("zip") || exportedName.toLowerCase().endsWith(".zip");

  if (normalizedLanguage === "SK") {
    if (isZip) return `Balík dokumentov bol vygenerovaný a stiahnutý: ${exportedName}.`;
    if (kind === "summary") return `PDF zhrnutie bolo vygenerované a stiahnuté: ${exportedName}.`;
    return `PDF dokument bol vygenerovaný a stiahnutý: ${exportedName}.`;
  }
  if (normalizedLanguage === "GE") {
    if (isZip) return `Das Dokumentenpaket wurde erstellt und heruntergeladen: ${exportedName}.`;
    if (kind === "summary") return `Die PDF-Zusammenfassung wurde erstellt und heruntergeladen: ${exportedName}.`;
    return `Das PDF-Dokument wurde erstellt und heruntergeladen: ${exportedName}.`;
  }
  if (isZip) return `The document package was created and downloaded: ${exportedName}.`;
  if (kind === "summary") return `The PDF summary was created and downloaded: ${exportedName}.`;
  return `The PDF document was created and downloaded: ${exportedName}.`;
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
  pendingInitialInstructionContent = "";
  sessionStatus.textContent = "No session created yet.";
  streamLog.textContent = "No stream started yet.";
  clearAgentQuestionsLog();
  messagesEl.textContent = "[]";
  resultEl.textContent = "No result fetched yet.";
  documentDebugEl.textContent = "No document debug fetched yet.";
  renderWelcomeMessage();
  userReplyInput.value = "";
  finishProcessingStatus("Idle.");
  refreshReplyControls();
  refreshPersistedCaseControls();
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
      finishProcessingStatus(`Error: ${message}`);
    }
  });
}

bind("createSession", createSession);
bind("ensureUser", ensureUser);
bind("createCase", createPersistedCase);
bind("uploadCaseDocuments", uploadCaseDocuments);
bind("inspectCaseDocuments", inspectCaseDocuments);
bind("refreshExistingCases", async () => {
  await refreshExistingCases({ preserveSelection: true });
});
bind("refreshDocumentTemplates", refreshDocumentTemplates);
bind("deleteAllCases", deleteAllCases);
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
      finishProcessingStatus(`Error: ${message}`);
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
  await loadPreparedCases();
  baseUrlInput.value = normalizeApiBaseUrl(baseUrlInput.value);
  userSimulationModeInput.value = "ReadUser";
  updateExistingCaseStatus();
  resetLoadedCaseData();
  setDocumentTemplatesPlaceholder();
  renderWelcomeMessage();
  clearWorkflowWarning();
  finishProcessingStatus("Idle.");
  refreshReplyControls();
  refreshPersistedCaseControls();
  try {
    await refreshDocumentTemplates();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    setDocumentTemplatesPlaceholder("Document templates could not be loaded.");
    appendStream(`document_templates_error: ${message}`);
  }
}

if (preparedCaseInput) {
  preparedCaseInput.addEventListener("change", () => {
    applyPreparedCaseSelection(preparedCaseInput.value);
  });
}

if (existingCaseInput) {
  existingCaseInput.addEventListener("change", async () => {
    try {
      await selectExistingCase(existingCaseInput.value);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      appendStream(`error: ${message}`);
      sessionStatus.textContent = message;
      setWorkflowWarning(message);
      finishProcessingStatus(`Error: ${message}`);
    }
  });
}

initializeSimulator();


const toolModeInput = document.getElementById("toolMode");
const toolTypeInput = document.getElementById("toolType");
const toolCommandInput = document.getElementById("toolCommand");
const runToolValidationButton = document.getElementById("runToolValidation");
const toolValidationLog = document.getElementById("toolValidationLog");

function validateToolCommand() {
  const command = String(toolCommandInput?.value || "").trim().toLowerCase();
  const mode = String(toolModeInput?.value || "audio");
  const tool = String(toolTypeInput?.value || "company");
  if (!command) {
    toolValidationLog.textContent = 'Ask command?';
    return;
  }
  if (mode === 'audio') {
    if (command.includes('validate company') || command.includes('company')) {
      toolValidationLog.textContent = 'Audio -> text recognized. Action tool: ValidationCompany (ORSK). Ask for company name or ICO.';
      return;
    }
  }
  if (tool === 'car' && !(command.includes('vin') || command.includes('spz'))) {
    toolValidationLog.textContent = 'Action tool ValidationCar selected. Ask for SPZ or VIN.';
    return;
  }
  toolValidationLog.textContent = `Action tool ${tool} recognized and command processed.`;
}

if (runToolValidationButton) runToolValidationButton.addEventListener('click', validateToolCommand);
