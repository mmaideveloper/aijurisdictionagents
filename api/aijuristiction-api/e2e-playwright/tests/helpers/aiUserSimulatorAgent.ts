export class AIUserSimulatorAgent {
  private readonly language: string;

  public constructor(language: string) {
    this.language = (language || 'en').toLowerCase();
  }

  public prepareRandomReply(): string {
    const templates = this.replyTemplatesForLanguage();
    return templates[Math.floor(Math.random() * templates.length)];
  }

  public prepareReplies(count: number): string[] {
    return Array.from({ length: count }, () => this.prepareRandomReply());
  }

  private replyTemplatesForLanguage(): string[] {
    if (this.language.startsWith('sk')) {
      return [
        'Môžete prosím upresniť, ktoré dokumenty potrebujete?',
        'Bolo to podpísané písomne a mám kópiu zmluvy.',
        'Potrebujem poradiť, aké sú moje ďalšie právne kroky.',
        'Môžem doplniť dátum podpisu a mená účastníkov.',
      ];
    }

    if (this.language.startsWith('de')) {
      return [
        'Können Sie bitte genauer erklären, welche Unterlagen relevant sind?',
        'Es wurde schriftlich unterzeichnet und ich habe eine Kopie des Vertrags.',
        'Ich möchte wissen, welche rechtlichen Schritte ich als Nächstes machen soll.',
        'Ich kann das Datum und die beteiligten Personen ergänzen.',
      ];
    }

    return [
      'Can you clarify which document details are most important?',
      'It was signed in writing and I have a copy of the agreement.',
      'Please advise me on the next legal step I should take.',
      'I can provide the signing date and participant names.',
    ];
  }
}
