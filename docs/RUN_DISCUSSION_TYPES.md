# Run Guide: Discussion Types and CLI Options

This guide lists all supported CLI options and shows how to run the system in each discussion type.

## Minimal runnable example

```bash
python examples/minimal_demo.py
```

## Main CLI entrypoint

```bash
python -m aijurisdictionagents --country SK --instruction "We believe the contract was breached due to late delivery."
```

## Discussion types

- `advice` (default): lawyer-only advice flow, no judge approval loop.
- `court`: judge review loop; judge can reject and force lawyer retry.

## All CLI options

```text
--data-dir DATA_DIR
--instruction INSTRUCTION
--country COUNTRY
--language LANGUAGE
--question-timeout-minutes QUESTION_TIMEOUT_MINUTES
--allow-pdf
--log-level LOG_LEVEL
--discussion-max-minutes DISCUSSION_MAX_MINUTES
--discussion-type {advice,court}
--case-id CASE_ID
```

Notes:
- `--country` is required.
- `--discussion-type` defaults to `advice`.
- `--discussion-max-minutes 0` means unlimited time.
- `--case-id` is used for existing case append in `advice` + Slovakia mode.

## Run commands by discussion type

### 1) Advice mode (default)

```bash
python -m aijurisdictionagents --country SK --discussion-type advice --instruction "Summarize my contract dispute options."
```

With documents:

```bash
python -m aijurisdictionagents --country SK --discussion-type advice --data-dir data --instruction "Assess breach risk from attached files."
```

With existing Slovakia case:

```bash
python -m aijurisdictionagents --country SK --discussion-type advice --case-id <guid> --instruction "Add new facts and continue."
```

### 2) Court mode

```bash
python -m aijurisdictionagents --country SK --discussion-type court --instruction "Prepare litigation strategy for non-payment."
```

With documents:

```bash
python -m aijurisdictionagents --country SK --discussion-type court --data-dir data --instruction "Evaluate evidence and likely court view."
```

## Common option combinations

Language override:

```bash
python -m aijurisdictionagents --country SK --language en-US --discussion-type advice --instruction "Advise me in English."
```

Shorter answer timeout:

```bash
python -m aijurisdictionagents --country SK --question-timeout-minutes 2 --discussion-type court --instruction "Proceed with court analysis."
```

Limit total discussion duration:

```bash
python -m aijurisdictionagents --country SK --discussion-max-minutes 15 --discussion-type advice --instruction "Give actionable next steps."
```

Enable PDF ingestion:

```bash
pip install pypdf
python -m aijurisdictionagents --country SK --allow-pdf --data-dir data --discussion-type court --instruction "Analyze uploaded PDFs."
```

Set logging verbosity:

```bash
python -m aijurisdictionagents --country SK --log-level INFO --discussion-type advice --instruction "Run with concise logs."
```

## Provider setup examples

OpenAI:

```powershell
$env:LLM_PROVIDER="openai"
$env:OPENAI_KEY="..."
python -m aijurisdictionagents --country SK --discussion-type advice --instruction "Provide legal guidance."
```

Azure Foundry:

```powershell
$env:LLM_PROVIDER="azurefoundry"
$env:AZURE_OPENAI_ENDPOINT="https://YOUR_RESOURCE_NAME.openai.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT="your_deployment_name"
$env:AZURE_OPENAI_API_KEY="..."
python -m aijurisdictionagents --country SK --discussion-type court --instruction "Run court discussion."
```
