# AI Car Validator Agent (Slovakia)

`AICarValidatorAgent` pripravuje bezpečný plán overenia vozidla pre slovenské prípady.

## Čo rieši

- Validácia VIN (formát + checksum).
- Predbežné overenie SPZ/EČV formátu.
- Návrh postupu pre overenie údajov o vozidle cez slovenské zdroje.
- Transparentné vysvetlenie limitu: úplná história vlastníkov sa štandardne neposkytuje bez právneho titulu.

## Limity pri histórii vlastníkov

Pri otázke „zoznam všetkých vlastníkov“ agent explicitne uvedie, že ide o citlivé údaje a typicky sú dostupné len oprávneným subjektom (polícia/súd/notár alebo subjekt s právnym dôvodom).

## Integrovaný nástroj

- `slovakia_car_validate`
  - vstup: `vin`, `spz`, `run_api_check`
  - výstup: validácia VIN, pravdepodobnosť slovenského formátu SPZ, krokový plán overenia + API report (ak je API nakonfigurované)

## API checky vozidla

Pri nastavenej `CAR_VALIDATION_API_BASE_URL` nástroj volá endpoint:

- `GET {CAR_VALIDATION_API_BASE_URL}/api/vehicles?ecv=<SPZ>`
- `GET {CAR_VALIDATION_API_BASE_URL}/api/vehicles?vin=<VIN>`

Pre `https://www.databazavozidiel.sk` to znamená:

- `https://www.databazavozidiel.sk/api/vehicles?ecv=BA123AB`
- `https://www.databazavozidiel.sk/api/vehicles?vin=1HGCM82633A004352`

Očakávané polia odpovede:

- `national_wanted_records`
- `vehicle_blocking`
- `leasing_status`
- `lien_status`
- `owner_count`
- `damage_records` (pole záznamov)

Kompatibilné aliasy (pre rôzne implementácie/špecifikácie):

- `nationalWantedRecords`, `isWanted`
- `vehicleBlocking`, `isBlocked`
- `leasingStatus`, `isLeasing`
- `lienStatus`, `isLien`, `zaloznePravo`
- `ownerCount`, `numberOfOwners`
- `damageRecords`, `damages`

Voliteľne sa mapujú aj základné údaje vozidla:

- `brand/make`, `model/vehicleModel`, `year/modelYear`, `color/vehicleColor`

## Deployment

Pre Azure API deployment nastavte v GitHub Environment:

- `CAR_VALIDATION_API_BASE_URL` ako premennú, napríklad `https://www.databazavozidiel.sk`
- `CAR_VALIDATION_API_KEY` ako secret, ak poskytovateľ vyžaduje API kľúč

`API Build and Deploy` a `infra/scripts/deploy_api.ps1` prenesú `CAR_VALIDATION_API_BASE_URL` do API Container App ako bežnú env premennú. `CAR_VALIDATION_API_KEY` sa ukladá ako Container Apps secret `car-validation-api-key` a do aplikácie sa vkladá cez `secretref:car-validation-api-key`.

## Automatické použitie pre car-dotazy

Repo obsahuje pomocníka `answer_slovak_car_validation_question`, ktorý rozpozná car/VIN/SPZ otázky a spustí `slovakia_car_validate`, ak je v registri dostupný.

## Minimal runnable example

```bash
python examples/car_validation_minimal_demo.py
```
