# Mobile and Web STT/TTS message flow

Default speech type is `message` for mobile and web. `conversation` remains
available as the legacy continuous voice-session flow.

## `speechtype=message` default

- user enables audio output
- Jurisdicta says the localized welcome/instruction message
- user clicks the composer microphone to dictate one message draft
- STT writes the transcript into the visible input box
- microphone remains active until the user clicks send, clicks microphone again,
  or says a send command such as `send`, `posli`, or `senden`
- ordinary dictated messages are reviewed as text before submission
- explicit action phrases such as "create a new case" or "information about
  company X" are routed from transcript text through the same intent/action
  layer used by typed messages

For GDPR/data-minimization, device/browser STT is preferred when available. Some
Android devices do not expose usable local STT, and some platform recognizers may
use Google/cloud services outside this app's direct pipeline. Server/Azure STT is
therefore an explicit fallback that requires consent before raw audio upload.

## `speechtype=conversation`

The previous mobile voice orchestrator is preserved when
`AIJ_SPEECHTYPE=conversation`:

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
- raw audio upload requires explicit consent; default message mode submits
  reviewed transcript text, not audio
- transparency: klient dostane eventy `listening_started`, `silence_threshold_reached`
- human oversight: pri nejednoznacnom tichu sa pyta na explicitne potvrdenie pred akciou
- traceability: transcript id je stabilny kluc pre audit bez full raw audio obsahu
