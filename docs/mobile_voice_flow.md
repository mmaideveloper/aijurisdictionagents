# Mobile STT/TTS plynuly command flow

Tento dokument popisuje hlasovy orchestrator pre mobilnu aplikaciu:

- priebezne prijima STT transkripty
- deduplikuje partial/final vstupy
- explicitne ukoncenie diktovania (`posli`, `to je vsetko`) vykona akciu hned
- po 5 sekundach neaktivity bez explicitneho ukoncenia pyta potvrdenie:
  `Mozem uz odpovedat na otazku? Povedzte ano alebo nie.`
- pocas cakania na potvrdenie prompt automaticky neopakuje; caka na `ano`
  alebo `nie`
- klik na mikrofon pocas pocuvania alebo potvrdenia je explicitne vypnutie
  hlasoveho vstupu; automaticky sa znovu nezapne, kym ho pouzivatel nezapne
- odpoved `ano` zastavi mikrofon pocas spracovania a odosle pending draft
- odpoved `nie` ponecha rovnaky draft a znovu pocuva dalsie pokracovanie
- pocas TTS odpovede sa mikrofon automaticky nezapina, aby dych alebo sum
  neprerusil asistenta; pouzivatel prerusi odpoved explicitne kliknutim na
  mikrofon v composer-i a potom moze rozpravat
- mapuje prikazy cez existujuci RuleEngine

## GDPR + EU AI Act baseline

- data minimization: orchestrator neuklada raw audio
- transparency: klient dostane eventy `listening_started`, `silence_threshold_reached`
- human oversight: pri nejednoznacnom tichu sa pyta na explicitne potvrdenie pred akciou
- traceability: transcript id je stabilny kluc pre audit bez full raw audio obsahu
