import re
from pathlib import Path

from document_engine.config import settings


class DocumentProcessingError(RuntimeError):
    pass


REQUIRED_FIELDS_BY_TYPE = {
    "confirmation": ["title", "issuer", "recipient", "facts"],
    "power_of_attorney": ["principal", "agent", "scope"],
    "purchase_contract_movable": ["seller", "buyer", "item", "price"],
    "purchase_contract_real_estate": [
        "seller",
        "buyer",
        "property",
        "price",
        "cadastral_area",
    ],
}


def process_document_request(
    *,
    request_id: str,
    correlation_id: str,
    document_type: str,
    payload: dict,
) -> dict:
    required_fields = REQUIRED_FIELDS_BY_TYPE.get(document_type)
    if required_fields is None:
        supported = ", ".join(sorted(REQUIRED_FIELDS_BY_TYPE))
        raise DocumentProcessingError(
            f"Unsupported document_type '{document_type}'. Supported: {supported}"
        )

    missing = [field for field in required_fields if not payload.get(field)]
    if missing:
        raise DocumentProcessingError(
            f"Missing required fields for {document_type}: {', '.join(missing)}"
        )

    body = render_document(document_type=document_type, payload=payload)
    output_path = write_document(
        request_id=request_id,
        correlation_id=correlation_id,
        document_type=document_type,
        body=body,
    )
    return {
        "format": "markdown",
        "document_path": str(output_path),
        "warnings": warnings_for(document_type),
    }


def render_document(*, document_type: str, payload: dict) -> str:
    title = payload.get("title") or document_type.replace("_", " ").title()
    lines = [
        f"# {title}",
        "",
        f"Document type: {document_type}",
        "",
    ]

    if document_type == "confirmation":
        lines.extend(
            [
                f"Issuer: {payload['issuer']}",
                f"Recipient: {payload['recipient']}",
                "",
                "Confirmed facts:",
                str(payload["facts"]),
            ]
        )
    elif document_type == "power_of_attorney":
        lines.extend(
            [
                f"Principal: {payload['principal']}",
                f"Agent: {payload['agent']}",
                "",
                "Scope:",
                str(payload["scope"]),
                "",
                "Signature: __________________________",
            ]
        )
    elif document_type.startswith("purchase_contract"):
        lines.extend(
            [
                f"Seller: {payload['seller']}",
                f"Buyer: {payload['buyer']}",
                f"Subject: {payload.get('item') or payload.get('property')}",
                f"Price: {payload['price']}",
                "",
                "The final legal wording must be reviewed before signing.",
            ]
        )
        if document_type == "purchase_contract_real_estate":
            lines.extend(
                [
                    f"Cadastral area: {payload['cadastral_area']}",
                    "",
                    "Real-estate transfer requires written form and signature checks.",
                ]
            )

    return "\n".join(lines).strip() + "\n"


def write_document(
    *,
    request_id: str,
    correlation_id: str,
    document_type: str,
    body: str,
) -> Path:
    output_dir = Path(settings.generated_documents_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_document_type = re.sub(r"[^a-zA-Z0-9_-]+", "-", document_type).strip("-")
    output_path = output_dir / f"{request_id}-{safe_document_type}.md"
    output_path.write_text(
        f"Correlation-Id: {correlation_id}\n\n{body}", encoding="utf-8"
    )
    return output_path


def warnings_for(document_type: str) -> list[str]:
    if document_type == "purchase_contract_real_estate":
        return [
            "High-risk document: require legal review before signing.",
            "Check cadastral requirements and official signature verification.",
        ]
    if document_type == "power_of_attorney":
        return [
            "Check whether written form or official signature verification is required."
        ]
    return []
