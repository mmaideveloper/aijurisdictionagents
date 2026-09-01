# Slovenská reklama JurisDigta pre bežných ľudí

Tento dokument je reprodukovateľné zadanie pre krátku 9:16 reklamu na JurisDigta. Cieľom je ľudsky a pokojne ukázať základnú právnu orientáciu a pomoc s dokumentmi bez sľubovania právneho zastupovania alebo garantovaného výsledku.

## Produkčný brief

- Jazyk: slovenčina.
- Publikum: bežní ľudia, ktorí potrebujú porozumieť právnemu dokumentu alebo sa zorientovať v ďalšom postupe.
- Tón: ľudský, prístupný, pokojný a dôveryhodný.
- Formát: 9:16, MP4/H.264, minimálne 720p, 30 fps.
- Hlavný text: `Základná právna orientácia a pomoc s dokumentmi pre každého. Začnite bezplatne.`
- Branding: presné schválené logo JurisDigta a `www.jurisdigta.eu` musia byť čitateľné v bezpečnej zóne.
- Záver: samostatná približne 2,5-sekundová karta s veľkým logom a URL viditeľnými až do posledného snímku.
- Hudba: pokojná inštrumentálna hudba bez vokálov, iba s preukázateľnou komerčnou licenciou pre web, YouTube a Instagram.
- Upozornenie: `AI pomoc nenahrádza právne poradenstvo. Dôležité kroky overte s právnikom.`

## Generačné prompty

### 1. Nejasný právny dokument

```text
Create the opening shot of a vertical cinematic advertisement. A relatable Slovak adult sits at a wooden table in a bright modern Central European home, reading an official-looking legal letter. The person is initially confused and mildly worried. Natural breathing and subtle hand movement, slow gentle camera push-in, realistic facial expression and document handling. Human, accessible, trustworthy, premium photorealistic advertising. Navy and pale-blue accents. No readable text, no logo, no courtroom, no lawyer robes, no dramatic panic, no watermark.
```

### 2. Odfotenie alebo nahratie dokumentu

```text
Second shot of a vertical cinematic advertisement. The same relatable Slovak adult at the same wooden table uses a smartphone to photograph an official-looking legal document. Over-the-shoulder composition focused on natural hands, phone camera and paper. Calm deliberate movement, subtle camera slide, warm reassuring daylight, human and accessible premium advertising. Navy and pale-blue accents. The phone screen contains no readable text. No logo, no courtroom, no lawyer robes, no watermark.
```

### 3. Zrozumiteľný výsledok

```text
Third shot of a vertical cinematic advertisement. Close over-the-shoulder view of the same relatable Slovak adult calmly reading a clear legal-assistance summary on a smartphone at home. The interface is clean, friendly, navy and pale blue with simple cards and check marks, but absolutely no readable words. The expression changes from uncertainty to understanding. Natural hand movement, gentle camera push, warm daylight, human and trustworthy premium advertising. No logo, no courtroom, no lawyer robes, no watermark.
```

### 4. Pokojný záver

```text
Final lifestyle shot of a vertical cinematic advertisement. The same relatable Slovak adult sits comfortably at home with a cup of tea, legal papers neatly organized on the table and a smartphone beside them. The person looks calm, reassured and in control, with a natural small smile. Warm golden daylight, subtle slow pull-back, human and accessible premium advertising, navy and pale-blue accents. Leave clean negative space in platform-safe areas for the exact logo, website URL and call to action added later. No readable text, no generated logo, no courtroom, no lawyer robes, no watermark.
```

## Deterministický strih

1. Generované scény skladajte v CapCut; nenechajte generátor kresliť logo ani text.
2. Texty, schválené logo a URL pridajte ako samostatné vrstvy.
3. Poslednú kartu vytvorte z `corporate-web/assets/login-shield.png` alebo iného výslovne schváleného brandového zdroja. Logo nedeformujte ani neprekresľujte AI.
4. Na poslednej karte zobrazte logo centrálne a `www.jurisdigta.eu` priamo pod ním s vysokým kontrastom. Obe vrstvy musia končiť na poslednom snímku.
5. Export skontrolujte v rozhraní 9:16 aj v prehrávači corporate webu. Uchovajte názov skladby, autora, zdroj a dôkaz licencie.

## Ochrana údajov a ľudská kontrola

Používajte iba syntetických ľudí, dokumenty a rozhrania. Do Dreamina, CapCut ani iného externého nástroja nenahrávajte reálne zákaznícke dokumenty, prípady, účty alebo nahrávky. Pred publikovaním musí človek potvrdiť správnosť tvrdenia o bezplatnom začiatku, právne upozornenie, logo, pravopis, hudobnú licenciu a celkovú vhodnosť. Generované právne informácie nesmú byť prezentované ako právne poradenstvo alebo náhrada právnika.

## Reprodukovateľný náhľad

Predvolený príklad repozitára zostáva:

```bash
python examples/minimal_demo.py
```

Video na corporate webe overte príkazom:

```bash
cd corporate-web
python -m http.server 8000
```

