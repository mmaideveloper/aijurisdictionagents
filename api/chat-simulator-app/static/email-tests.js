const recipientInput = document.getElementById("emailRecipient");
const phoneInput = document.getElementById("emailPhone");
const passwordInput = document.getElementById("emailPassword");
const deviceIdInput = document.getElementById("emailDeviceId");
const firstNameInput = document.getElementById("emailFirstName");
const lastNameInput = document.getElementById("emailLastName");
const planInput = document.getElementById("emailPlan");
const paymentProviderInput = document.getElementById("emailPaymentProvider");
const transportInput = document.getElementById("emailTransport");
const senderInput = document.getElementById("emailSender");
const smtpHostInput = document.getElementById("emailSmtpHost");
const smtpPortInput = document.getElementById("emailSmtpPort");
const smtpUseTlsInput = document.getElementById("emailSmtpUseTls");
const smtpUsernameInput = document.getElementById("emailSmtpUsername");
const smtpPasswordInput = document.getElementById("emailSmtpPassword");
const transportLinksEl = document.getElementById("emailTransportLinks");
const logEl = document.getElementById("emailTestLog");

function appendLog(message, data = null) {
  const line = data ? `${message}: ${JSON.stringify(data, null, 2)}` : message;
  if (logEl.textContent === "No email test sent yet.") {
    logEl.textContent = line;
  } else {
    logEl.textContent += `\n${line}`;
  }
  logEl.scrollTop = logEl.scrollHeight;
}

async function parseResponse(response) {
  const text = await response.text();
  const body = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${JSON.stringify(body)}`);
  }
  return body;
}

function emailPayload(template) {
  const email = recipientInput.value.trim().toLowerCase();
  const phone = phoneInput.value.trim();
  const password = passwordInput.value.trim();
  if (!email || !phone || !password) {
    throw new Error("Recipient email, mobile phone, and password are required.");
  }
  return {
    transport: transportInput.value,
    template,
    recipient: email,
    sender: senderInput.value.trim(),
    smtp_host: smtpHostInput.value.trim(),
    smtp_port: Number(smtpPortInput.value || 587),
    smtp_use_tls: smtpUseTlsInput.value === "true",
    smtp_username: smtpUsernameInput.value.trim(),
    smtp_password: smtpPasswordInput.value,
    phone_number: phone,
    password,
    device_id: deviceIdInput.value.trim(),
    first_name: firstNameInput.value.trim() || "Email",
    last_name: lastNameInput.value.trim() || "Tester",
    plan_code: planInput.value,
    payment_provider: paymentProviderInput.value,
  };
}

function renderTransportLinks(links = {}) {
  if (!transportLinksEl) return;
  const entries = [
    ["Open email logs", links.logs || "/internal/email-tests/logs"],
    ["Open generated emails", links.emails || "/internal/email-tests/emails"],
  ];
  if (links.email) {
    entries.push(["Open latest email", links.email]);
  }
  transportLinksEl.innerHTML = "";
  for (const [label, href] of entries) {
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.target = "_blank";
    anchor.rel = "noreferrer";
    anchor.textContent = label;
    transportLinksEl.appendChild(anchor);
  }
}

async function sendEmailTemplate(template) {
  const response = await fetch("/internal/email-tests/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(emailPayload(template)),
  });
  const body = await parseResponse(response);
  renderTransportLinks(body.links || {});
  appendLog(`${template}_email_${body.status}`, body);
}

function bind(id, template) {
  document.getElementById(id).addEventListener("click", async () => {
    try {
      await sendEmailTemplate(template);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      appendLog(`error: ${message}`);
    }
  });
}

bind("sendRegistrationEmail", "registration");
bind("sendOtpEmail", "otp");
bind("sendPaymentEmail", "payment");
renderTransportLinks();
