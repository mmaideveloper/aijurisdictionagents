# Jurisdigta e2e test scenarios

Tento dokument slúži ako štartovacia sada testovacích scenárov pre **Jurisdigtu / AI Lawyer Agent**.
Je pripravený tak, aby sa dal použiť:

- ako zadanie pre nové `pytest` unit/integration testy,
- ako checklist pre manuálne QA,
- ako podklad pre CI/CD pipeline v `e2etests/`.

## Navrhovaná štruktúra testov

| Vrstva | Účel | Odporúčaný prefix testu |
| --- | --- | --- |
| Unit | Overenie routingu, klasifikácie vstupu, extrakcie polí, citácií zákonov a dátumu poslednej validácie. | `test_unit_*` |
| Integration | Overenie orchestrace medzi agentom, document processorom, validatorom a law store. | `test_integration_*` |
| End-to-end | Simulácia reálneho správania používateľa cez otázku alebo upload dokumentu. | `test_*_e2e` |

## Matica scenárov

| ID | Test name / spúšťač | Vrstva | Vstup | Konkrétny sample input | Očakávaný výstup |
| --- | --- | --- | --- | --- | --- |
| Q1 | `test_case_question_summary_only_e2e` | E2E | Otázka bez potreby generovať dokument | `Mám spor so susedom, ktorý mi blokuje prístup k parkovaciemu miestu. Chcem vedieť, aké mám možnosti a či mám ísť na obec alebo súd.` | Agent vráti stručné **zhrnutie prípadu**, navrhne **ďalšie kroky**, negeneruje dokument, zobrazí **odkazy na relevantné zákony** a uvedie, že výsledok je len právne informačný prehľad. |
| Q2 | `test_unit_question_summary_only_router` | Unit | Klasifikácia textovej otázky | Rovnaký vstup ako Q1 | Router nastaví mód `summary_only`, `document_required=False`, `document_type=None`. |
| Q3 | `test_integration_question_summary_only_law_citations` | Integration | Otázka bez dokumentu | `Prenajímateľ mi nechce vrátiť depozit po skončení nájmu. Aké mám práva?` | Odpoveď obsahuje summary, možnosti riešenia, aspoň 1-2 citácie zákonov a žiadny generovaný dokument v artefaktoch session. |
| G1 | `test_case_question_document_generation_e2e` | E2E | Otázka + opis prípadu, ktorý má skončiť generovaním dokumentu | `Potrebujem pripraviť splnomocnenie pre brata, aby ma zastupoval na katastri pri prepise bytu v Trnave.` | Agent vyžiada alebo použije potrebné identifikačné údaje, vygeneruje **návrh splnomocnenia**, pridá **summary prípadu**, **overenie správnosti dokumentu** a odkazy na relevantné zákony/predpisy. |
| G2 | `test_unit_document_request_classifier` | Unit | Rozpoznanie potreby generovania dokumentu | Rovnaký vstup ako G1 | Klasifikácia vráti `document_required=True`, `document_type='power_of_attorney'`, `workflow='document_generation'`. |
| G3 | `test_integration_document_generation_contract_output` | Integration | Požiadavka na zmluvu | `Chcem jednoduchú nájomnú zmluvu na byt v Bratislave medzi prenajímateľom Ján Novák a nájomcom Eva Kováčová od 1. 5. 2026 za 900 EUR mesačne.` | Výstup obsahuje návrh dokumentu, summary, kontrolu povinných polí (strany, predmet nájmu, nájomné, trvanie, podpisy) a právne citácie. |
| G4 | `test_contract_summary_e2e` | E2E | Upload existujúceho kontraktu na sumarizáciu | Existujúci fixture upload PDF kontraktu v `e2etests/test_contract_end_to_end.py` | Výsledok obsahuje krátke zhrnutie kontraktu, odporúčanie a citácie na všetky uploadnuté strany dokumentu. |
| D1 | `test_case_document_summary_with_law_timestamp_e2e` | E2E | Upload dokumentu na summary | Upload PDF: `Najomna_zmluva_2024.pdf` | Agent vytvorí **summary dokumentu**, vypíše hlavné strany, predmet, povinnosti a zobrazí **dátum poslednej verifikácie zákonov** použitých pri posúdení. |
| D2 | `test_unit_document_summary_metadata` | Unit | Metadata odpovede pri summary dokumentu | Výstup z parsera nad dokumentom `Kupna_zmluva.pdf` | Response metadata obsahujú `summary`, `law_last_verified_at`, `source_documents`, `jurisdiction='SK'`. |
| D3 | `test_integration_document_summary_law_store_timestamp` | Integration | Summary dokumentu s napojením na law store | Upload dokumentu + seeded law DB s dátumom aktualizácie `2026-03-20T09:30:00Z` | API odpoveď obsahuje dokumentové zhrnutie a presne ten istý timestamp ako `law_last_verified_at`. |
| V1 | `test_case_document_validation_latest_laws_e2e` | E2E | Upload dokumentu na validáciu podľa posledných zákonov | Upload PDF starej nájomnej zmluvy bez depozitu, bez písomnej výpovede a bez identifikácie strán | Agent označí neplatné alebo chýbajúce časti, vypíše **zoznam nájdených problémov**, odporučí opravy a zobrazí **dátum posledného update law store**. |
| V2 | `test_unit_document_validation_flags` | Unit | Validácia pravidiel dokumentu | Text zmluvy bez údajov o depozite, opravách a výpovedi | Validator vráti flags ako `missing_deposit=True`, `missing_termination_clause=True`, `missing_party_identification=True`. |
| V3 | `test_integration_document_validation_with_latest_laws` | Integration | Dokument + law store + validator | Seeded law store s novelou účinnou od `2026-01-01`, upload starého dokumentu | Odpoveď obsahuje validation summary, zoznam porušení voči posledným pravidlám a timestamp poslednej aktualizácie zdroja práva. |
| V4 | `test_slovak_lease_review_e2e` | E2E | Revízia starej slovenskej nájomnej zmluvy | Existujúci fixture upload v `simulate_slovak_lease_review(...)` | Výstup vytvorí revidovaný dokument, diff artefakt, summary vykonaných zmien a zachytí chýbajúce oblasti ako identifikácia strán, depozit, opravy a písomná výpoveď. |

## Detail očakávaní podľa hlavných business flow

### 1. Otázka -> iba summary prípadu bez generovania dokumentu

**Primárny test:** `test_case_question_summary_only_e2e`

Očakávané asercie:

1. Odpoveď obsahuje sekciu typu `summary` alebo `case_summary`.
2. Odpoveď obsahuje sekciu `possible_solutions` alebo explicitné odporúčania ďalších krokov.
3. Odpoveď obsahuje `law_references` s minimálne jedným relevantným predpisom.
4. Odpoveď **neobsahuje** `generated_document`.
5. Odpoveď má bezpečnostný disclaimer, že nejde o finálne zastúpenie advokátom.

### 2. Otázka/popis prípadu -> generovanie dokumentu + kontrola správnosti

**Primárny test:** `test_case_question_document_generation_e2e`

Očakávané asercie:

1. Agent rozpozná typ dokumentu.
2. Výsledok obsahuje `generated_document` alebo exportovateľný text dokumentu.
3. Súčasťou odpovede je `document_summary`.
4. Systém vykoná základnú `document_validation` nad povinnými políčkami.
5. Odpoveď obsahuje `law_references` a odporúčanie na ľudskú kontrolu pri formálnom podaní.

### 3. Upload dokumentu -> summary + dátum poslednej verifikácie zákonov

**Primárny test:** `test_case_document_summary_with_law_timestamp_e2e`

Očakávané asercie:

1. Summary obsahuje typ dokumentu, zmluvné strany a hlavný účel dokumentu.
2. Odpoveď obsahuje pole `law_last_verified_at`.
3. Timestamp je v ISO 8601 formáte.
4. Ak law store nie je dostupný, systém vráti fallback `unknown` alebo `unavailable`, ale flow nespadne.

### 4. Upload dokumentu -> validácia podľa posledných zákonov + dátum posledného update

**Primárny test:** `test_case_document_validation_latest_laws_e2e`

Očakávané asercie:

1. Odpoveď obsahuje `validation_summary`.
2. Odpoveď obsahuje štruktúrovaný zoznam `issues` alebo `invalid_areas`.
3. Každý problém má aspoň stručný návrh opravy.
4. Odpoveď obsahuje `law_last_updated_at` alebo ekvivalentné metadata.
5. Validácia reflektuje poslednú dostupnú verziu zákonov v systéme.

## Návrh jednotných response polí pre testy

Aby sa scenáre dali jednoducho testovať naprieč unit/integration/E2E vrstvami, odporúča sa stabilizovať aspoň tieto polia odpovede:

```json
{
  "mode": "summary_only | document_generation | document_summary | document_validation",
  "summary": "...",
  "possible_solutions": ["..."],
  "generated_document": "...",
  "document_summary": "...",
  "document_validation": {
    "issues": ["..."],
    "status": "pass | warning | fail"
  },
  "law_references": [
    {
      "title": "...",
      "section": "...",
      "url": "..."
    }
  ],
  "law_last_verified_at": "2026-03-20T09:30:00Z",
  "law_last_updated_at": "2026-03-20T09:30:00Z"
}
```

## Odporúčaná implementácia v CI/CD

- **Unit stage**: spúšťať router, parser a validator testy pri každom pull requeste.
- **Integration stage**: spúšťať testy proti seeded law DB a mocked document processoru.
- **E2E stage**: spúšťať deterministické scenáre s fixture dokumentmi a snapshotmi odpovedí.
- **Regression gate**: fail pipeline, ak zmiznú `law_references`, `law_last_verified_at` alebo `document_validation.issues` pre scenáre, ktoré ich vyžadujú.

## Minimálny zoznam testov na okamžité doplnenie

Ak chceš túto sadu zaviesť hneď, odporúčané je začať týmito testami:

1. `test_case_question_summary_only_e2e`
2. `test_case_question_document_generation_e2e`
3. `test_case_document_summary_with_law_timestamp_e2e`
4. `test_case_document_validation_latest_laws_e2e`
5. `test_integration_document_validation_with_latest_laws`
6. `test_unit_document_request_classifier`

Tieto názvy sú zámerne konzistentné s `pytest` naming convention a môžu byť priamo použité pri doplnení automatizovaných testov.
