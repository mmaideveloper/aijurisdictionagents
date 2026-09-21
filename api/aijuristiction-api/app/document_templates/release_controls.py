from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateReleaseControl:
    risk_tier: str
    required_preflight_facts: tuple[str, ...]
    submission_mode: str


# These controls are product safeguards, not a substitute for case-specific legal advice.
PRIORITY_THREE_RELEASE_CONTROLS: dict[str, TemplateReleaseControl] = {
    "sk.contract.commercial_agency": TemplateReleaseControl(
        risk_tier="high",
        required_preflight_facts=(
            "principal_identification", "agent_identification", "contract_scope", "territory",
            "commission_terms", "authority_to_conclude", "duration_and_termination",
        ),
        submission_mode="human_review_draft",
    ),
    "sk.company.share_transfer": TemplateReleaseControl(
        risk_tier="high",
        required_preflight_facts=(
            "company_identifier", "current_articles_reviewed", "transferor_identification",
            "transferee_identification", "share_scope", "transfer_price", "transfer_restrictions_checked",
            "general_meeting_consent", "insolvency_and_enforcement_check", "signature_certification_plan",
        ),
        submission_mode="human_review_draft",
    ),
    "sk.company.sro_articles": TemplateReleaseControl(
        risk_tier="high",
        required_preflight_facts=(
            "founder_count", "company_name", "company_seat", "business_activities", "shareholders",
            "registered_capital", "contributions", "managing_directors", "registry_filing_plan",
        ),
        submission_mode="human_review_draft",
    ),
    "sk.court.alimony_petition": TemplateReleaseControl(
        risk_tier="high",
        required_preflight_facts=(
            "applicant_identification", "respondent_identification", "child_identification",
            "court_jurisdiction", "requested_amount", "supporting_evidence",
        ),
        submission_mode="official_form_only",
    ),
    "sk.court.payment_order": TemplateReleaseControl(
        risk_tier="high",
        required_preflight_facts=(
            "claimant_identification", "defendant_identification", "court_jurisdiction", "claim_amount",
            "claim_due_date", "supporting_evidence", "official_filing_route",
        ),
        submission_mode="official_form_only",
    ),
    "sk.court.general_action": TemplateReleaseControl(
        risk_tier="high",
        required_preflight_facts=(
            "claimant_identification", "defendant_identification", "court_jurisdiction", "claim_request",
            "facts", "supporting_evidence", "limitation_period_review",
        ),
        submission_mode="human_review_draft",
    ),
}


def priority_three_release_control(template_key: str) -> TemplateReleaseControl | None:
    return PRIORITY_THREE_RELEASE_CONTROLS.get(template_key.strip())
