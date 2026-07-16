import { Language } from "../data/translations";

type LegalSection = {
  heading: string;
  body: string;
  links?: Array<{
    label: string;
    href: string;
  }>;
};

type LegalDocument = {
  title: string;
  summary: string;
  sections: LegalSection[];
  lastUpdatedLabel: string;
  lastUpdated: string;
};

type LegalContentByLanguage = {
  footerLinks: {
    privacy: string;
    disclaimer: string;
    terms: string;
  };
  privacy: LegalDocument;
  disclaimer: LegalDocument;
  terms: LegalDocument;
};

export const legalContent: Record<Language, LegalContentByLanguage> = {
  en: {
    footerLinks: {
      privacy: "Privacy Policy",
      disclaimer: "Disclaimer",
      terms: "Terms of Service"
    },
    privacy: {
      title: "Privacy Notice",
      summary:
        "This notice explains how Jurisdigta AI lawyer processes personal and case-related data in the platform.",
      sections: [
        {
          heading: "Controller and privacy contact",
          body:
            "The controller is Esolutions SK s.r.o., Company ID (IČO) 46491261, Tax ID (DIČ) 2820020907, Partizánska 665/101, 059 18 Spišské Bystré, Slovakia. Privacy requests can be sent to info@jurisdigta.eu. No data protection officer has currently been appointed."
        },
        {
          heading: "Data we collect",
          body:
            "We process account and contact details, authentication and subscription data, case content, prompts, AI outputs, uploaded and generated documents, user approvals, and security and operational logs. Case files may contain third-party data, special-category data, or information about criminal convictions and offences; submit only data that is necessary and that you are entitled to use."
        },
        {
          heading: "Purposes and legal bases",
          body:
            "We use data to create and administer accounts, provide cases and requested AI-assisted functions, secure and support the service, prevent misuse, meet Slovak and EU legal obligations, and establish or defend legal claims. The legal bases are performance of a contract (GDPR Article 6(1)(b)), legal obligations (Article 6(1)(c)), and legitimate interests in service security, reliability, misuse prevention, and legal-claim protection (Article 6(1)(f)). Consent (Article 6(1)(a)) applies when you approve optional external AI processing. Special-category or criminal-offence data is processed only where an applicable GDPR and Slovak-law condition permits it, including where necessary for legal claims."
        },
        {
          heading: "AI models and user approval",
          body:
            "Local Ollama models are the default and process case content within Jurisdigta-controlled infrastructure. Microsoft Azure AI Foundry in an EU data region is used only after your explicit approval for the relevant external processing. You may refuse or withdraw that approval for future external processing without losing the local route. AI outputs are drafts and require human review."
        },
        {
          heading: "Recipients and transfers",
          body:
            "We do not sell personal data. Access is limited to authorized personnel and processors supporting hosting, communications, security, accounting, and service operation. Microsoft receives approved content only when the external Azure AI Foundry route is selected. Processing is configured for the EU data region and no transfer outside the EEA is intended. If that changes, we will identify the transfer and applicable GDPR safeguard before it begins."
        },
        {
          heading: "Retention and deletion",
          body:
            "Retention follows the purpose of each category and applicable Slovak law. Account data is kept while the account is active and as needed to close it. Case content, uploads, prompts, and outputs are kept while the case or account requires them and longer only where a legal obligation or legal claim justifies it. Security logs and approval records are kept only for the period needed to secure the service and demonstrate compliance. Accounting documents are kept for the statutory period, generally ten years following the relevant accounting year under Act No. 431/2002 Coll. You may request deletion through the privacy contact; legal exceptions will be explained in the response."
        },
        {
          heading: "Security and data minimization",
          body:
            "We use access controls, authentication, restricted administration, privacy-minimized logging, and technical and organizational safeguards appropriate to the risk. Users should avoid including unrelated personal data in case files. No internet or AI service can be guaranteed completely secure."
        },
        {
          heading: "Your rights",
          body:
            "Subject to legal conditions, you may request access, rectification, erasure, restriction, portability, or object to processing based on legitimate interests. Where processing relies on consent, you may withdraw it at any time for future processing without affecting earlier lawful processing. Send requests to info@jurisdigta.eu; we may verify your identity before releasing or changing data.",
          links: [{ label: "Email the privacy contact", href: "mailto:info@jurisdigta.eu" }]
        },
        {
          heading: "Complaints",
          body:
            "If you believe your data has been processed unlawfully, you may contact us first or lodge a complaint with the Personal Data Protection Office of the Slovak Republic, Galvaniho 7/B, 821 04 Bratislava, Slovakia.",
          links: [
            { label: "Slovak Data Protection Office", href: "https://dataprotection.gov.sk/en/contact/" }
          ]
        },
        {
          heading: "Required data and consequences",
          body:
            "Account and case data marked as required is contractually necessary to register, authenticate, and provide the requested service. Without it, we may be unable to open an account, process a case, or provide the selected function. Optional external-AI approval is not required for the local model route."
        },
        {
          heading: "Automated decisions and human oversight",
          body:
            "Jurisdigta does not make approvals or legal decisions based solely on automated processing and does not use profiling that produces legal or similarly significant effects. AI-generated legal-risk outputs remain drafts for human review; users retain responsibility for deciding whether and how to use them."
        }
      ],
      lastUpdatedLabel: "Last Updated",
      lastUpdated: "July 15, 2026"
    },
    disclaimer: {
      title: "Disclaimer",
      summary:
        "AIJurisdiction provides AI-generated legal information for support purposes and not as a substitute for professional legal counsel.",
      sections: [
        {
          heading: "AI-Generated Information",
          body:
            "Outputs are generated by AI models and may contain inaccuracies, omissions, or outdated legal interpretations."
        },
        {
          heading: "No Legal Advice",
          body:
            "Content is informational only and does not constitute legal advice for any specific matter."
        },
        {
          heading: "No Attorney-Client Relationship",
          body:
            "Using this platform does not create an attorney-client relationship between you and AIJurisdiction or its operators."
        },
        {
          heading: "Limitation of Liability",
          body:
            "To the fullest extent permitted by law, AIJurisdiction is not liable for losses or damages arising from reliance on platform outputs."
        },
        {
          heading: "No Warranty",
          body:
            "The service and all generated content are provided on an \"as is\" and \"as available\" basis without warranties."
        },
        {
          heading: "Jurisdictional Applicability",
          body:
            "Legal relevance varies by country and region. Users must confirm local applicability with qualified legal professionals."
        },
        {
          heading: "User Responsibility",
          body:
            "You are solely responsible for decisions, filings, and actions taken based on or influenced by platform content."
        },
        {
          heading: "External Resources",
          body:
            "References to external laws, links, or sources are provided for convenience and may change without notice."
        },
        {
          heading: "Right to Modify",
          body:
            "We may update this disclaimer and platform behavior at any time. Continued use indicates acceptance of updates."
        }
      ],
      lastUpdatedLabel: "Last Updated",
      lastUpdated: "February 18, 2026"
    },
    terms: {
      title: "Terms of Service",
      summary:
        "These terms govern your use of AIJurisdiction services, interfaces, and generated outputs.",
      sections: [
        {
          heading: "Acceptance of Terms",
          body:
            "By accessing or using AIJurisdiction, you agree to comply with these terms and all applicable laws."
        },
        {
          heading: "Permitted Use",
          body:
            "You may use the service only for lawful purposes and must not submit content that violates rights, laws, or contractual duties."
        },
        {
          heading: "Account and Access",
          body:
            "You are responsible for maintaining account confidentiality and for all activities performed under your credentials."
        },
        {
          heading: "Intellectual Property",
          body:
            "Platform software, branding, and underlying systems remain the property of AIJurisdiction and its licensors."
        },
        {
          heading: "Service Changes",
          body:
            "We may update, suspend, or discontinue features at any time, including changes required by legal or security obligations."
        }
      ],
      lastUpdatedLabel: "Last Updated",
      lastUpdated: "February 18, 2026"
    }
  },
  sk: {
    footerLinks: {
      privacy: "Ochrana súkromia",
      disclaimer: "Upozornenie",
      terms: "Podmienky sluzby"
    },
    privacy: {
      title: "Ochrana súkromia",
      summary:
        "Tieto pravidlá vysvetľujú, ako Jurisdigta AI právnik spracúva osobné a prípadové údaje v platforme.",
      sections: [
        {
          heading: "Prevádzkovateľ a kontakt pre ochranu súkromia",
          body:
            "Prevádzkovateľom je Esolutions SK s.r.o., IČO 46491261, DIČ 2820020907, Partizánska 665/101, 059 18 Spišské Bystré, Slovenská republika. Žiadosti týkajúce sa ochrany osobných údajov posielajte na info@jurisdigta.eu. Zodpovedná osoba zatiaľ nebola určená."
        },
        {
          heading: "Aké údaje zbierame",
          body:
            "Spracúvame údaje o účte a kontaktné údaje, autentifikačné a predplatiteľské údaje, obsah prípadov, zadania, výstupy AI, nahrané a vytvorené dokumenty, súhlasy používateľa a bezpečnostné a prevádzkové záznamy. Prípadové spisy môžu obsahovať údaje tretích osôb, osobitné kategórie údajov alebo údaje o odsúdeniach a trestných činoch; uvádzajte len údaje, ktoré sú nevyhnutné a ktoré ste oprávnení použiť."
        },
        {
          heading: "Aké údaje používame",
          body:
            "Údaje používame na vytvorenie a správu účtu, poskytovanie prípadov a vyžiadaných funkcií podporovaných AI, zabezpečenie a podporu služby, predchádzanie zneužitiu, plnenie povinností podľa slovenského a európskeho práva a uplatňovanie alebo obhajovanie právnych nárokov. Právnym základom je plnenie zmluvy (čl. 6 ods. 1 písm. b) GDPR), zákonná povinnosť (písm. c)) a oprávnený záujem na bezpečnosti, spoľahlivosti, prevencii zneužitia a ochrane právnych nárokov (písm. f)). Súhlas (písm. a)) sa používa pri voliteľnom externom spracovaní AI. Osobitné kategórie údajov alebo údaje o trestných činoch spracúvame iba vtedy, keď to umožňuje GDPR a slovenské právo, najmä ak je to nevyhnutné na právne nároky."
        },
        {
          heading: "Modely AI a súhlas používateľa",
          body:
            "Predvolene používame lokálne modely Ollama, ktoré spracúvajú obsah prípadov v infraštruktúre kontrolovanej Jurisdigtou. Microsoft Azure AI Foundry v dátovej oblasti EÚ použijeme iba po vašom výslovnom súhlase s príslušným externým spracovaním. Súhlas môžete odmietnuť alebo odvolať pre budúce externé spracovanie bez straty lokálnej trasy. Výstupy AI sú návrhy a vyžadujú ľudskú kontrolu."
        },
        {
          heading: "Zdieľanie údajov",
          body:
            "Osobné údaje nepredávame. Prístup majú iba oprávnené osoby a sprostredkovatelia zabezpečujúci hosting, komunikáciu, bezpečnosť, účtovníctvo a prevádzku služby. Microsoft dostane schválený obsah iba pri výbere externej trasy Azure AI Foundry. Spracovanie je nastavené na dátovú oblasť EÚ a prenos mimo EHP sa neplánuje. Ak sa to zmení, pred prenosom uvedieme jeho rozsah a príslušnú záruku podľa GDPR."
        },
        {
          heading: "Uchovávanie a bezpečnosť",
          body:
            "Dobu uchovávania určujeme podľa účelu každej kategórie a platného slovenského práva. Údaje o účte uchovávame počas aktívneho účtu a na jeho uzavretie. Obsah prípadov, nahrané súbory, zadania a výstupy uchovávame, kým ich vyžaduje prípad alebo účet, a dlhšie iba vtedy, ak to odôvodňuje zákonná povinnosť alebo právny nárok. Bezpečnostné záznamy a doklady o súhlase uchovávame len na zabezpečenie služby a preukázanie súladu. Účtovné doklady uchovávame počas zákonnej lehoty, spravidla desať rokov nasledujúcich po príslušnom účtovnom roku podľa zákona č. 431/2002 Z. z. O vymazanie môžete požiadať cez kontakt pre ochranu súkromia; prípadné zákonné výnimky vysvetlíme v odpovedi. Používame primerané technické a organizačné bezpečnostné opatrenia a minimalizované záznamy."
        },
        {
          heading: "Vaše práva",
          body:
            "Za podmienok stanovených právnymi predpismi môžete požiadať o prístup, opravu, vymazanie, obmedzenie spracúvania a prenosnosť údajov alebo namietať proti spracúvaniu na základe oprávneného záujmu. Súhlas môžete kedykoľvek odvolať pre budúce spracovanie bez vplyvu na predchádzajúce zákonné spracovanie. Žiadosť pošlite na info@jurisdigta.eu; pred sprístupnením alebo zmenou údajov môžeme overiť vašu totožnosť.",
          links: [{ label: "Napísať kontaktu pre ochranu súkromia", href: "mailto:info@jurisdigta.eu" }]
        },
        {
          heading: "Sťažnosť dozornému orgánu",
          body:
            "Ak sa domnievate, že vaše údaje spracúvame nezákonne, môžete najprv kontaktovať nás alebo podať návrh na začatie konania na Úrad na ochranu osobných údajov Slovenskej republiky, Galvaniho 7/B, 821 04 Bratislava.",
          links: [
            { label: "Úrad na ochranu osobných údajov SR", href: "https://dataprotection.gov.sk/sk/kontakt/" }
          ]
        },
        {
          heading: "Povinné údaje a následky neposkytnutia",
          body:
            "Údaje o účte a prípade označené ako povinné sú zmluvne potrebné na registráciu, autentifikáciu a poskytnutie požadovanej služby. Bez nich nemusíme byť schopní vytvoriť účet, spracovať prípad alebo poskytnúť vybranú funkciu. Súhlas s externou AI nie je potrebný na použitie lokálneho modelu."
        },
        {
          heading: "Automatizované rozhodovanie a ľudský dohľad",
          body:
            "Jurisdigta nevykonáva schválenia ani právne rozhodnutia založené výlučne na automatizovanom spracúvaní a nepoužíva profilovanie s právnymi alebo podobne významnými účinkami. Výstupy AI s právnym rizikom zostávajú návrhmi na ľudskú kontrolu; používateľ rozhoduje, či a ako ich použije."
        }
      ],
      lastUpdatedLabel: "Posledná aktualizácia",
      lastUpdated: "15. júla 2026"
    },
    disclaimer: {
      title: "Upozornenie",
      summary:
        "AIJurisdiction poskytuje AI generovane pravne informacie len na podporne ucely, nie ako nahradu pravneho poradenstva.",
      sections: [
        {
          heading: "AI generovane informacie",
          body:
            "Vystupy su generovane AI modelmi a mozu obsahovat nepresnosti, vynechania alebo zastarane pravne vyklady."
        },
        {
          heading: "Nejde o pravne poradenstvo",
          body:
            "Obsah je iba informativny a nepredstavuje pravne poradenstvo pre konkretnu situaciu."
        },
        {
          heading: "Bez vztahu klient pravnik",
          body:
            "Pouzivanie platformy nevytvara vztah klient-pravnik medzi vami a AIJurisdiction alebo jeho prevadzkovatelmi."
        },
        {
          heading: "Obmedzenie zodpovednosti",
          body:
            "V maximalnom rozsahu povolenom zakonmi AIJurisdiction nezodpoveda za skody vzniknute spoliehanim sa na vystupy platformy."
        },
        {
          heading: "Bez zaruky",
          body:
            "Sluzba aj generovany obsah su poskytovane v stave \"ako su\" a \"podla dostupnosti\" bez zaruk."
        },
        {
          heading: "Jurisdikcna platnost",
          body:
            "Pravna relevantnost sa lisi podla krajiny a regionu. Pouzivatel musi platnost overit s kvalifikovanym pravnikom."
        },
        {
          heading: "Zodpovednost pouzivatela",
          body:
            "Za rozhodnutia, podania a kroky vykonane na zaklade obsahu platformy nesiete plnu zodpovednost vy."
        },
        {
          heading: "Externe zdroje",
          body:
            "Odkazy na externe predpisy alebo zdroje su orientacne a mozu sa menit bez predchadzajuceho upozornenia."
        },
        {
          heading: "Pravo na zmenu",
          body:
            "Toto upozornenie aj funkcionalitu platformy mozeme kedykolvek upravit. Dalsie pouzivanie znamena suhlas so zmenami."
        }
      ],
      lastUpdatedLabel: "Posledna aktualizacia",
      lastUpdated: "18. februar 2026"
    },
    terms: {
      title: "Podmienky sluzby",
      summary:
        "Tieto podmienky upravuju pouzivanie sluzieb, rozhrani a vystupov AIJurisdiction.",
      sections: [
        {
          heading: "Prijatie podmienok",
          body:
            "Pouzivanim AIJurisdiction suhlasite s tymito podmienkami a s platnymi pravnymi predpismi."
        },
        {
          heading: "Povolene pouzitie",
          body:
            "Sluzbu mozete pouzivat iba zakonny sposobom a nesmiete nahravat obsah, ktory porusuje prava alebo zmluvne povinnosti."
        },
        {
          heading: "Ucet a pristup",
          body:
            "Za bezpecnost prihlasovacich udajov a aktivity vykonane cez vas ucet zodpovedate vy."
        },
        {
          heading: "Dusevne vlastnictvo",
          body:
            "Softver, znacka a podkladove systemy platformy zostavaju majetkom AIJurisdiction a jeho licencnych partnerov."
        },
        {
          heading: "Zmeny sluzby",
          body:
            "Funkcie mozeme upravit, pozastavit alebo ukoncit, vratane zmien vyzadovanych pravnymi alebo bezpecnostnymi povinnostami."
        }
      ],
      lastUpdatedLabel: "Posledna aktualizacia",
      lastUpdated: "18. februar 2026"
    }
  },
  de: {
    footerLinks: {
      privacy: "Datenschutz",
      disclaimer: "Haftungsausschluss",
      terms: "Nutzungsbedingungen"
    },
    privacy: {
      title: "Datenschutzhinweise",
      summary:
        "Diese Hinweise erklären, wie Jurisdigta AI Anwalt personenbezogene und fallbezogene Daten auf der Plattform verarbeitet.",
      sections: [
        {
          heading: "Verantwortlicher und Datenschutzkontakt",
          body:
            "Verantwortlicher ist Esolutions SK s.r.o., Unternehmens-ID (IČO) 46491261, Steuer-ID (DIČ) 2820020907, Partizánska 665/101, 059 18 Spišské Bystré, Slowakei. Datenschutzanfragen richten Sie an info@jurisdigta.eu. Ein Datenschutzbeauftragter wurde derzeit nicht benannt."
        },
        {
          heading: "Welche Daten wir erfassen",
          body:
            "Wir verarbeiten Konto- und Kontaktdaten, Authentifizierungs- und Abonnementdaten, Fallinhalte, Eingaben, KI-Ausgaben, hochgeladene und erzeugte Dokumente, Nutzereinwilligungen sowie Sicherheits- und Betriebsprotokolle. Fallakten können Daten Dritter, besondere Datenkategorien oder Angaben zu strafrechtlichen Verurteilungen und Straftaten enthalten; übermitteln Sie nur erforderliche Daten, zu deren Verwendung Sie berechtigt sind."
        },
        {
          heading: "Zwecke und Rechtsgrundlagen",
          body:
            "Wir verwenden Daten zur Konto- und Fallverwaltung, für angeforderte KI-gestützte Funktionen, Sicherheit und Support, Missbrauchsprävention, gesetzliche Pflichten sowie zur Geltendmachung oder Verteidigung von Rechtsansprüchen. Rechtsgrundlagen sind Vertragserfüllung (Art. 6 Abs. 1 Buchst. b DSGVO), rechtliche Verpflichtungen (Buchst. c), berechtigte Interessen an Sicherheit, Zuverlässigkeit, Missbrauchsprävention und Rechtsschutz (Buchst. f) sowie Einwilligung (Buchst. a) für optionale externe KI-Verarbeitung. Besondere Datenkategorien oder Straftatendaten verarbeiten wir nur, wenn eine Bedingung der DSGVO und des slowakischen Rechts erfüllt ist, insbesondere soweit dies für Rechtsansprüche erforderlich ist."
        },
        {
          heading: "KI-Modelle und Einwilligung",
          body:
            "Standardmäßig verwenden wir lokale Ollama-Modelle in einer von Jurisdigta kontrollierten Infrastruktur. Microsoft Azure AI Foundry in einer EU-Datenregion wird nur nach Ihrer ausdrücklichen Einwilligung in die jeweilige externe Verarbeitung genutzt. Sie können diese für künftige externe Verarbeitung verweigern oder widerrufen, ohne die lokale Route zu verlieren. KI-Ausgaben sind Entwürfe und erfordern menschliche Prüfung."
        },
        {
          heading: "Empfänger und Übermittlungen",
          body:
            "Wir verkaufen keine personenbezogenen Daten. Zugriff erhalten nur befugte Personen und Auftragsverarbeiter für Hosting, Kommunikation, Sicherheit, Buchhaltung und Betrieb. Microsoft erhält genehmigte Inhalte nur bei Auswahl der externen Azure-AI-Foundry-Route. Die Verarbeitung ist für die EU-Datenregion konfiguriert; eine Übermittlung außerhalb des EWR ist nicht beabsichtigt. Sollte sich dies ändern, nennen wir vorab Umfang und DSGVO-Garantie."
        },
        {
          heading: "Speicherung und Sicherheit",
          body:
            "Die Speicherdauer richtet sich nach dem Zweck jeder Datenkategorie und dem anwendbaren slowakischen Recht. Kontodaten bleiben während des aktiven Kontos und seiner Abwicklung gespeichert. Fallinhalte, Uploads, Eingaben und Ausgaben bleiben erhalten, solange Fall oder Konto sie benötigen, und länger nur, wenn eine gesetzliche Pflicht oder ein Rechtsanspruch dies rechtfertigt. Sicherheitsprotokolle und Einwilligungsnachweise werden nur zur Absicherung und zum Compliance-Nachweis aufbewahrt. Buchungsunterlagen werden grundsätzlich zehn Jahre nach dem betreffenden Geschäftsjahr gemäß Gesetz Nr. 431/2002 Slg. aufbewahrt. Eine Löschung können Sie beim Datenschutzkontakt beantragen; gesetzliche Ausnahmen erläutern wir in der Antwort. Wir setzen angemessene technische und organisatorische Maßnahmen sowie minimierte Protokolle ein."
        },
        {
          heading: "Ihre Rechte",
          body:
            "Unter den gesetzlichen Voraussetzungen können Sie Auskunft, Berichtigung, Löschung, Einschränkung und Datenübertragbarkeit verlangen oder einer Verarbeitung aufgrund berechtigter Interessen widersprechen. Einwilligungen können Sie jederzeit für die Zukunft widerrufen, ohne die Rechtmäßigkeit früherer Verarbeitung zu berühren. Schreiben Sie an info@jurisdigta.eu; vor einer Datenfreigabe oder -änderung dürfen wir Ihre Identität prüfen.",
          links: [{ label: "Datenschutzkontakt anschreiben", href: "mailto:info@jurisdigta.eu" }]
        },
        {
          heading: "Beschwerde",
          body:
            "Wenn Sie eine rechtswidrige Verarbeitung vermuten, können Sie zunächst uns kontaktieren oder sich beim Amt für den Schutz personenbezogener Daten der Slowakischen Republik, Galvaniho 7/B, 821 04 Bratislava, beschweren.",
          links: [
            { label: "Slowakische Datenschutzbehörde", href: "https://dataprotection.gov.sk/en/contact/" }
          ]
        },
        {
          heading: "Erforderliche Daten und Folgen",
          body:
            "Als erforderlich gekennzeichnete Konto- und Falldaten werden vertraglich für Registrierung, Authentifizierung und die angeforderte Leistung benötigt. Ohne sie können wir möglicherweise kein Konto anlegen, keinen Fall bearbeiten oder die gewählte Funktion bereitstellen. Die Einwilligung in externe KI ist für die lokale Modellroute nicht erforderlich."
        },
        {
          heading: "Automatisierte Entscheidungen und menschliche Aufsicht",
          body:
            "Jurisdigta trifft keine Genehmigungen oder Rechtsentscheidungen ausschließlich automatisiert und verwendet kein Profiling mit rechtlicher oder ähnlich erheblicher Wirkung. Rechtlich riskante KI-Ausgaben bleiben Entwürfe zur menschlichen Prüfung; Nutzer entscheiden selbst, ob und wie sie diese verwenden."
        }
      ],
      lastUpdatedLabel: "Letzte Aktualisierung",
      lastUpdated: "15. Juli 2026"
    },
    disclaimer: {
      title: "Haftungsausschluss",
      summary:
        "AIJurisdiction stellt KI-generierte Rechtsinformationen zur Verfugung, jedoch keine individuelle Rechtsberatung.",
      sections: [
        {
          heading: "KI-generierte Inhalte",
          body:
            "Ausgaben werden durch KI-Modelle erzeugt und konnen unvollstandig, ungenau oder veraltet sein."
        },
        {
          heading: "Keine Rechtsberatung",
          body:
            "Alle Inhalte dienen nur der Information und ersetzen keine professionelle Rechtsberatung."
        },
        {
          heading: "Kein Mandatsverhaltnis",
          body:
            "Durch die Nutzung entsteht kein Mandats- oder Anwaltsverhaltnis mit AIJurisdiction oder den Betreibern."
        },
        {
          heading: "Haftungsbegrenzung",
          body:
            "Soweit gesetzlich zulassig, haftet AIJurisdiction nicht fur Schaden durch Vertrauen auf Plattformausgaben."
        },
        {
          heading: "Keine Gewahrleistung",
          body:
            "Der Dienst und alle Inhalte werden ohne Gewahr auf \"as is\"- und \"as available\"-Basis bereitgestellt."
        },
        {
          heading: "Jurisdiktionsbezug",
          body:
            "Die rechtliche Anwendbarkeit variiert je nach Land und Region und muss durch qualifizierte Juristen gepruft werden."
        },
        {
          heading: "Verantwortung der Nutzer",
          body:
            "Sie tragen die alleinige Verantwortung fur Entscheidungen und Handlungen auf Basis der Plattforminhalte."
        },
        {
          heading: "Externe Quellen",
          body:
            "Verweise auf externe Gesetze oder Links dienen nur der Orientierung und konnen sich ohne Mitteilung andern."
        },
        {
          heading: "Recht auf Anderung",
          body:
            "Wir konnen diesen Haftungsausschluss und Plattformfunktionen jederzeit andern. Weitere Nutzung gilt als Zustimmung."
        }
      ],
      lastUpdatedLabel: "Letzte Aktualisierung",
      lastUpdated: "18. Februar 2026"
    },
    terms: {
      title: "Nutzungsbedingungen",
      summary:
        "Diese Bedingungen regeln die Nutzung von AIJurisdiction, einschliesslich Oberflachen und erzeugter Inhalte.",
      sections: [
        {
          heading: "Annahme der Bedingungen",
          body:
            "Mit Zugriff auf AIJurisdiction stimmen Sie diesen Bedingungen sowie den anwendbaren Gesetzen zu."
        },
        {
          heading: "Zulassige Nutzung",
          body:
            "Die Plattform darf nur rechtmassig genutzt werden. Unzulassige oder rechtsverletzende Inhalte sind untersagt."
        },
        {
          heading: "Konto und Zugriff",
          body:
            "Sie sind fur die Vertraulichkeit Ihrer Zugangsdaten und fur alle Kontoaktivitaten verantwortlich."
        },
        {
          heading: "Geistiges Eigentum",
          body:
            "Software, Marke und zugrunde liegende Systeme verbleiben im Eigentum von AIJurisdiction und seinen Lizenzgebern."
        },
        {
          heading: "Anderungen am Dienst",
          body:
            "Wir konnen Funktionen jederzeit anpassen, aussetzen oder einstellen, auch zur Einhaltung rechtlicher oder sicherheitsbezogener Vorgaben."
        }
      ],
      lastUpdatedLabel: "Letzte Aktualisierung",
      lastUpdated: "18. Februar 2026"
    }
  }
};
