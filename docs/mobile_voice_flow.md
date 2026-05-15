# Mobile STT/TTS plynuly command flow

Tento dokument popisuje hlasovy orchestrator pre mobilnu aplikaciu:

- priebezne prijima STT transkripty
- deduplikuje partial/final vstupy
- po 10 sekundach neaktivity pyta potvrdenie vykonania poziadavky
- mapuje prikazy cez existujuci RuleEngine

## GDPR + EU AI Act baseline

- data minimization: orchestrator neuklada raw audio
- transparency: klient dostane eventy `listening_started`, `silence_threshold_reached`
- human oversight: pri tichu sa pyta na explicitne potvrdenie pred akciou
- traceability: transcript id je stabilny kluc pre audit bez full raw audio obsahu
