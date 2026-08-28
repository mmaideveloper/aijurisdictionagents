from __future__ import annotations

from copy import deepcopy
from typing import Any


def build_default_slovak_flow_packs() -> list[dict[str, Any]]:
    packs: list[dict[str, Any]] = [
        {
            "flow_key": "sk.system.unsupported_or_human_review",
            "version": 1,
            "jurisdiction": "SK",
            "domain": "governance",
            "title": "Bezpečný prechod na ľudskú kontrolu",
            "description": (
                "Explicitný neautomatizovaný tok pre typy prípadov bez schváleného "
                "vykonateľného pracovného postupu."
            ),
            "is_enabled": True,
            "definition": {
                "required_facts": [],
                "conditional_facts": [],
                "mcp_retrieval": {"required": False, "query_keys": []},
                "allowed_tools": [],
                "required_tools": [],
                "optional_tools": [],
                "consent_policy": {"required_for_personal_data_tools": True},
                "prompt_references": ["case_type_prompt@current"],
                "templates": [],
                "validation_gates": ["review_case"],
                "escalation_rules": ["always_human_review"],
                "human_review": {"required": True},
                "automated_finalization": False,
            },
        },
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
                "steps": [
                    "collect_parties_and_subject",
                    "validate_price_and_payment_terms",
                    "generate_documents",
                ],
                "delivery": {"single_document": "sale_purchase_agreement", "multi_document_bundle": "zip"},
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
                "intent": {
                    "keywords": [
                        "orsr",
                        "obchodny register",
                        "obchodný register",
                        "zapis do orsr",
                        "pridanie vlastnika firmy",
                        "novy vlastnik firmy",
                    ]
                },
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
                "steps": [
                    "collect_company_and_change_facts",
                    "verify_company_in_register",
                    "prepare_registry_documents",
                ],
                "delivery": {"single_document": None, "multi_document_bundle": "zip"},
            },
        },
        {
            "flow_key": "sk.company.owner_transfer",
            "version": 1,
            "jurisdiction": "SK",
            "domain": "commercial",
            "title": "Prevod obchodného podielu (nový vlastník firmy)",
            "description": "Postup a dokumentácia pre pridanie/prevod nového vlastníka v s.r.o.",
            "is_enabled": True,
            "definition": {
                "intent": {
                    "keywords": [
                        "novy vlastnik firmy",
                        "dalsi vlastnik",
                        "prevod obchodneho podielu",
                        "pridanie noveho vlastnika",
                    ]
                },
                "required_facts": [
                    "company_name",
                    "transferor_details",
                    "transferee_details",
                    "transfer_share_scope",
                    "effective_date",
                ],
                "tools": ["obchodny_register_company_check"],
                "outputs": [
                    "share_transfer_agreement",
                    "corporate_resolution",
                    "registry_filing_package",
                ],
                "steps": [
                    "collect_transfer_facts",
                    "confirm_transferor_from_orsr",
                    "generate_transfer_documents",
                ],
                "delivery": {"single_document": None, "multi_document_bundle": "zip"},
            },
        },
        {
            "flow_key": "sk.civil.lease_advisory",
            "version": 1,
            "jurisdiction": "SK",
            "domain": "civil",
            "title": "Prenájom bytu (poradenstvo a zmluva)",
            "description": "Checklist pravidiel prenájmu + návrh nájomnej zmluvy.",
            "is_enabled": True,
            "definition": {
                "intent": {
                    "keywords": [
                        "prenajom bytu",
                        "najomna zmluva",
                        "podnajomnik",
                        "vypovedat zmluvu",
                    ]
                },
                "required_facts": [
                    "property_identification",
                    "landlord_identification",
                    "tenant_identification",
                    "rent_terms",
                ],
                "outputs": ["lease_advisory_checklist", "lease_agreement_draft"],
                "steps": [
                    "collect_lease_context",
                    "assess_termination_and_damage_risks",
                    "generate_lease_documents",
                ],
                "delivery": {"single_document": None, "multi_document_bundle": "zip"},
            },
        },
        {
            "flow_key": "sk.probate.inheritance_proceeding",
            "version": 1,
            "jurisdiction": "SK",
            "domain": "civil",
            "title": "Dedičské konanie",
            "description": "Príprava podkladov a kontrolný postup pre dedičské konanie.",
            "is_enabled": True,
            "definition": {
                "intent": {
                    "keywords": [
                        "deditske konanie",
                        "dedičské konanie",
                        "dedicia",
                    ]
                },
                "required_facts": [
                    "decedent_identification",
                    "heirs",
                    "estate_assets",
                ],
                "outputs": ["inheritance_case_brief"],
                "steps": [
                    "collect_decedent_and_heir_data",
                    "prepare_inheritance_case_summary",
                ],
                "delivery": {"single_document": "inheritance_case_brief", "multi_document_bundle": "zip"},
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
                "steps": [
                    "collect_principal_and_agent_details",
                    "confirm_scope_and_validity",
                    "generate_power_of_attorney",
                ],
                "delivery": {"single_document": "power_of_attorney", "multi_document_bundle": "zip"},
                "proactive_recommendations": [
                    "Pri úradných úkonoch upozorni na overenie podpisu.",
                ],
            },
        },
        {
            "flow_key": "sk.civil.payment_confirmation",
            "version": 1,
            "jurisdiction": "SK",
            "domain": "civil",
            "title": "Potvrdenie o prijatí platby",
            "description": "Príprava potvrdenia o prijatí alebo zaplatení sumy s identifikáciou strán a platobných údajov.",
            "is_enabled": True,
            "definition": {
                "intent": {
                    "keywords": [
                        "potvrdenie",
                        "potvrdenie o zaplateni",
                        "potvrdenie o zaplatení",
                        "potvrdenie o prijati sumy",
                        "potvrdenie o prijatí sumy",
                        "prijatie sumy",
                        "prijatie sumu",
                        "prijal sumu",
                        "uhrada",
                        "úhrada",
                    ]
                },
                "required_facts": [
                    "payer_identification",
                    "recipient_identification",
                    "amount",
                    "payment_date",
                    "payment_purpose",
                ],
                "conditional_facts": [],
                "outputs": ["payment_confirmation"],
                "steps": [
                    "collect_payment_confirmation_facts",
                    "validate_party_and_amount_details",
                    "generate_payment_confirmation",
                ],
                "delivery": {"single_document": "payment_confirmation", "multi_document_bundle": "zip"},
                "mcp_retrieval": {
                    "required": True,
                    "query_keys": ["payment_confirmation_legal_requirements"],
                    "failure_policy": "human_review_required",
                },
                "allowed_tools": [],
                "required_tools": [],
                "optional_tools": [],
                "consent_policy": {
                    "purpose": "prepare_payment_confirmation",
                    "required_for_personal_data_tools": True,
                    "withdrawal_supported": True,
                },
                "prompt_references": ["sk.civil.payment_confirmation@1"],
                "templates": ["payment_confirmation"],
                "validation_gates": [
                    "verify_input",
                    "verify_output",
                    "verify_safety_and_gdpr",
                    "review_case",
                ],
                "human_review": {"required_on_failure": True},
                "escalation_rules": [
                    "missing_legal_sources",
                    "unresolved_fact_conflict",
                    "validator_failure",
                ],
                "automated_finalization": True,
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
                "intent": {
                    "keywords": [
                        "overit osobu",
                        "overit firmu",
                        "screening",
                        "preverenie osoby",
                        "preverenie firmy",
                        "vyhladaj informacie o firme",
                        "vyhladaj informacie o osobe",
                    ]
                },
                "required_facts": ["entity_type", "entity_reference"],
                "outputs": ["screening_summary"],
                "tools": [
                    "obchodny_register_company_check",
                    "entity_screening_agent",
                    "slovakia_property_lv_lookup",
                    "dovera_debtor_check",
                ],
                "steps": [
                    "collect_target_entity",
                    "run_screening_tools",
                    "prepare_summary_document",
                ],
                "delivery": {"single_document": "screening_summary", "multi_document_bundle": "zip"},
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
    payment_confirmation_v1 = next(
        item
        for item in packs
        if item["flow_key"] == "sk.civil.payment_confirmation" and item["version"] == 1
    )
    payment_confirmation_v2 = deepcopy(payment_confirmation_v1)
    payment_confirmation_v2["version"] = 2
    payment_confirmation_v2["definition"]["prompt_references"] = [
        "sk.civil.payment_confirmation@2"
    ]
    packs.append(payment_confirmation_v2)
    return packs
