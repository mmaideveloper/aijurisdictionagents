/* Shared assessment API, memory-only authentication and text-only rendering. */
const el = id => document.getElementById(id);
const flags = { personal_data: "Processes personal data?", health_data: "Processes health/genetic/biometric data?", uses_ai: "Uses AI?", medical_purpose: "Has an intended medical purpose?", specimen_analysis: "Analyses human specimen/lab information?", automated_decisions: "Decides without meaningful human review?" };
const strings = ["intended_purpose", "users", "lifecycle", "role", "suppliers"];
let identity = null;
let assessment = null;
let mfaToken = null;
const device = crypto.randomUUID();
for (const name of strings) {
  const label = document.createElement("label"); label.textContent = name.replaceAll("_", " ");
  const input = document.createElement("input"); input.id = name; input.maxLength = name === "lifecycle" ? 500 : name === "users" || name === "role" ? 1000 : 2000;
  label.append(input); el("facts").append(label);
}
for (const [name, title] of Object.entries(flags)) {
  const label = document.createElement("label"); label.textContent = title;
  const select = document.createElement("select"); select.id = name;
  for (const [value, text] of [["", "Unknown — ask me"], ["yes", "Yes"], ["no", "No"]]) select.add(new Option(text, value));
  label.append(select); el("facts").append(label);
}
async function request(path, method = "GET", body) {
  const headers = { "x-api-key": el("key").value };
  if (identity) Object.assign(headers, { "x-jurisdigta-device-id": device, "x-jurisdigta-device-token": identity.device_auth_token });
  if (!(body instanceof FormData)) headers["Content-Type"] = "application/json";
  const response = await fetch(el("base").value.replace(/\/$/, "") + path, { method, headers, body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body) });
  if (!response.ok) { const error = await response.json(); throw new Error(typeof error.detail === "string" ? error.detail : `Request failed (${response.status}).`); }
  return response;
}
async function perform(work) {
  el("status").textContent = "Processing…";
  for (const button of document.querySelectorAll("button")) button.disabled = true;
  try { await work(); el("status").textContent = "Ready. Review the result and any unresolved evidence gaps."; }
  catch (error) { el("status").textContent = error.message || "Request failed."; }
  finally { for (const button of document.querySelectorAll("button")) button.disabled = false; el("download").disabled = !assessment; }
}
el("sign-in").onclick = () => perform(async () => {
  const path = mfaToken ? "/v1/users/sign-in/mfa/verify" : "/v1/users/sign-in";
  const payload = mfaToken ? { mfa_token: mfaToken, device_id: device, method: "email", verification_code: el("otp").value } : { email: el("email").value, password: el("password").value, device_id: device, verification_code: el("otp").value || null };
  const result = await (await request(path, "POST", payload)).json();
  if (result.mfa_token) { mfaToken = result.mfa_token; await request("/v1/users/sign-in/mfa/send-email-code", "POST", { mfa_token: mfaToken }); throw new Error("Enter the emailed MFA code and sign in again."); }
  if (!result.device_auth_token) throw new Error("Authenticated device session required.");
  identity = result; mfaToken = null; el("password").value = ""; el("otp").value = "";
  const cases = await (await request(`/v1/cases?user_id=${encodeURIComponent(identity.user_id)}`)).json();
  el("case").replaceChildren(new Option("Select a case", ""));
  for (const item of cases) el("case").add(new Option(item.title, item.case_id));
});
el("logout").onclick = () => { identity = null; assessment = null; mfaToken = null; el("password").value = ""; el("otp").value = ""; el("result").replaceChildren(); el("case").replaceChildren(new Option("Sign in first", "")); el("download").disabled = true; };
el("case").onchange = () => { assessment = null; el("result").replaceChildren(); el("download").disabled = true; };
el("assessment").onsubmit = event => { event.preventDefault(); void perform(async () => {
  if (!identity || !el("case").value) throw new Error("Sign in and select an existing case first.");
  const base = `/v1/cases/${encodeURIComponent(el("case").value)}`; const params = `?user_id=${encodeURIComponent(identity.user_id)}`;
  if (el("files").files.length) { const form = new FormData(); for (const file of el("files").files) form.append("files", file); await request(`${base}/documents${params}`, "POST", form); el("files").value = ""; }
  const history = await (await request(`${base}/history${params}`)).json();
  const documents = history.documents.filter(item => item.kind === "uploaded").map(item => item.doc_id);
  if (documents.length > 10) throw new Error("Use web document selection when the case has more than 10 uploaded files.");
  const facts = { description: el("description").value };
  for (const name of strings) facts[name] = el(name).value;
  for (const name of Object.keys(flags)) facts[name] = el(name).value === "yes" ? true : el(name).value === "no" ? false : null;
  assessment = await (await request(`${base}/software-assessments${params}`, "POST", { request_id: crypto.randomUUID(), facts, document_ids: documents, external_acknowledged: el("external").checked })).json();
  el("result").replaceChildren(); const warning = document.createElement("p"); warning.textContent = assessment.warning; el("result").append(warning);
  // No HTML interpretation of uploaded excerpts, model output, or source titles.
  const preview = document.createElement("pre"); preview.style.whiteSpace = "pre-wrap";
  preview.textContent = JSON.stringify({ provider: assessment.provider, model: assessment.model, coverage: assessment.coverage, output: assessment.output, document_locations: assessment.documents, legal_sources: assessment.sources }, null, 2); el("result").append(preview);
}); };
el("download").onclick = () => perform(async () => {
  if (!assessment || !identity) return;
  const response = await request(`/v1/cases/${encodeURIComponent(el("case").value)}/software-assessments/${assessment.assessment_id}/export?user_id=${encodeURIComponent(identity.user_id)}&revision=${assessment.revision}`);
  const url = URL.createObjectURL(await response.blob()); const link = document.createElement("a"); link.href = url; link.download = `software-assessment-v${assessment.revision}.pdf`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
