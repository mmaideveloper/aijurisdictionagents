from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from typing import Any, cast
from xml.etree import ElementTree

from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

from aijurisdictionagents.api_db import SubscriptionPlan, User, UserSubscription


@dataclass(frozen=True)
class SubscriptionInvoice:
    invoice_id: str
    issued_at: str
    user: User
    subscription: UserSubscription
    plan: SubscriptionPlan
    payment_provider: str
    payment_id: str
    amount_eur: Decimal

    @property
    def invoice_number(self) -> str:
        year = self.issued_at[:4] or "0000"
        suffix = self.subscription.subscription_id.replace("-", "")[:8].upper()
        return f"JD-{year}-{suffix}"


def build_subscription_invoice(
    *,
    user: User,
    subscription: UserSubscription,
    plan: SubscriptionPlan,
    payment_provider: str,
    payment_id: str,
) -> SubscriptionInvoice:
    issued_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    invoice_id = f"inv_{subscription.subscription_id.replace('-', '')[:16]}"
    return SubscriptionInvoice(
        invoice_id=invoice_id,
        issued_at=issued_at,
        user=user,
        subscription=subscription,
        plan=plan,
        payment_provider=payment_provider,
        payment_id=payment_id,
        amount_eur=_eur(plan.price_eur),
    )


def build_subscription_invoice_attachments(invoice: SubscriptionInvoice) -> list[dict[str, Any]]:
    pdf_bytes = render_subscription_invoice_pdf(invoice)
    xml_bytes = render_subscription_invoice_ubl(invoice)
    filename_root = invoice.invoice_number.lower()
    return [
        {
            "filename": f"{filename_root}.pdf",
            "mime_type": "application/pdf",
            "content_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "disposition": "attachment",
        },
        {
            "filename": f"{filename_root}.xml",
            "mime_type": "application/xml",
            "content_base64": base64.b64encode(xml_bytes).decode("ascii"),
            "disposition": "attachment",
        },
    ]


def render_subscription_invoice_pdf(invoice: SubscriptionInvoice) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
    width, height = A4
    margin = 56
    y = height - margin

    pdf.setTitle(invoice.invoice_number)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(margin, y, "JurisDigta Invoice")
    y -= 36

    pdf.setFont("Helvetica", 10)
    rows = [
        ("Invoice number", invoice.invoice_number),
        ("Issued at", invoice.issued_at),
        ("Supplier", "JurisDigta"),
        ("Buyer", invoice.user.full_name),
        ("Buyer email", invoice.user.email),
        ("Subscription", invoice.plan.display_name),
        ("Payment provider", invoice.payment_provider),
        ("Payment reference", invoice.payment_id),
    ]
    for label, value in rows:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(margin, y, f"{label}:")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(margin + 130, y, _pdf_value(value))
        y -= 18

    y -= 12
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(margin, y, "Description")
    pdf.drawRightString(width - margin, y, "Amount")
    y -= 10
    pdf.line(margin, y, width - margin, y)
    y -= 18

    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin, y, f"{invoice.plan.display_name} subscription")
    pdf.drawRightString(width - margin, y, f"{_money(invoice.amount_eur)} EUR")
    y -= 24
    pdf.line(margin, y, width - margin, y)
    y -= 20
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(width - margin, y, f"Total: {_money(invoice.amount_eur)} EUR")
    y -= 36

    pdf.setFont("Helvetica", 9)
    pdf.drawString(
        margin,
        y,
        "Generated from the subscription payment confirmation record. Review before accounting use.",
    )
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def render_subscription_invoice_ubl(invoice: SubscriptionInvoice) -> bytes:
    invoice_element = ElementTree.Element("Invoice", {"xmlns": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"})
    _child(invoice_element, "CustomizationID", "urn:cen.eu:en16931:2017")
    _child(invoice_element, "ProfileID", "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0")
    _child(invoice_element, "ID", invoice.invoice_number)
    _child(invoice_element, "IssueDate", invoice.issued_at[:10])
    _child(invoice_element, "InvoiceTypeCode", "380")
    _child(invoice_element, "DocumentCurrencyCode", "EUR")
    _child(invoice_element, "BuyerReference", invoice.user.user_id)

    supplier = _child(invoice_element, "AccountingSupplierParty")
    supplier_party = _child(supplier, "Party")
    _child(supplier_party, "Name", "JurisDigta")

    customer = _child(invoice_element, "AccountingCustomerParty")
    customer_party = _child(customer, "Party")
    _child(customer_party, "Name", invoice.user.full_name)
    contact = _child(customer_party, "Contact")
    _child(contact, "ElectronicMail", invoice.user.email)

    payment = _child(invoice_element, "PaymentMeans")
    _child(payment, "PaymentMeansCode", "68")
    _child(payment, "PaymentID", invoice.payment_id)

    total = _child(invoice_element, "LegalMonetaryTotal")
    amount = _money(invoice.amount_eur)
    _child(total, "LineExtensionAmount", amount, {"currencyID": "EUR"})
    _child(total, "TaxExclusiveAmount", amount, {"currencyID": "EUR"})
    _child(total, "TaxInclusiveAmount", amount, {"currencyID": "EUR"})
    _child(total, "PayableAmount", amount, {"currencyID": "EUR"})

    line = _child(invoice_element, "InvoiceLine")
    _child(line, "ID", "1")
    _child(line, "InvoicedQuantity", "1", {"unitCode": "EA"})
    _child(line, "LineExtensionAmount", amount, {"currencyID": "EUR"})
    item = _child(line, "Item")
    _child(item, "Name", f"{invoice.plan.display_name} subscription")
    price = _child(line, "Price")
    _child(price, "PriceAmount", amount, {"currencyID": "EUR"})

    ElementTree.indent(invoice_element, space="  ")
    return cast(bytes, ElementTree.tostring(invoice_element, encoding="utf-8", xml_declaration=True))


def _child(
    parent: ElementTree.Element,
    tag: str,
    text: str | None = None,
    attributes: dict[str, str] | None = None,
) -> ElementTree.Element:
    child = ElementTree.SubElement(parent, tag, attributes or {})
    if text is not None:
        child.text = text
    return child


def _eur(value: int) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _pdf_value(value: str) -> str:
    return " ".join(str(value or "").split())[:96]
