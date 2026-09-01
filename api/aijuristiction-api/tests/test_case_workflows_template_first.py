from typing import Any

from app.case_workflows import service
from app.document_templates.models import DocumentTemplateDefinition, TemplateSourceReference
from app.document_templates.store import DocumentTemplateNotFoundError


class _FakeTemplateStore:
    def get(self, *, template_key: str, jurisdiction: str | None = None):
        if template_key != "sk.employment.employment_contract":
            raise DocumentTemplateNotFoundError(template_key)
        return DocumentTemplateDefinition(
            template_id="seed-sk-employment-contract",
            template_key="sk.employment.employment_contract",
            lineage_key="seed-sk-employment-contract",
            jurisdiction=jurisdiction or "SK",
            language="sk-SK",
            category="Pracovne a personalne dokumenty",
            title="Pracovna zmluva",
            template_kind="employment_contract",
            description="test template",
            source_format="HTML",
            source_url="https://example.test/pracovna-zmluva",
            body=(
                "PRACOVNÁ ZMLUVA\n\nČlánok I\nDruh práce\n"
                "Pozícia: {{job_position}}\n\nČlánok IV\nMzda\n"
                "Zamestnávateľ: {{employer_business_name}}\n"
                "Mzda: {{base_monthly_salary}}\n"
            ),
            keywords=("pracovna zmluva",),
            placeholders=(
                "job_position", "employer_business_name", "base_monthly_salary",
                "employee_full_name", "employee_birth_date", "employee_residence",
                "place_of_work", "start_date", "employment_term_description",
                "weekly_working_hours", "employer_seat", "employer_ico",
                "employer_representative", "job_description",
            ),
            source_refs=(
                TemplateSourceReference(
                    label="Reviewed test source",
                    url="https://example.test/reviewed-source",
                    publisher="Test publisher",
                    source_kind="external_template_page",
                    notes="Synthetic source metadata for provenance testing.",
                ),
            ),
            disclaimer_title="Dôležité upozornenie",
            disclaimer_text="Pred podpisom je povinná ľudská kontrola.",
            disclaimer_footer="Vzorový návrh – vyžaduje ľudskú kontrolu.",
        )

    def find_best_match(
        self, *, request_text: str, country: str, template_kind: str | None = None
    ):
        del country
        if template_kind == "employment_contract" and "pracovn" in request_text.lower():
            return 10, self.get(
                template_key="sk.employment.employment_contract", jurisdiction="SK"
            )
        return 0, None


def test_render_template_first_employment_draft_uses_managed_template(monkeypatch: Any) -> None:
    monkeypatch.setattr(service, "get_document_template_store", lambda: _FakeTemplateStore())

    rendered = service._render_template_first_employment_draft(
        {
            "jurisdiction": "SK",
            "language": "sk-SK",
            "case_type_key": "sk.employment.employment_contract",
            "request_text": "Priprav pracovnu zmluvu.",
            "verified_facts": {
                "employer_business_name": "Fiktíva Digital Solutions",
                "employer_seat": "Inovačná 18, 040 01 Košice",
                "employer_ico": "99 999 999",
                "employer_representative": "Ing. Martin Vzorový, konateľ",
                "employee_full_name": "Lucia Vzorová",
                "employee_birth_date": "14. februára 1994",
                "employee_birth_number": "945214/0000",
                "employee_residence": "Vzorová 27, 058 01 Poprad",
                "job_position": "AI vývojár / softvérový inžinier",
                "job_description": "Návrh, vývoj, testovanie a údržba softvérových riešení.",
                "place_of_work": "Inovačná 18, 040 01 Košice",
                "start_date": "1. októbra 2026",
                "employment_term_description": "pracovný pomer na dobu neurčitú",
                "probation_period": "3 mesiace",
                "base_monthly_salary": "3 200 EUR brutto",
                "weekly_working_hours": "40 hodín",
                "working_time_distribution": "pondelok až piatok",
                "vacation_entitlement": "v rozsahu podľa Zákonníka práce",
                "signature_place": "Košice",
                "signature_date": "15. septembra 2026",
                "employer_signatory_name": "Ing. Martin Vzorový",
                "employee_signatory_name": "Lucia Vzorová",
            },
        }
    )

    assert rendered is not None
    answer, template = rendered
    normalized = " ".join(answer.split()).lower()
    assert template.template_key == "sk.employment.employment_contract"
    assert "článok i" in normalized
    assert "článok iv" in normalized
    assert "fiktíva digital solutions" in normalized


def test_template_first_test_keeps_real_shared_modules_available() -> None:
    from aijurisdictionagents.api_db import ApiDatabaseStore, CaseDocument

    assert callable(ApiDatabaseStore.from_env)
    assert CaseDocument.__module__ == "aijurisdictionagents.api_db.store"


def test_template_draft_artifact_persists_fact_free_provenance() -> None:
    template = _FakeTemplateStore().get(
        template_key="sk.employment.employment_contract", jurisdiction="SK"
    )

    artifact = service._template_draft_artifact(
        state={"workflow_run_id": "workflow-123", "verified_facts": {"client_name": "Lucia Vzorová"}},
        template=template,
    )

    assert artifact["artifact_id"] == "workflow-123:draft"
    assert artifact["template_key"] == "sk.employment.employment_contract"
    assert artifact["template_version"] == 1
    assert artifact["template_source_url"] == "https://example.test/pracovna-zmluva"
    assert artifact["template_source_references"] == [
        {
            "label": "Reviewed test source",
            "url": "https://example.test/reviewed-source",
            "publisher": "Test publisher",
            "source_kind": "external_template_page",
            "notes": "Synthetic source metadata for provenance testing.",
        }
    ]
    assert artifact["human_review_required"] is True
    assert artifact["human_review_disclosure"]["footer"] == "Vzorový návrh – vyžaduje ľudskú kontrolu."
    assert "verified_facts" not in artifact
    assert "Lucia Vzorová" not in str(artifact)
