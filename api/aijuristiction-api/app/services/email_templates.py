from __future__ import annotations

import base64
from dataclasses import dataclass
from html import escape
from typing import Any

HEADER_CID = "jurisdigta-email-header@jurisdigta"
FOOTER_CID = "jurisdigta-email-footer@jurisdigta"
_BRANDED_TEMPLATE_VERSION = "jurisdigta-email-v1"
_OTP_EVENTS = {"registration_code", "sign_in_code", "otp", "one_time_code"}

_HEADER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="210" viewBox="0 0 900 210" role="img" aria-label="JurisDigta header"><rect width="900" height="210" fill="#f8fafc"/><path d="M0 0h900v24H0z" fill="#1b7f8e"/><path d="M0 186h900v24H0z" fill="#d6a84f"/><rect x="64" y="54" width="96" height="96" rx="18" fill="#ffffff" stroke="#1b7f8e" stroke-width="6"/><path d="M112 82v42M88 104l24-10 24 10M88 104l-12 22M136 104l12 22" fill="none" stroke="#172033" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="76" cy="126" r="9" fill="#d6a84f"/><circle cx="148" cy="126" r="9" fill="#d6a84f"/><circle cx="112" cy="94" r="9" fill="#1b7f8e"/><rect x="96" y="126" width="32" height="20" rx="3" fill="#172033"/><text x="190" y="98" font-family="Georgia, 'Times New Roman', serif" font-size="42" font-weight="700" fill="#172033">JurisDigta</text><text x="192" y="134" font-family="Arial, sans-serif" font-size="20" fill="#475569">Professional legal workflow notification</text></svg>"""

_FOOTER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="150" viewBox="0 0 900 150" role="img" aria-label="JurisDigta footer"><rect width="900" height="150" fill="#172033"/><path d="M0 0h900v8H0z" fill="#d6a84f"/><text x="64" y="58" font-family="Georgia, 'Times New Roman', serif" font-size="25" font-weight="700" fill="#ffffff">JurisDigta</text><text x="64" y="91" font-family="Arial, sans-serif" font-size="16" fill="#cbd5e1">AI-assisted legal documents require user or professional review before filing, signing, or reliance.</text><text x="64" y="120" font-family="Arial, sans-serif" font-size="14" fill="#94a3b8">Privacy by design | GDPR-aware workflows | EU AI Act human oversight</text></svg>"""


@dataclass(frozen=True)
class BrandedEmail:
    subject: str
    text_body: str
    html_body: str
    inline_attachments: list[dict[str, str]]

    def metadata(self, **values: Any) -> dict[str, Any]:
        metadata: dict[str, Any] = dict(values)
        metadata["html_body"] = self.html_body
        metadata["attachments"] = list(self.inline_attachments)
        metadata["template"] = _BRANDED_TEMPLATE_VERSION
        return metadata


def build_welcome_email(*, full_name: str) -> BrandedEmail:
    name = _display_name(full_name)
    subject = "Welcome to AI Jurisdiction"
    body = (
        f"Hello {name},\n\n"
        "your account was created successfully. "
        "You can now sign in and start working with your legal assistant.\n\n"
        "Generated legal outputs should be reviewed before filing, signing, or relying on them.\n"
    )
    html = _render_branded_layout(
        title="Welcome to JurisDigta",
        greeting=f"Hello {name},",
        paragraphs=[
            "Your account was created successfully.",
            "You can now sign in and continue your legal workflow with privacy-aware document support.",
            "Generated legal outputs should be reviewed before filing, signing, or relying on them.",
        ],
        details=[("Account status", "Ready to use")],
    )
    return _email(subject=subject, text_body=body, html_body=html)


def build_subscription_change_email(*, full_name: str, plan_code: str) -> BrandedEmail:
    name = _display_name(full_name)
    plan = _display_value(plan_code)
    subject = "Subscription change requested"
    body = (
        f"Hello {name},\n\n"
        f"your subscription change request to plan '{plan}' was recorded and is now pending.\n"
    )
    html = _render_branded_layout(
        title="Subscription Change Requested",
        greeting=f"Hello {name},",
        paragraphs=["Your subscription change request was recorded and is now pending."],
        details=[("Requested plan", plan), ("Status", "Pending")],
    )
    return _email(subject=subject, text_body=body, html_body=html)


def build_subscription_status_email(*, full_name: str, plan_code: str, status: str) -> BrandedEmail:
    name = _display_name(full_name)
    plan = _display_value(plan_code)
    normalized_status = _display_value(status)
    if status == "paid":
        subject = "Payment confirmed"
        paragraphs = [
            "Payment for your subscription was confirmed and your plan is active.",
            "Your invoice is attached as a PDF and UBL XML file.",
        ]
        body = (
            f"Hello {name},\n\n"
            f"payment for your '{plan}' subscription was confirmed and your plan is active.\n"
            "Your invoice is attached as a PDF and UBL XML file.\n"
        )
    elif status == "failed":
        subject = "Payment failed"
        paragraphs = ["Payment for your subscription failed. Please retry your payment method."]
        body = f"Hello {name},\n\npayment for your '{plan}' subscription failed. Please retry your payment method.\n"
    else:
        subject = "Subscription status changed"
        paragraphs = ["Your subscription status changed."]
        body = f"Hello {name},\n\nyour subscription '{plan}' status changed to '{normalized_status}'.\n"
    html = _render_branded_layout(
        title=subject,
        greeting=f"Hello {name},",
        paragraphs=paragraphs,
        details=[("Plan", plan), ("Status", normalized_status)],
    )
    return _email(subject=subject, text_body=body, html_body=html)


def build_case_documents_email(*, case_subject: str, version: str, correlation_id: str) -> BrandedEmail:
    subject_value = _display_value(case_subject) or "Generated legal documents"
    version_value = _display_value(version) or "v1"
    correlation_value = _display_value(correlation_id)
    subject = f"Legal document package | {subject_value}"
    body = (
        "Dear client,\n\n"
        f"Please find attached generated documents for case '{subject_value}'.\n\n"
        "Review the generated legal documents before filing, signing, or relying on them.\n\n"
        "Regards,\nJurisDigta Legal Team\n\n"
        f"Case Subject: {subject_value}\nVersion: {version_value}\nCorrelation ID: {correlation_value}\n"
    )
    html = _render_branded_layout(
        title="Legal Document Package",
        greeting="Dear client,",
        paragraphs=[
            "Please find attached generated documents for the referenced case subject.",
            "Review the generated legal documents before filing, signing, or relying on them.",
        ],
        details=[
            ("Case subject", subject_value),
            ("Version", version_value),
            ("Correlation ID", correlation_value),
        ],
    )
    return _email(subject=subject, text_body=body, html_body=html)


def build_generic_branded_email(*, subject: str, body: str) -> BrandedEmail:
    clean_subject = _display_value(subject) or "JurisDigta notification"
    paragraphs = [paragraph for paragraph in _plain_text_paragraphs(body) if paragraph]
    if not paragraphs:
        paragraphs = ["This notification was generated by JurisDigta."]
    html = _render_branded_layout(
        title=clean_subject,
        greeting=None,
        paragraphs=paragraphs,
        details=[],
    )
    return _email(subject=clean_subject, text_body=body, html_body=html)


def ensure_branded_email_metadata(*, subject: str, body: str, metadata: dict[str, Any]) -> dict[str, Any]:
    if _is_otp_metadata(subject=subject, metadata=metadata):
        return metadata
    if _metadata_has_current_branding(metadata):
        return metadata

    prepared = dict(metadata)
    existing_attachments = _metadata_attachments(prepared)
    existing_html = prepared.get("html_body")
    if isinstance(existing_html, str) and existing_html.strip():
        email = _email(
            subject=subject,
            text_body=body,
            html_body=_wrap_existing_html(subject=subject, html_body=existing_html),
        )
    else:
        email = build_generic_branded_email(subject=subject, body=body)
    prepared["html_body"] = email.html_body
    prepared["attachments"] = list(email.inline_attachments) + existing_attachments
    prepared["template"] = _BRANDED_TEMPLATE_VERSION
    return prepared


def _is_otp_metadata(*, subject: str, metadata: dict[str, Any]) -> bool:
    event = str(metadata.get("event") or "").strip().lower()
    if event in _OTP_EVENTS:
        return True
    normalized_subject = subject.strip().lower()
    return " code" in normalized_subject or normalized_subject.endswith("code")


def _metadata_has_current_branding(metadata: dict[str, Any]) -> bool:
    if metadata.get("template") != _BRANDED_TEMPLATE_VERSION:
        return False
    html_body = metadata.get("html_body")
    attachments = _metadata_attachments(metadata)
    return (
        isinstance(html_body, str)
        and f"cid:{HEADER_CID}" in html_body
        and f"cid:{FOOTER_CID}" in html_body
        and any(item.get("content_id") == HEADER_CID for item in attachments)
        and any(item.get("content_id") == FOOTER_CID for item in attachments)
    )


def _metadata_attachments(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    attachments = metadata.get("attachments")
    if not isinstance(attachments, list):
        return []
    return [dict(item) for item in attachments if isinstance(item, dict)]


def _wrap_existing_html(*, subject: str, html_body: str) -> str:
    return _render_branded_layout(
        title=_display_value(subject) or "JurisDigta notification",
        greeting=None,
        paragraphs=[],
        details=[],
        raw_html=html_body,
    )


def _email(*, subject: str, text_body: str, html_body: str) -> BrandedEmail:
    return BrandedEmail(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        inline_attachments=_inline_attachments(),
    )


def _render_branded_layout(
    *,
    title: str,
    greeting: str | None,
    paragraphs: list[str],
    details: list[tuple[str, str]],
    raw_html: str | None = None,
) -> str:
    detail_rows = "".join(
        "<tr>"
        f"<th style=\"padding:10px 12px;text-align:left;border-bottom:1px solid #e2e8f0;color:#475569;font-size:13px;\">{escape(label)}</th>"
        f"<td style=\"padding:10px 12px;border-bottom:1px solid #e2e8f0;color:#172033;font-size:13px;\">{escape(value)}</td>"
        "</tr>"
        for label, value in details
        if label and value
    )
    details_table = (
        "<table role=\"presentation\" style=\"width:100%;border-collapse:collapse;margin:18px 0;border:1px solid #e2e8f0;\">"
        f"{detail_rows}</table>"
        if detail_rows
        else ""
    )
    paragraph_html = "".join(
        f"<p style=\"margin:0 0 14px;color:#334155;font-size:15px;line-height:1.6;\">{escape(paragraph)}</p>"
        for paragraph in paragraphs
    )
    greeting_html = (
        f"<p style=\"margin:0 0 14px;color:#172033;font-size:16px;line-height:1.6;font-weight:700;\">{escape(greeting)}</p>"
        if greeting
        else ""
    )
    raw_section = (
        f"<div style=\"margin:0 0 18px;color:#334155;font-size:15px;line-height:1.6;\">{raw_html}</div>"
        if raw_html
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
  <body style="margin:0;background:#eef2f7;padding:24px;font-family:Arial,Helvetica,sans-serif;">
    <table role="presentation" style="width:100%;border-collapse:collapse;">
      <tr>
        <td align="center">
          <table role="presentation" style="width:100%;max-width:760px;border-collapse:collapse;background:#ffffff;border:1px solid #dbe3ef;">
            <tr><td><img src="cid:{HEADER_CID}" width="760" alt="JurisDigta" style="display:block;width:100%;height:auto;border:0;" /></td></tr>
            <tr>
              <td style="padding:28px 34px 26px;">
                <h1 style="margin:0 0 18px;color:#172033;font-family:Georgia,'Times New Roman',serif;font-size:26px;line-height:1.25;">{escape(title)}</h1>
                {greeting_html}
                {paragraph_html}
                {raw_section}
                {details_table}
                <p style="margin:18px 0 0;color:#475569;font-size:13px;line-height:1.55;">This email intentionally excludes unnecessary legal case detail. Keep account access private and contact support if the message is unexpected.</p>
              </td>
            </tr>
            <tr><td><img src="cid:{FOOTER_CID}" width="760" alt="JurisDigta privacy and review footer" style="display:block;width:100%;height:auto;border:0;" /></td></tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _inline_attachments() -> list[dict[str, str]]:
    return [
        _inline_svg_attachment(
            filename="jurisdigta-email-header.svg",
            content_id=HEADER_CID,
            content=_HEADER_SVG,
        ),
        _inline_svg_attachment(
            filename="jurisdigta-email-footer.svg",
            content_id=FOOTER_CID,
            content=_FOOTER_SVG,
        ),
    ]


def _inline_svg_attachment(*, filename: str, content_id: str, content: str) -> dict[str, str]:
    return {
        "filename": filename,
        "mime_type": "image/svg+xml",
        "content_base64": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "content_id": content_id,
        "disposition": "inline",
    }


def _plain_text_paragraphs(body: str) -> list[str]:
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    return [" ".join(part.split()) for part in normalized.split("\n\n")]


def _display_name(value: str) -> str:
    return _display_value(value) or "client"


def _display_value(value: str) -> str:
    return " ".join(str(value or "").strip().split())
