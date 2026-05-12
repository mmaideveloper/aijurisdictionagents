-- Seed flow packs required by chat-simulator testcases.
-- Idempotent: inserts only when (jurisdiction, flow_key, version) does not already exist.

INSERT INTO flow_packs (
    flow_id,
    flow_key,
    version,
    jurisdiction,
    domain,
    title,
    description,
    definition_json,
    is_enabled,
    is_deleted,
    created_at,
    updated_at,
    deleted_at
)
SELECT
    'seed-sk-company-owner-transfer-v1',
    'sk.company.owner_transfer',
    1,
    'SK',
    'commercial',
    'Prevod obchodného podielu (nový vlastník firmy)',
    'Postup a dokumentácia pre pridanie/prevod nového vlastníka v s.r.o.',
    '{"intent":{"keywords":["novy vlastnik firmy","dalsi vlastnik","prevod obchodneho podielu","pridanie noveho vlastnika"]},"required_facts":["company_name","transferor_details","transferee_details","transfer_share_scope","effective_date"],"outputs":["share_transfer_agreement","corporate_resolution","registry_filing_package"],"steps":["collect_transfer_facts","confirm_transferor_from_orsr","generate_transfer_documents"],"delivery":{"single_document":null,"multi_document_bundle":"zip"}}',
    1,
    0,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    NULL
WHERE NOT EXISTS (
    SELECT 1 FROM flow_packs WHERE flow_key = 'sk.company.owner_transfer' AND version = 1 AND jurisdiction = 'SK'
);

INSERT INTO flow_packs (
    flow_id,
    flow_key,
    version,
    jurisdiction,
    domain,
    title,
    description,
    definition_json,
    is_enabled,
    is_deleted,
    created_at,
    updated_at,
    deleted_at
)
SELECT
    'seed-sk-civil-lease-advisory-v1',
    'sk.civil.lease_advisory',
    1,
    'SK',
    'civil',
    'Prenájom bytu (poradenstvo a zmluva)',
    'Checklist pravidiel prenájmu + návrh nájomnej zmluvy.',
    '{"intent":{"keywords":["prenajom bytu","najomna zmluva","podnajomnik","vypovedat zmluvu"]},"required_facts":["property_identification","landlord_identification","tenant_identification","rent_terms"],"outputs":["lease_advisory_checklist","lease_agreement_draft"],"steps":["collect_lease_context","assess_termination_and_damage_risks","generate_lease_documents"],"delivery":{"single_document":null,"multi_document_bundle":"zip"}}',
    1,
    0,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    NULL
WHERE NOT EXISTS (
    SELECT 1 FROM flow_packs WHERE flow_key = 'sk.civil.lease_advisory' AND version = 1 AND jurisdiction = 'SK'
);

INSERT INTO flow_packs (
    flow_id,
    flow_key,
    version,
    jurisdiction,
    domain,
    title,
    description,
    definition_json,
    is_enabled,
    is_deleted,
    created_at,
    updated_at,
    deleted_at
)
SELECT
    'seed-sk-probate-inheritance-v1',
    'sk.probate.inheritance_proceeding',
    1,
    'SK',
    'civil',
    'Dedičské konanie',
    'Príprava podkladov a kontrolný postup pre dedičské konanie.',
    '{"intent":{"keywords":["deditske konanie","dedičské konanie","dedicia"]},"required_facts":["decedent_identification","heirs","estate_assets"],"outputs":["inheritance_case_brief"],"steps":["collect_decedent_and_heir_data","prepare_inheritance_case_summary"],"delivery":{"single_document":"inheritance_case_brief","multi_document_bundle":"zip"}}',
    1,
    0,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    NULL
WHERE NOT EXISTS (
    SELECT 1 FROM flow_packs WHERE flow_key = 'sk.probate.inheritance_proceeding' AND version = 1 AND jurisdiction = 'SK'
);

INSERT INTO flow_packs (
    flow_id,
    flow_key,
    version,
    jurisdiction,
    domain,
    title,
    description,
    definition_json,
    is_enabled,
    is_deleted,
    created_at,
    updated_at,
    deleted_at
)
SELECT
    'seed-sk-civil-payment-confirmation-v1',
    'sk.civil.payment_confirmation',
    1,
    'SK',
    'civil',
    'Potvrdenie o prijatí platby',
    'Príprava potvrdenia o prijatí alebo zaplatení sumy s identifikáciou strán a platobných údajov.',
    '{"intent":{"keywords":["potvrdenie","potvrdenie o zaplateni","potvrdenie o zaplatení","potvrdenie o prijati sumy","potvrdenie o prijatí sumy","prijatie sumy","prijatie sumu","prijal sumu","uhrada","úhrada"]},"required_facts":["payer_identification","recipient_identification","amount","payment_date","payment_purpose"],"outputs":["payment_confirmation"],"steps":["collect_payment_confirmation_facts","validate_party_and_amount_details","generate_payment_confirmation"],"delivery":{"single_document":"payment_confirmation","multi_document_bundle":"zip"}}',
    1,
    0,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    NULL
WHERE NOT EXISTS (
    SELECT 1 FROM flow_packs WHERE flow_key = 'sk.civil.payment_confirmation' AND version = 1 AND jurisdiction = 'SK'
);
