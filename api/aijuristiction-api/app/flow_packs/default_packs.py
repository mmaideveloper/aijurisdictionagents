from __future__ import annotations

from typing import Any


def build_default_slovak_flow_packs() -> list[dict[str, Any]]:
    return [
        {
            "flow_key": "sk.contract.sale_purchase",
            "version": 1,
            "jurisdiction": "SK",
            "domain": "civil",
            "title": "Kúpna zmluva (všeobecná)",
            "description": "Príprava kúpnej zmluvy pre hnuteľné veci a základná kontrola povinných údajov.",
            "is_enabled": True,
            "definition": {
                "intent": {"keywords": ["kúpna zmluva", "kupna zmluva", "predaj", "kupa"]},
                "required_facts": [
                    "seller_identification",
                    "buyer_identification",
                    "subject_description",
                    "purchase_price",
                    "payment_terms",
                ],
                "outputs": ["sale_purchase_agreement", "handover_protocol_template"],
                "proactive_recommendations": [
                    "Navrhni odovzdávací protokol.",
                    "Upozorni na zodpovednosť za vady.",
                ],
            },
        },
        {
            "flow_key": "sk.company.registry_change",
            "version": 1,
            "jurisdiction": "SK",
            "domain": "commercial",
            "title": "Firemné zmeny do ORSR",
            "description": "Balík dokumentov pre časté zmeny v s.r.o. vrátane podania na ORSR.",
            "is_enabled": True,
            "definition": {
                "intent": {"keywords": ["orsr", "obchodny register", "obchodný register", "zapis do orsr"]},
                "required_facts": [
                    "company_name",
                    "company_identifier",
                    "change_type",
                    "effective_date",
                ],
                "tools": ["obchodny_register_company_check"],
                "outputs": [
                    "corporate_resolution",
                    "updated_articles",
                    "registry_filing_package",
                ],
            },
        },
        {
            "flow_key": "sk.civil.power_of_attorney",
            "version": 1,
            "jurisdiction": "SK",
            "domain": "civil",
            "title": "Splnomocnenie",
            "description": "Príprava všeobecného alebo osobitného splnomocnenia so scope control.",
            "is_enabled": True,
            "definition": {
                "intent": {"keywords": ["splnomocnenie", "plna moc", "plná moc"]},
                "required_facts": [
                    "principal_identification",
                    "agent_identification",
                    "scope_of_authority",
                    "validity_period",
                ],
                "outputs": ["power_of_attorney"],
                "proactive_recommendations": [
                    "Pri úradných úkonoch upozorni na overenie podpisu.",
                ],
            },
        },
        {
            "flow_key": "sk.criminal.criminal_complaint",
            "version": 1,
            "jurisdiction": "SK",
            "domain": "criminal",
            "title": "Trestné oznámenie",
            "description": "Štruktúrovaná príprava podania trestného oznámenia s evidenciou dôkazov.",
            "is_enabled": True,
            "definition": {
                "intent": {"keywords": ["trestne oznamenie", "trestné oznámenie", "trestne konanie"]},
                "required_facts": [
                    "complainant_identification",
                    "factual_description",
                    "approx_time_and_place",
                    "available_evidence",
                ],
                "outputs": ["criminal_complaint_submission", "evidence_index"],
                "escalation_rules": ["recommend_human_lawyer_review_if_sensitive_case"],
            },
        },
        {
            "flow_key": "sk.notary.notarial_process",
            "version": 1,
            "jurisdiction": "SK",
            "domain": "notary",
            "title": "Notárske procesy",
            "description": "Príprava podkladov pre notársku zápisnicu a osvedčovanie listín/podpisov.",
            "is_enabled": True,
            "definition": {
                "intent": {"keywords": ["notar", "notár", "notarska zapisnica", "notárska zápisnica"]},
                "required_facts": ["participants", "document_purpose", "required_notary_act"],
                "outputs": ["notary_preparation_checklist"],
                "proactive_recommendations": [
                    "Upozorni na potrebu originálov/príloh.",
                    "Upozorni na overenie totožnosti.",
                ],
            },
        },
        {
            "flow_key": "sk.support.person_company_screening",
            "version": 1,
            "jurisdiction": "SK",
            "domain": "support",
            "title": "Screening osoby/firmy",
            "description": "Pomocný proces pre zistenie verejne dostupných údajov o osobe alebo firme.",
            "is_enabled": True,
            "definition": {
                "intent": {"keywords": ["overit osobu", "overit firmu", "screening", "preverenie osoby", "preverenie firmy"]},
                "required_facts": ["entity_type", "entity_reference"],
                "outputs": ["screening_summary"],
                "tools": ["obchodny_register_company_check", "entity_screening_agent"],
            },
        },
        {
            "flow_key": "cz.contract.sale_purchase",
            "version": 1,
            "jurisdiction": "CZ",
            "domain": "civil",
            "title": "Kupní smlouva (obecná)",
            "description": "Příprava kupní smlouvy pro běžné občanskoprávní převody.",
            "is_enabled": True,
            "definition": {
                "intent": {"keywords": ["kupni smlouva", "koupě", "prodej"]},
                "required_facts": [
                    "seller_identification",
                    "buyer_identification",
                    "subject_description",
                    "purchase_price",
                    "payment_terms",
                ],
                "outputs": ["sale_purchase_agreement", "handover_protocol_template"],
            },
        },
        {
            "flow_key": "cz.civil.power_of_attorney",
            "version": 1,
            "jurisdiction": "CZ",
            "domain": "civil",
            "title": "Plná moc",
            "description": "Příprava obecné nebo zvláštní plné moci.",
            "is_enabled": True,
            "definition": {
                "intent": {"keywords": ["plna moc", "plná moc", "zmocnění"]},
                "required_facts": [
                    "principal_identification",
                    "agent_identification",
                    "scope_of_authority",
                    "validity_period",
                ],
                "outputs": ["power_of_attorney"],
            },
        },
    ]
