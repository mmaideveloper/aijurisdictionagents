import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:share_plus/share_plus.dart';
import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'package:url_launcher/url_launcher.dart';

import 'audio/jurisdicta_speaker.dart';
import 'auth/local_auth_store.dart';
import 'chat/speech_flow.dart';
import 'logging/app_logger.dart';
import 'platform/app_updater.dart';
import 'platform/file_saver.dart';
import 'update/github_release.dart';

const String _apiBaseUrlOverride = String.fromEnvironment(
  'AIJ_API_BASE_URL',
  defaultValue: '',
);
const String _apiKey = String.fromEnvironment(
  'AIJ_API_KEY',
  defaultValue: 'aijuris',
);
const String _defaultCountry = String.fromEnvironment(
  'AIJ_DEFAULT_COUNTRY',
  defaultValue: 'SK',
);
const String _defaultLanguage = String.fromEnvironment(
  'AIJ_DEFAULT_LANGUAGE',
  defaultValue: 'SK',
);
const String _fallbackLanguageCode = 'SK';
const String _localAutofillPhoneNumber = '+421944400166';
const String _githubOwner = String.fromEnvironment(
  'AIJ_GITHUB_OWNER',
  defaultValue: 'mmaideveloper',
);
const String _githubRepo = String.fromEnvironment(
  'AIJ_GITHUB_REPO',
  defaultValue: 'aijurisdictionagents',
);

const Map<String, String> _sessionExpiredMessagesByLanguage = <String, String>{
  'SK':
      'Relacia vyprsala. Vytvorili sme novu relaciu. Prosim, odoslite poslednu spravu znova.',
  'EN':
      'Your session expired. A new session was created. Please send your last message again.',
  'GE':
      'Ihre Sitzung ist abgelaufen. Eine neue Sitzung wurde erstellt. Bitte senden Sie Ihre letzte Nachricht erneut.',
};

String _normalizeLanguageCode(String languageCode) {
  final normalized = languageCode.trim().toUpperCase();
  if (normalized == 'DE') {
    return 'GE';
  }
  switch (normalized) {
    case 'SK':
    case 'EN':
    case 'GE':
      return normalized;
    default:
      return _fallbackLanguageCode;
  }
}

String _sessionExpiredMessageForLanguage(String languageCode) {
  final normalized = _normalizeLanguageCode(languageCode);
  return _sessionExpiredMessagesByLanguage[normalized] ??
      _sessionExpiredMessagesByLanguage[_fallbackLanguageCode]!;
}

String _defaultApiBaseUrl() {
  if (_apiBaseUrlOverride.trim().isNotEmpty) {
    return _apiBaseUrlOverride.trim();
  }
  if (kIsWeb) {
    return 'http://127.0.0.1:8080';
  }
  return 'http://10.0.2.2:8080';
}

final Random _correlationIdRandom = Random();
int _correlationIdCounter = 0;

String _generateRequestId() {
  final timestamp = DateTime.now()
      .toUtc()
      .millisecondsSinceEpoch
      .toRadixString(16)
      .padLeft(12, '0');
  final randomChunk = _correlationIdRandom
      .nextInt(0x7fffffff)
      .toRadixString(16)
      .padLeft(8, '0');
  _correlationIdCounter = (_correlationIdCounter + 1) % 0xffff;
  final counterChunk = _correlationIdCounter.toRadixString(16).padLeft(4, '0');
  return 'mbl-req-$timestamp-$randomChunk-$counterChunk';
}

String _generateFlowCorrelationId() {
  final timestamp = DateTime.now()
      .toUtc()
      .millisecondsSinceEpoch
      .toRadixString(16)
      .padLeft(12, '0');
  final randomChunk = _correlationIdRandom
      .nextInt(0x7fffffff)
      .toRadixString(16)
      .padLeft(8, '0');
  return 'mbl-flow-$timestamp-$randomChunk';
}

bool _isLocalApiBaseUrl(String apiBaseUrl) {
  final host = Uri.parse(apiBaseUrl).host.toLowerCase();
  return host == 'localhost' ||
      host == '127.0.0.1' ||
      host == '10.0.2.2' ||
      host == '0.0.0.0';
}

enum ResponderMode { aiUserSimulator, realPerson }

class LocaleOption {
  const LocaleOption({
    required this.countryCode,
    required this.languageCode,
    required this.label,
  });

  final String countryCode;
  final String languageCode;
  final String label;
}

const List<LocaleOption> _localeOptions = <LocaleOption>[
  LocaleOption(countryCode: 'SK', languageCode: 'SK', label: 'Slovakia (SK)'),
  LocaleOption(countryCode: 'CZ', languageCode: 'CS', label: 'Czechia (CS)'),
  LocaleOption(countryCode: 'DE', languageCode: 'DE', label: 'Germany (DE)'),
  LocaleOption(
      countryCode: 'US', languageCode: 'EN', label: 'United States (EN)'),
];

class AppStrings {
  AppStrings(String languageCode)
      : languageCode = _normalizeLanguageCode(languageCode);

  final String languageCode;

  static const Map<String, Map<String, String>> _localized =
      <String, Map<String, String>>{
    'SK': <String, String>{
      'auth_sign_in_tab': 'Prihlasenie',
      'auth_sign_up_tab': 'Registracia',
      'phone_number': 'Telefonne cislo',
      'phone_number_required': 'Telefonne cislo *',
      'phone_number_hint': _localAutofillPhoneNumber,
      'email': 'E-mail',
      'email_required': 'E-mail *',
      'password': 'Heslo',
      'password_required': 'Heslo *',
      'first_name': 'Meno',
      'first_name_optional': 'Meno (volitelne)',
      'last_name': 'Priezvisko',
      'last_name_optional': 'Priezvisko (volitelne)',
      'signing_in': 'Prihlasujem...',
      'login': 'Prihlasenie',
      'sign_in_by_phone': 'Prihlasit cez telefon',
      'sign_in_by_email_password': 'Prihlasit cez e-mail a heslo',
      'sign_in_failed': 'Prihlasenie zlyhalo: {{error}}',
      'phone_not_found':
          'Telefonne cislo sa nenaslo. Prihlaste sa e-mailom a heslom.',
      'invalid_email_password': 'Neplatny e-mail alebo heslo.',
      'signing_up': 'Registrujem...',
      'go_to_sign_up': 'Registracia',
      'create_account': 'Vytvorit ucet',
      'sign_up_failed': 'Registracia zlyhala: {{error}}',
      'account': 'Ucet',
      'sign_out': 'Odhlasit sa',
      'save_changes': 'Ulozit zmeny',
      'saving': 'Ukladam...',
      'update_sign_in_profile': 'Upravit prihlasovaci profil',
      'profile_update_failed': 'Aktualizacia profilu zlyhala: {{error}}',
      'debug_mode': 'Debug rezim',
      'debug_mode_description': 'V debug rezime sa vsetky logy ukladaju do suboru na Android zariadeni.',
      'debug_mode_enabled': 'Debug rezim zapnuty.',
      'debug_mode_disabled': 'Debug rezim vypnuty.',
      'share_logs': 'Zdielat logy',
      'logs_shared': 'Zdielanie logov bolo spustene.',
      'share_logs_failed': 'Zdielanie logov zlyhalo: {{error}}',
      'subscription': 'Predplatne',
      'subscription_change_requested':
          'Zmena predplatneho bola odoslana (pending).',
      'subscription_change_failed': 'Zmena predplatneho zlyhala: {{error}}',
      'subscription_status': 'Stav: {{status}}',
      'update_available': 'Dostupna aktualizacia',
      'update_body':
          'K dispozicii je nova verzia.\n\n{{current}} -> {{latest}}',
      'later': 'Neskor',
      'update': 'Aktualizovat',
      'invalid_release_url': 'Adresa aktualizacie je neplatna.',
      'could_not_open_update_page':
          'Stranku s aktualizaciou sa nepodarilo otvorit.',
      'update_apk_missing':
          'Release neobsahuje Android APK subor. Otvaram stranku release.',
      'update_download_started': 'Stahujem aktualizaciu {{latest}}...',
      'update_install_started':
          'Android instalator bol otvoreny. Potvrdte aktualizaciu.',
      'update_download_failed': 'Stahovanie aktualizacie zlyhalo: {{error}}',
      'update_install_failed':
          'Spustenie aktualizacie zlyhalo: {{error}}',
      'update_install_signature_mismatch':
          'Nainstalovana aplikacia ma iny podpis ako aktualizacia. Odinstalujte aktualnu aplikaciu a potom nainstalujte novu verziu.',
      'allow_install_unknown_apps':
          'V nastaveniach Androidu povolte instalacie z tejto aplikacie a vratte sa spat.',
      'speech_recognition_error': 'Chyba rozpoznavania reci: {{error}}',
      'speech_unavailable':
          'Rozpoznavanie reci na tomto zariadeni nie je dostupne.',
      'speech_input_toggle_label': 'Vstup hlasom',
      'speech_input_enabled': 'Vstup hlasom zapnuty',
      'speech_input_disabled': 'Vstup hlasom vypnuty',
      'speech_input_disabled_message':
          'Vstup hlasom je vypnuty. Zapnite ho tlacidlom Vstup hlasom.',
      'speaker_voice_label': 'Hlas asistenta',
      'speaker_voice_unavailable': 'Pre zvoleny jazyk nie je dostupny hlas.',
      'test_speaker_voice': 'Vyskusat hlas',
      'speaker_test_sample':
          'Dobry den, som Jurisdicta a toto je ukazka hlasu.',
      'no_camera_available': 'Na tomto zariadeni nie je dostupna kamera.',
      'document_added': 'Dokument bol pridany z kamery.',
      'create_or_select_case':
          'Pred odoslanim spravy vytvorte alebo vyberte pripad.',
      'failed_to_reach_api':
          'Nepodarilo sa spojit s API na adrese {{url}}: {{error}}',
      'failed_to_reach_api_with_correlation':
          'Nepodarilo sa spojit s API na adrese {{url}}: {{error}} (ID: {{id}})',
      'request_id_label': 'Correlation ID: {{id}}',
      'show_request_id': 'ID',
      'copy_request_id': 'Kopirovat correlation ID',
      'request_id_copied': 'Correlation ID bolo skopirovane: {{id}}',
      'pdf_not_ready':
          'PDF este nie je pripravene. Najprv dokoncite AI diskusiu.',
      'pdf_saved_to': 'PDF ulozene do {{path}}',
      'pdf_download_started': 'Stahovanie PDF spustene: {{filename}}',
      'pdf_download_failed': 'Stahovanie PDF zlyhalo: {{error}}',
      'open_saved_file_failed': 'Subor sa nepodarilo otvorit.',
      'failed_to_load_cases': 'Nepodarilo sa nacitat pripady: {{error}}',
      'failed_to_load_case_history':
          'Nepodarilo sa nacitat historiu pripadu: {{error}}',
      'maximum_cases':
          'Maximum je 5 pripadov. Najprv odstran existujuci pripad.',
      'create_case': 'Vytvorit pripad',
      'delete_case': 'Odstranit pripad',
      'case_name': 'Nazov pripadu',
      'cancel': 'Zrusit',
      'create': 'Vytvorit',
      'case_created': 'Pripad bol vytvoreny.',
      'rename_case': 'Premenovat pripad',
      'save': 'Ulozit',
      'rename_case_failed': 'Premenovanie pripadu zlyhalo: {{error}}',
      'case_deleted': 'Pripad bol odstraneny.',
      'delete_case_failed': 'Odstranenie pripadu zlyhalo: {{error}}',
      'select_case': 'Vyberte pripad',
      'case_history': 'Historia pripadu',
      'case_documents': 'Dokumenty pripadu',
      'show_next_5_messages': 'Zobrazit dalsich 5 sprav',
      'download_case_document': 'Stiahnut {{filename}}',
      'case_document_download_failed':
          'Stahovanie dokumentu zlyhalo: {{error}}',
      'attached_document': 'Prilozeny dokument: {{path}}',
      'clear': 'VYMAZAT',
      'you': 'Vy',
      'assistant': 'Asistent',
      'document_label': 'Dokument: {{path}}',
      'language_country': 'Jazyk a krajina',
      'local_mode': 'Lokalny rezim',
      'real_agent': 'Realny agent',
      'ai_user_simulator_agent': 'AI simulator pouzivatela',
      'summary_pdf': 'PDF zhrnutie',
      'document_pdf': 'PDF dokument',
      'export_documents': 'Dokumenty',
      'upload_documents': 'Nahrat dokumenty',
      'case_input_discussion': 'Popiste pripad pre spustenie diskusie...',
      'case_input_question': 'Polozte pravnu otazku...',
      'stop_speech_input': 'Zastavit hlasovy vstup',
      'speech_input': 'Pridat otazku alebo odpoved hlasom',
      'start_ai_discussion': 'Spustit AI diskusiu',
      'send_to_api': 'Odoslat do API',
      'capture_document': 'Zachytit dokument',
      'use_photo': 'Pouzit fotku',
      'camera_unavailable':
          'Kameru sa nepodarilo inicializovat. Skuste znova alebo pouzite ine zariadenie.',
      'camera_busy':
          'Kamera je obsadena alebo nedostupna. Zatvorte ine aplikacie a skuste znova.',
      'camera_access_denied':
          'Pristup ku kamere bol zamietnuty. Povolte kameru v prehliadaci a skuste znova.',
      'camera_error_with_reason':
          'Kameru sa nepodarilo inicializovat. {{reason}}',
      'camera_capture_failed':
          'Obrazok sa nepodarilo zachytit. Skuste znova alebo pouzite ine zariadenie.',
      'locale_SK': 'Slovensko (SK)',
      'locale_CZ': 'Cesko (CS)',
      'locale_DE': 'Nemecko (DE)',
      'locale_US': 'Spojene staty (EN)',
    },
    'EN': <String, String>{
      'auth_sign_in_tab': 'Sign in',
      'auth_sign_up_tab': 'Sign up',
      'phone_number': 'Phone number',
      'phone_number_required': 'Phone number *',
      'phone_number_hint': _localAutofillPhoneNumber,
      'email': 'Email',
      'email_required': 'Email *',
      'password': 'Password',
      'password_required': 'Password *',
      'first_name': 'First name',
      'first_name_optional': 'First name (optional)',
      'last_name': 'Last name',
      'last_name_optional': 'Last name (optional)',
      'signing_in': 'Signing in...',
      'login': 'Login',
      'sign_in_by_phone': 'Sign in by phone',
      'sign_in_by_email_password': 'Sign in by email/password',
      'sign_in_failed': 'Sign in failed: {{error}}',
      'phone_not_found':
          'Phone number not found. Sign in using email and password.',
      'invalid_email_password': 'Invalid email or password.',
      'signing_up': 'Signing up...',
      'go_to_sign_up': 'Sign up',
      'create_account': 'Create account',
      'sign_up_failed': 'Sign up failed: {{error}}',
      'account': 'Account',
      'sign_out': 'Sign out',
      'save_changes': 'Save changes',
      'saving': 'Saving...',
      'update_sign_in_profile': 'Update sign in profile',
      'profile_update_failed': 'Profile update failed: {{error}}',
      'debug_mode': 'Debug mode',
      'debug_mode_description': 'In debug mode, all logs are written to a file on Android.',
      'debug_mode_enabled': 'Debug mode enabled.',
      'debug_mode_disabled': 'Debug mode disabled.',
      'share_logs': 'Share logs',
      'logs_shared': 'Log sharing has started.',
      'share_logs_failed': 'Failed to share logs: {{error}}',
      'subscription': 'Subscription',
      'subscription_change_requested':
          'Subscription change requested (pending).',
      'subscription_change_failed': 'Failed to change subscription: {{error}}',
      'subscription_status': 'Status: {{status}}',
      'update_available': 'Update available',
      'update_body':
          'A newer version is available.\n\n{{current}} -> {{latest}}',
      'later': 'Later',
      'update': 'Update',
      'invalid_release_url': 'Release URL is invalid.',
      'could_not_open_update_page': 'Could not open update page.',
      'update_apk_missing':
          'This release does not include an Android APK. Opening the release page.',
      'update_download_started': 'Downloading update {{latest}}...',
      'update_install_started':
          'Android installer opened. Confirm the upgrade to continue.',
      'update_download_failed': 'Failed to download update: {{error}}',
      'update_install_failed': 'Failed to start update: {{error}}',
      'update_install_signature_mismatch':
          'The installed app signature differs from the update APK. Uninstall the current app, then install the new version.',
      'allow_install_unknown_apps':
          'Allow installs from this app in Android settings, then return to continue the update.',
      'speech_recognition_error': 'Speech recognition error: {{error}}',
      'speech_unavailable': 'Speech recognition is unavailable on this device.',
      'speech_input_toggle_label': 'Speech input',
      'speech_input_enabled': 'Speech input on',
      'speech_input_disabled': 'Speech input off',
      'speech_input_disabled_message':
          'Speech input is turned off. Use the Speech input button to enable it.',
      'speaker_voice_label': 'Assistant voice',
      'speaker_voice_unavailable':
          'No matching speaker voice is available for the selected language.',
      'test_speaker_voice': 'Test voice',
      'speaker_test_sample':
          'Hello, I am Jurisdicta and this is a sample of the selected voice.',
      'no_camera_available': 'No camera available on this device.',
      'document_added': 'Document added from camera.',
      'create_or_select_case':
          'Create or select a case before sending messages.',
      'failed_to_reach_api': 'Failed to reach API at {{url}}: {{error}}',
      'failed_to_reach_api_with_correlation':
          'Failed to reach API at {{url}}: {{error}} (ID: {{id}})',
      'request_id_label': 'Correlation ID: {{id}}',
      'show_request_id': 'ID',
      'copy_request_id': 'Copy ID',
      'request_id_copied': 'Correlation ID copied: {{id}}',
      'pdf_not_ready':
          'PDF is not ready yet. Complete the AI discussion first.',
      'pdf_saved_to': 'PDF saved to {{path}}',
      'pdf_download_started': 'PDF download started: {{filename}}',
      'pdf_download_failed': 'Failed to download PDF: {{error}}',
      'open_saved_file_failed': 'Could not open the saved file.',
      'failed_to_load_cases': 'Failed to load cases: {{error}}',
      'failed_to_load_case_history': 'Failed to load case history: {{error}}',
      'maximum_cases':
          'Maximum 5 cases allowed. Delete an existing case first.',
      'create_case': 'Create case',
      'delete_case': 'Delete case',
      'case_name': 'Case name',
      'cancel': 'Cancel',
      'create': 'Create',
      'case_created': 'Case created.',
      'rename_case': 'Rename case',
      'save': 'Save',
      'rename_case_failed': 'Failed to rename case: {{error}}',
      'case_deleted': 'Case deleted.',
      'delete_case_failed': 'Failed to delete case: {{error}}',
      'select_case': 'Select case',
      'case_history': 'Case history',
      'case_documents': 'Case documents',
      'show_next_5_messages': 'Show next 5 messages',
      'download_case_document': 'Download {{filename}}',
      'case_document_download_failed':
          'Failed to download case document: {{error}}',
      'attached_document': 'Attached document: {{path}}',
      'clear': 'CLEAR',
      'you': 'You',
      'assistant': 'Assistant',
      'document_label': 'Document: {{path}}',
      'language_country': 'Language & Country',
      'local_mode': 'Local mode',
      'real_agent': 'Real Agent',
      'ai_user_simulator_agent': 'AI User Simulator Agent',
      'summary_pdf': 'Summary PDF',
      'document_pdf': 'Document PDF',
      'export_documents': 'Documents',
      'upload_documents': 'Upload documents',
      'case_input_discussion': 'Describe the case to start discussion...',
      'case_input_question': 'Ask your legal question...',
      'stop_speech_input': 'Stop speech input',
      'speech_input': 'Add question/answer by speech',
      'start_ai_discussion': 'Start AI discussion',
      'send_to_api': 'Send to API',
      'capture_document': 'Capture document',
      'use_photo': 'Use photo',
      'camera_unavailable':
          'Could not initialize camera. Try again or use another device.',
      'camera_busy':
          'Camera is busy or unavailable. Close other apps using the camera and try again.',
      'camera_access_denied':
          'Camera access was denied. Allow camera permission in the browser and try again.',
      'camera_error_with_reason': 'Could not initialize camera. {{reason}}',
      'camera_capture_failed':
          'Could not capture the image. Try again or use another device.',
      'locale_SK': 'Slovakia (SK)',
      'locale_CZ': 'Czechia (CS)',
      'locale_DE': 'Germany (DE)',
      'locale_US': 'United States (EN)',
    },
    'GE': <String, String>{
      'auth_sign_in_tab': 'Anmelden',
      'auth_sign_up_tab': 'Registrieren',
      'phone_number': 'Telefonnummer',
      'phone_number_required': 'Telefonnummer *',
      'phone_number_hint': _localAutofillPhoneNumber,
      'email': 'E-Mail',
      'email_required': 'E-Mail *',
      'password': 'Passwort',
      'password_required': 'Passwort *',
      'first_name': 'Vorname',
      'first_name_optional': 'Vorname (optional)',
      'last_name': 'Nachname',
      'last_name_optional': 'Nachname (optional)',
      'signing_in': 'Anmeldung laeuft...',
      'login': 'Login',
      'sign_in_by_phone': 'Mit Telefonnummer anmelden',
      'sign_in_by_email_password': 'Mit E-Mail und Passwort anmelden',
      'sign_in_failed': 'Anmeldung fehlgeschlagen: {{error}}',
      'phone_not_found':
          'Telefonnummer nicht gefunden. Bitte mit E-Mail und Passwort anmelden.',
      'invalid_email_password': 'Ungueltige E-Mail oder falsches Passwort.',
      'signing_up': 'Registrierung laeuft...',
      'go_to_sign_up': 'Registrieren',
      'create_account': 'Konto erstellen',
      'sign_up_failed': 'Registrierung fehlgeschlagen: {{error}}',
      'account': 'Konto',
      'sign_out': 'Abmelden',
      'save_changes': 'Aenderungen speichern',
      'saving': 'Speichere...',
      'update_sign_in_profile': 'Anmeldeprofil aktualisieren',
      'profile_update_failed': 'Profilaktualisierung fehlgeschlagen: {{error}}',
      'debug_mode': 'Debug-Modus',
      'debug_mode_description': 'Im Debug-Modus werden alle Logs in eine Datei auf Android geschrieben.',
      'debug_mode_enabled': 'Debug-Modus aktiviert.',
      'debug_mode_disabled': 'Debug-Modus deaktiviert.',
      'share_logs': 'Logs teilen',
      'logs_shared': 'Log-Freigabe wurde gestartet.',
      'share_logs_failed': 'Logs konnten nicht geteilt werden: {{error}}',
      'subscription': 'Abonnement',
      'subscription_change_requested': 'Abo-Aenderung gesendet (pending).',
      'subscription_change_failed': 'Abo-Aenderung fehlgeschlagen: {{error}}',
      'subscription_status': 'Status: {{status}}',
      'update_available': 'Update verfuegbar',
      'update_body':
          'Eine neuere Version ist verfuegbar.\n\n{{current}} -> {{latest}}',
      'later': 'Spaeter',
      'update': 'Aktualisieren',
      'invalid_release_url': 'Release-URL ist ungueltig.',
      'could_not_open_update_page':
          'Update-Seite konnte nicht geoeffnet werden.',
      'update_apk_missing':
          'Dieses Release enthaelt keine Android-APK. Die Release-Seite wird geoeffnet.',
      'update_download_started': 'Update {{latest}} wird heruntergeladen...',
      'update_install_started':
          'Android-Installer wurde geoeffnet. Bestaetigen Sie das Update.',
      'update_download_failed':
          'Das Update konnte nicht heruntergeladen werden: {{error}}',
      'update_install_failed':
          'Das Update konnte nicht gestartet werden: {{error}}',
      'update_install_signature_mismatch':
          'Die Signatur der installierten App unterscheidet sich von der Update-APK. Deinstallieren Sie die aktuelle App und installieren Sie dann die neue Version.',
      'allow_install_unknown_apps':
          'Erlauben Sie Installationen aus dieser App in den Android-Einstellungen und kehren Sie dann zur App zurueck.',
      'speech_recognition_error': 'Fehler bei der Spracherkennung: {{error}}',
      'speech_unavailable':
          'Spracherkennung ist auf diesem Geraet nicht verfuegbar.',
      'speech_input_toggle_label': 'Spracheingabe',
      'speech_input_enabled': 'Spracheingabe an',
      'speech_input_disabled': 'Spracheingabe aus',
      'speech_input_disabled_message':
          'Spracheingabe ist ausgeschaltet. Aktivieren Sie sie mit der Schaltflaeche Spracheingabe.',
      'speaker_voice_label': 'Assistentenstimme',
      'speaker_voice_unavailable':
          'Fuer die gewaehlte Sprache ist keine passende Stimme verfuegbar.',
      'test_speaker_voice': 'Stimme testen',
      'speaker_test_sample':
          'Guten Tag, ich bin Jurisdicta und dies ist eine Sprachprobe.',
      'no_camera_available': 'Auf diesem Geraet ist keine Kamera verfuegbar.',
      'document_added': 'Dokument wurde von der Kamera hinzugefuegt.',
      'create_or_select_case':
          'Erstellen oder waehlen Sie zuerst einen Fall aus.',
      'failed_to_reach_api':
          'API unter {{url}} konnte nicht erreicht werden: {{error}}',
      'failed_to_reach_api_with_correlation':
          'API unter {{url}} konnte nicht erreicht werden: {{error}} (ID: {{id}})',
      'request_id_label': 'Correlation-ID: {{id}}',
      'show_request_id': 'ID',
      'copy_request_id': 'ID kopieren',
      'request_id_copied': 'Correlation-ID kopiert: {{id}}',
      'pdf_not_ready':
          'PDF ist noch nicht bereit. Schliessen Sie zuerst die AI-Diskussion ab.',
      'pdf_saved_to': 'PDF gespeichert unter {{path}}',
      'pdf_download_started': 'PDF-Download gestartet: {{filename}}',
      'pdf_download_failed': 'PDF-Download fehlgeschlagen: {{error}}',
      'open_saved_file_failed': 'Gespeicherte Datei konnte nicht geoeffnet werden.',
      'failed_to_load_cases': 'Faelle konnten nicht geladen werden: {{error}}',
      'failed_to_load_case_history':
          'Fallhistorie konnte nicht geladen werden: {{error}}',
      'maximum_cases':
          'Maximal 5 Faelle erlaubt. Loeschen Sie zuerst einen bestehenden Fall.',
      'create_case': 'Fall erstellen',
      'delete_case': 'Fall loeschen',
      'case_name': 'Fallname',
      'cancel': 'Abbrechen',
      'create': 'Erstellen',
      'case_created': 'Fall wurde erstellt.',
      'rename_case': 'Fall umbenennen',
      'save': 'Speichern',
      'rename_case_failed': 'Umbenennen des Falls fehlgeschlagen: {{error}}',
      'case_deleted': 'Fall wurde geloescht.',
      'delete_case_failed': 'Loeschen des Falls fehlgeschlagen: {{error}}',
      'select_case': 'Fall auswaehlen',
      'case_history': 'Fallhistorie',
      'case_documents': 'Falldokumente',
      'show_next_5_messages': 'Weitere 5 Nachrichten zeigen',
      'download_case_document': '{{filename}} herunterladen',
      'case_document_download_failed':
          'Download des Dokuments fehlgeschlagen: {{error}}',
      'attached_document': 'Angehaengtes Dokument: {{path}}',
      'clear': 'LOESCHEN',
      'you': 'Sie',
      'assistant': 'Assistent',
      'document_label': 'Dokument: {{path}}',
      'language_country': 'Sprache und Land',
      'local_mode': 'Lokaler Modus',
      'real_agent': 'Echter Agent',
      'ai_user_simulator_agent': 'AI-Benutzer-Simulator',
      'summary_pdf': 'PDF Zusammenfassung',
      'document_pdf': 'PDF Dokument',
      'export_documents': 'Dokumente',
      'upload_documents': 'Dokumente hochladen',
      'case_input_discussion':
          'Beschreiben Sie den Fall, um die Diskussion zu starten...',
      'case_input_question': 'Stellen Sie Ihre Rechtsfrage...',
      'stop_speech_input': 'Spracheingabe stoppen',
      'speech_input': 'Frage oder Antwort per Sprache hinzufuegen',
      'start_ai_discussion': 'AI-Diskussion starten',
      'send_to_api': 'An API senden',
      'capture_document': 'Dokument erfassen',
      'use_photo': 'Foto verwenden',
      'camera_unavailable':
          'Kamera konnte nicht initialisiert werden. Bitte erneut versuchen oder anderes Geraet verwenden.',
      'camera_busy':
          'Kamera ist belegt oder nicht verfuegbar. Schliessen Sie andere Apps und versuchen Sie es erneut.',
      'camera_access_denied':
          'Kamerazugriff wurde verweigert. Erlauben Sie den Zugriff im Browser und versuchen Sie es erneut.',
      'camera_error_with_reason':
          'Kamera konnte nicht initialisiert werden. {{reason}}',
      'camera_capture_failed':
          'Bild konnte nicht aufgenommen werden. Bitte erneut versuchen oder anderes Geraet verwenden.',
      'locale_SK': 'Slowakei (SK)',
      'locale_CZ': 'Tschechien (CS)',
      'locale_DE': 'Deutschland (DE)',
      'locale_US': 'Vereinigte Staaten (EN)',
    },
  };

  String t(String key,
      [Map<String, String> params = const <String, String>{}]) {
    final bundle =
        _localized[languageCode] ?? _localized[_fallbackLanguageCode]!;
    var value = bundle[key] ?? _localized[_fallbackLanguageCode]![key] ?? key;
    for (final entry in params.entries) {
      value = value.replaceAll('{{${entry.key}}}', entry.value);
    }
    return value;
  }

  String localeLabel(LocaleOption option) {
    return t('locale_${option.countryCode}');
  }
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final logger = await createAppLogger();
  final apiBaseUrl = _defaultApiBaseUrl();
  await logger.info(
    'Application startup',
    <String, Object?>{
      'api_base_url': apiBaseUrl,
      'is_web': kIsWeb,
      'log_file': logger.logFilePath,
    },
  );
  List<CameraDescription> cameras = <CameraDescription>[];
  try {
    cameras = await availableCameras();
    await logger.info(
      'Camera discovery completed',
      <String, Object?>{'camera_count': cameras.length},
    );
  } catch (error, stackTrace) {
    await logger.error(
      'Camera discovery failed',
      error,
      stackTrace,
    );
  }
  runApp(AIJurisdictionMobileApp(
      cameras: cameras, logger: logger, apiBaseUrl: apiBaseUrl));
}

Future<String> _readAppVersionLabel() async {
  final info = await PackageInfo.fromPlatform();
  final version = info.version.trim();
  final build = info.buildNumber.trim();
  return build.isEmpty ? 'v$version' : 'v$version+$build';
}

Future<void> _openSavedFile(
  BuildContext context,
  AppStrings strings,
  String savedPath,
) async {
  final fileUri = Uri.file(savedPath);
  try {
    final opened = await launchUrl(
      fileUri,
      mode: LaunchMode.externalApplication,
    );
    if (!opened && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(strings.t('open_saved_file_failed'))),
      );
    }
  } catch (_) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(strings.t('open_saved_file_failed'))),
      );
    }
  }
}

class AIJurisdictionMobileApp extends StatelessWidget {
  const AIJurisdictionMobileApp({
    super.key,
    required this.cameras,
    required this.logger,
    required this.apiBaseUrl,
  });

  final List<CameraDescription> cameras;
  final AppLogger logger;
  final String apiBaseUrl;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'AIJurisDigta',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo),
        useMaterial3: true,
      ),
      home: AuthGatePage(
        cameras: cameras,
        logger: logger,
        apiBaseUrl: apiBaseUrl,
      ),
    );
  }
}

class ChatMessage {
  const ChatMessage({
    required this.role,
    required this.content,
    this.agentName,
    this.documentPath,
    this.createdAt,
  });

  final String role;
  final String content;
  final String? agentName;
  final String? documentPath;
  final DateTime? createdAt;
}

String _displayContentForMessage(ChatMessage message) {
  return _sanitizeVisibleMessageContent(message.content);
}

String _sanitizeVisibleMessageContent(String content) {
  var visible = _stripCaseUpdateJson(content).trim();
  if (visible.isEmpty) {
    return '';
  }

  visible = _stripTrailingJsonPayload(visible).trim();
  if (visible.isEmpty) {
    return '';
  }

  visible = _stripJsonFenceBlocks(visible);
  if (visible.isEmpty) {
    return '';
  }

  visible = _stripAssistantAgentPrefixes(visible);
  if (visible.isEmpty) {
    return '';
  }

  final filteredLines = visible
      .split('\n')
      .where((line) => !_looksLikeTechnicalJsonLine(line))
      .toList();
  return filteredLines.join('\n').trim();
}

String _stripAssistantAgentPrefixes(String content) {
  var visible = content.trimLeft();
  final prefixPattern = RegExp(
    r'^(?:Lawyer[A-Za-z]+|Judge[A-Za-z]+|Jurisdicta)\s*:\s*',
  );
  while (true) {
    final match = prefixPattern.firstMatch(visible);
    if (match == null) {
      break;
    }
    visible = visible.substring(match.end).trimLeft();
  }
  return visible.trimRight();
}

String _stripCaseUpdateJson(String content) {
  final marker = RegExp(
    r'\*{0,2}\s*CASE_UPDATE_JSON\s*:?\s*\*{0,2}',
    caseSensitive: false,
  );
  final match = marker.firstMatch(content);
  if (match == null) {
    return content.trimRight();
  }
  final visible = content.substring(0, match.start).trimRight();
  return visible.isEmpty ? content.trimRight() : visible;
}

String _stripTrailingJsonPayload(String content) {
  final trimmed = content.trimRight();
  final candidateIndexes = <int>[];

  for (var index = 0; index < trimmed.length; index++) {
    final char = trimmed[index];
    if (char != '{' && char != '[') {
      continue;
    }
    if (index == 0) {
      candidateIndexes.add(index);
      continue;
    }
    final previous = trimmed[index - 1];
    if (previous == '\n' || previous == '\r') {
      candidateIndexes.add(index);
    }
  }

  for (final index in candidateIndexes) {
    final suffix = trimmed.substring(index).trim();
    if (!_isJsonPayload(suffix)) {
      continue;
    }
    final prefix = trimmed.substring(0, index).trimRight();
    return prefix;
  }

  return trimmed;
}

String _stripJsonFenceBlocks(String content) {
  final lines = content.split('\n');
  final kept = <String>[];
  var inJsonFence = false;

  for (final line in lines) {
    final trimmed = line.trim().toLowerCase();
    if (trimmed.startsWith('```json')) {
      inJsonFence = true;
      continue;
    }
    if (inJsonFence && trimmed == '```') {
      inJsonFence = false;
      continue;
    }
    if (!inJsonFence) {
      kept.add(line);
    }
  }

  return kept.join('\n').trim();
}

bool _looksLikeTechnicalJsonLine(String line) {
  final trimmed = line.trim();
  if (trimmed.isEmpty) {
    return false;
  }
  if (trimmed.toLowerCase().contains('case_update_json')) {
    return true;
  }
  if (trimmed == '{' ||
      trimmed == '}' ||
      trimmed == '[' ||
      trimmed == ']' ||
      trimmed == '},' ||
      trimmed == '],') {
    return true;
  }
  if (trimmed.startsWith('"') && trimmed.contains('":')) {
    return true;
  }
  if ((trimmed.startsWith('{') || trimmed.startsWith('[')) &&
      _isJsonPayload(trimmed)) {
    return true;
  }
  return false;
}

bool _isJsonPayload(String value) {
  try {
    final decoded = jsonDecode(value);
    return decoded is Map<String, dynamic> || decoded is List<dynamic>;
  } catch (_) {
    return false;
  }
}

class CaseSummary {
  const CaseSummary({
    required this.caseId,
    required this.title,
    required this.status,
  });

  final String caseId;
  final String title;
  final String status;

  static CaseSummary fromJson(Map<String, dynamic> json) {
    return CaseSummary(
      caseId: json['case_id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      status: json['status'] as String? ?? 'open',
    );
  }
}

class CaseHistoryMessage {
  const CaseHistoryMessage({
    required this.communicationId,
    required this.role,
    required this.content,
    required this.createdAt,
    this.agentName,
  });

  final String communicationId;
  final String role;
  final String content;
  final String createdAt;
  final String? agentName;

  static CaseHistoryMessage fromJson(Map<String, dynamic> json) {
    return CaseHistoryMessage(
      communicationId: json['communication_id'] as String? ?? '',
      role: json['role'] as String? ?? 'assistant',
      content: json['content'] as String? ?? '',
      createdAt: json['created_at'] as String? ?? '',
      agentName: json['agent_name'] as String?,
    );
  }

  ChatMessage toChatMessage() {
    return ChatMessage(
      role: role,
      content: content,
      agentName: agentName,
      createdAt: DateTime.tryParse(createdAt),
    );
  }
}

class CaseDocumentItem {
  const CaseDocumentItem({
    required this.docId,
    required this.kind,
    required this.version,
    required this.originalFilename,
    required this.createdAt,
  });

  final String docId;
  final String kind;
  final int version;
  final String originalFilename;
  final String createdAt;

  static CaseDocumentItem fromJson(Map<String, dynamic> json) {
    return CaseDocumentItem(
      docId: json['doc_id'] as String? ?? '',
      kind: json['kind'] as String? ?? '',
      version: json['version'] as int? ?? 0,
      originalFilename: json['original_filename'] as String? ?? 'document',
      createdAt: json['created_at'] as String? ?? '',
    );
  }
}

class CaseHistoryPage {
  const CaseHistoryPage({
    required this.messages,
    required this.documents,
    required this.hasMore,
  });

  final List<CaseHistoryMessage> messages;
  final List<CaseDocumentItem> documents;
  final bool hasMore;

  static CaseHistoryPage fromJson(Map<String, dynamic> json) {
    final rawMessages = json['messages'] as List<dynamic>? ?? const <dynamic>[];
    final rawDocuments =
        json['documents'] as List<dynamic>? ?? const <dynamic>[];
    return CaseHistoryPage(
      messages: rawMessages
          .whereType<Map>()
          .map((value) =>
              CaseHistoryMessage.fromJson(Map<String, dynamic>.from(value)))
          .toList(),
      documents: rawDocuments
          .whereType<Map>()
          .map((value) =>
              CaseDocumentItem.fromJson(Map<String, dynamic>.from(value)))
          .toList(),
      hasMore: json['has_more'] == true,
    );
  }
}

class StreamEvent {
  const StreamEvent({required this.event, required this.data});

  final String event;
  final Object? data;
}

class ExportFilePayload {
  const ExportFilePayload({
    required this.bytes,
    required this.filename,
    required this.contentType,
  });

  final Uint8List bytes;
  final String filename;
  final String contentType;
}

class SessionExpiredException implements Exception {
  const SessionExpiredException();

  @override
  String toString() => 'Session expired and was recreated.';
}

class ApiClient {
  ApiClient(
      {required this.baseUri, required this.apiKey, required this.logger});

  final Uri baseUri;
  final String apiKey;
  final AppLogger logger;
  String? _sessionId;
  String? _caseId;
  String? _userId;
  final String _flowCorrelationId = _generateFlowCorrelationId();
  String? _lastCorrelationId;

  String get flowCorrelationId => _flowCorrelationId;
  String? get lastCorrelationId => _lastCorrelationId;

  String? get sessionId => _sessionId;
  String? get caseId => _caseId;

  void setSignedInUser(String userId) {
    _userId = userId;
  }

  void setActiveCase(String? caseId) {
    _caseId = caseId;
    _sessionId = null;
    _lastCorrelationId = null;
  }

  Map<String, String> _headersForRequest(String requestId) => <String, String>{
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'x-correlation-id': _flowCorrelationId,
        'x-request-id': requestId,
      };

  Map<String, String> _headersForLog(String requestId) => <String, String>{
        'Content-Type': 'application/json',
        'x-api-key': '***',
        'x-correlation-id': _flowCorrelationId,
        'x-request-id': requestId,
      };

  void _recordCorrelationId(http.BaseResponse response) {
    _lastCorrelationId =
        response.headers['x-correlation-id'] ?? _flowCorrelationId;
  }

  Future<http.Response> _postJson({
    required String path,
    required Map<String, Object?> payload,
    required String action,
  }) async {
    final uri = baseUri.resolve(path);
    final requestId = _generateRequestId();
    final headers = _headersForRequest(requestId);
    await logger.info(
      'API request',
      <String, Object?>{
        'action': action,
        'method': 'POST',
        'url': uri.toString(),
        'headers': _headersForLog(requestId),
        'payload': payload,
      },
    );
    try {
      final response = await http.post(
        uri,
        headers: headers,
        body: jsonEncode(payload),
      );
      _recordCorrelationId(response);
      await logger.info(
        'API response',
        <String, Object?>{
          'action': action,
          'status_code': response.statusCode,
          'body': response.body,
          'correlation_id': _lastCorrelationId,
        },
      );
      return response;
    } catch (error, stackTrace) {
      await logger.error(
        'API request failed',
        error,
        stackTrace,
        <String, Object?>{
          'action': action,
          'url': uri.toString(),
          'correlation_id': _flowCorrelationId,
          'request_id': requestId,
        },
      );
      rethrow;
    }
  }

  Future<http.Response> _get({
    required String path,
    required String action,
  }) async {
    final uri = baseUri.resolve(path);
    final requestId = _generateRequestId();
    final headers = _headersForRequest(requestId);
    await logger.info(
      'API request',
      <String, Object?>{
        'action': action,
        'method': 'GET',
        'url': uri.toString(),
        'headers': _headersForLog(requestId),
      },
    );
    try {
      final response = await http.get(uri, headers: headers);
      _recordCorrelationId(response);
      await logger.info(
        'API response',
        <String, Object?>{
          'action': action,
          'status_code': response.statusCode,
          'content_type': response.headers['content-type'],
          'bytes': response.bodyBytes.length,
          'correlation_id': _lastCorrelationId,
        },
      );
      return response;
    } catch (error, stackTrace) {
      await logger.error(
        'API request failed',
        error,
        stackTrace,
        <String, Object?>{
          'action': action,
          'url': uri.toString(),
          'correlation_id': _flowCorrelationId,
          'request_id': requestId,
        },
      );
      rethrow;
    }
  }

  Future<List<CaseSummary>> listCases({required String userId}) async {
    final response = await _get(
      path: '/v1/cases?user_id=$userId',
      action: 'list_cases',
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('Case list failed with status ${response.statusCode}.');
    }
    final decoded = jsonDecode(response.body) as List<dynamic>;
    return decoded
        .whereType<Map>()
        .map((value) => CaseSummary.fromJson(Map<String, dynamic>.from(value)))
        .toList();
  }

  Future<CaseHistoryPage> loadCaseHistory({
    required String caseId,
    required String userId,
    int offset = 0,
    int limit = 5,
  }) async {
    final response = await _get(
      path:
          '/v1/cases/$caseId/history?user_id=$userId&offset=$offset&limit=$limit',
      action: 'case_history',
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception(
        'Case history failed with status ${response.statusCode}.',
      );
    }
    return CaseHistoryPage.fromJson(
      _decodeResponseBody(response, action: 'case_history'),
    );
  }

  Future<CaseSummary> createCase(
      {required String userId, required String title}) async {
    final response = await _postJson(
      path: '/v1/cases',
      action: 'create_case',
      payload: <String, Object?>{'user_id': userId, 'title': title},
    );
    if (response.statusCode == 409) {
      throw Exception('Maximum number of cases reached (5).');
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception(
          'Case creation failed with status ${response.statusCode}.');
    }
    return CaseSummary.fromJson(
        _decodeResponseBody(response, action: 'create_case'));
  }

  Future<CaseSummary> renameCase(
      {required String caseId,
      required String userId,
      required String title}) async {
    final uri = baseUri.resolve('/v1/cases/$caseId');
    final requestId = _generateRequestId();
    final response = await http.patch(
      uri,
      headers: _headersForRequest(requestId),
      body: jsonEncode(<String, Object?>{'user_id': userId, 'title': title}),
    );
    _recordCorrelationId(response);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('Case rename failed with status ${response.statusCode}.');
    }
    return CaseSummary.fromJson(
        _decodeResponseBody(response, action: 'rename_case'));
  }

  Future<void> deleteCase(
      {required String caseId, required String userId}) async {
    final uri = baseUri.resolve('/v1/cases/$caseId?user_id=$userId');
    final requestId = _generateRequestId();
    final response = await http.delete(
      uri,
      headers: <String, String>{
        'x-api-key': apiKey,
        'x-correlation-id': _flowCorrelationId,
        'x-request-id': requestId,
      },
    );
    _recordCorrelationId(response);
    if (response.statusCode != 204) {
      throw Exception('Case delete failed with status ${response.statusCode}.');
    }
    if (_caseId == caseId) {
      _caseId = null;
      _sessionId = null;
    }
  }

  Future<String> _createSession({
    required ResponderMode responderMode,
    required LocaleOption locale,
  }) async {
    final discussionType =
        responderMode == ResponderMode.realPerson ? 'court' : 'advice';
    final payload = <String, Object?>{
      'discussion_type': discussionType,
      'country': locale.countryCode,
      'language': locale.languageCode,
      'user_id': _userId,
      'case_id': _caseId,
    };
    final sessionResponse = await _postJson(
      path: '/v1/chat/sessions',
      action: 'create_session',
      payload: payload,
    );

    if (sessionResponse.statusCode < 200 || sessionResponse.statusCode >= 300) {
      await logger.info(
        'Session creation returned non-success status',
        <String, Object?>{
          'status_code': sessionResponse.statusCode,
          'body': sessionResponse.body,
        },
      );
      throw Exception(
        'Session creation failed with status ${sessionResponse.statusCode}.',
      );
    }

    final body = _decodeResponseBody(sessionResponse, action: 'create_session');
    final sessionId = body['id'] as String?;
    if (sessionId == null || sessionId.isEmpty) {
      throw Exception(
          'Session creation succeeded but no session id was returned.');
    }
    await logger.info(
      'Session created',
      <String, Object?>{
        'session_id': sessionId,
        'discussion_type': discussionType,
        'country': locale.countryCode,
        'language': locale.languageCode,
      },
    );
    return sessionId;
  }

  Future<String> _ensureSession({
    required ResponderMode responderMode,
    required LocaleOption locale,
  }) async {
    final existing = _sessionId;
    if (existing != null && existing.isNotEmpty) {
      await logger.info(
        'Reusing existing session',
        <String, Object?>{'session_id': existing},
      );
      return existing;
    }
    final created = await _createSession(
      responderMode: responderMode,
      locale: locale,
    );
    _sessionId = created;
    return created;
  }

  String _extractErrorDetailFromBody(String body) {
    final normalizedBody = body.trim();
    if (normalizedBody.isEmpty) {
      return body;
    }
    try {
      final decoded = jsonDecode(normalizedBody);
      if (decoded is Map<String, dynamic>) {
        final detail = decoded['detail'] as Object?;
        if (detail is String && detail.trim().isNotEmpty) {
          return detail.trim();
        }
      }
    } catch (_) {
      // Fall back to raw response body when JSON decoding fails.
    }
    return body;
  }

  String _extractErrorDetail(http.Response response) {
    return _extractErrorDetailFromBody(response.body);
  }

  bool _isMissingSessionDetail(String detail) {
    final normalized = detail.toLowerCase();
    return normalized.contains('session') && normalized.contains('not found');
  }

  bool _isMissingSessionResponse(http.Response response) {
    if (response.statusCode != 404) {
      return false;
    }
    final detail = _extractErrorDetail(response);
    return _isMissingSessionDetail(detail);
  }

  Future<String> _recreateSessionAfterMissing({
    required String operation,
    required String missingSessionId,
    required ResponderMode responderMode,
    required LocaleOption locale,
  }) async {
    await logger.info(
      'Missing session detected, recreating session',
      <String, Object?>{
        'operation': operation,
        'missing_session_id': missingSessionId,
      },
    );
    _sessionId = null;
    final recreated = await _ensureSession(
      responderMode: responderMode,
      locale: locale,
    );
    await logger.info(
      'Session recreated',
      <String, Object?>{
        'operation': operation,
        'recreated_session_id': recreated,
      },
    );
    return recreated;
  }

  Future<String> sendMessage({
    required String message,
    required ResponderMode responderMode,
    required LocaleOption locale,
    String? documentPath,
  }) async {
    final sessionId = await _ensureSession(
      responderMode: responderMode,
      locale: locale,
    );
    final content = documentPath == null
        ? message
        : '$message\n\n[Attached local document path: $documentPath]';
    final payload = <String, Object?>{'content': content};

    final response = await _postJson(
      path: '/v1/chat/sessions/$sessionId/reply',
      action: 'reply',
      payload: payload,
    );

    if (_isMissingSessionResponse(response)) {
      final retrySessionId = await _recreateSessionAfterMissing(
        operation: 'reply',
        missingSessionId: sessionId,
        responderMode: responderMode,
        locale: locale,
      );
      final retryResponse = await _postJson(
        path: '/v1/chat/sessions/$retrySessionId/reply',
        action: 'reply_retry',
        payload: payload,
      );
      if (_isMissingSessionResponse(retryResponse)) {
        await _recreateSessionAfterMissing(
          operation: 'reply_retry',
          missingSessionId: retrySessionId,
          responderMode: responderMode,
          locale: locale,
        );
        throw const SessionExpiredException();
      }
      return _parseReply(retryResponse, action: 'reply_retry');
    }

    return _parseReply(response, action: 'reply');
  }

  List<StreamEvent> _parseSseBlock(String block) {
    final lines = block
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .toList();
    if (lines.isEmpty) {
      return const [];
    }
    final eventLine = lines.firstWhere(
      (line) => line.startsWith('event:'),
      orElse: () => '',
    );
    final dataLine = lines.firstWhere(
      (line) => line.startsWith('data:'),
      orElse: () => '',
    );
    if (eventLine.isEmpty || dataLine.isEmpty) {
      return const [];
    }
    final event = eventLine.substring(6).trim();
    final rawData = dataLine.substring(5).trim();
    Object? data = rawData;
    try {
      data = jsonDecode(rawData);
    } catch (_) {
      data = rawData;
    }
    return <StreamEvent>[StreamEvent(event: event, data: data)];
  }

  Stream<StreamEvent> startDiscussionStream({
    required String instruction,
    required LocaleOption locale,
    required double questionTimeoutSeconds,
    required double maxDiscussionMinutes,
    required double communicationMinutes,
    String? documentPath,
  }) async* {
    _sessionId = null;
    final payload = <String, Object?>{
      'instruction': instruction,
      'documents': <Object?>[],
      'question_timeout_seconds': questionTimeoutSeconds,
      'max_discussion_minutes': maxDiscussionMinutes,
      'communication_minutes': communicationMinutes,
      'user_simulation_mode': 'AIUserSimulatorAgent',
    };
    if (documentPath != null && documentPath.trim().isNotEmpty) {
      await logger.info(
        'Discussion started with local document path context',
        <String, Object?>{'document_path': documentPath},
      );
    }

    for (var attempt = 0; attempt < 2; attempt++) {
      final sessionId = await _ensureSession(
        responderMode: ResponderMode.aiUserSimulator,
        locale: locale,
      );
      final path = '/v1/chat/sessions/$sessionId/stream';
      final uri = baseUri.resolve(path);
      final requestId = _generateRequestId();
      final request = http.Request('POST', uri)
        ..headers.addAll(_headersForRequest(requestId))
        ..body = jsonEncode(payload);
      await logger.info(
        'API stream request',
        <String, Object?>{
          'action': 'start_discussion_stream',
          'attempt': attempt + 1,
          'method': 'POST',
          'url': uri.toString(),
          'headers': _headersForLog(requestId),
          'payload': payload,
        },
      );

      final client = http.Client();
      try {
        final response = await client.send(request);
        _recordCorrelationId(response);
        if (response.statusCode < 200 || response.statusCode >= 300) {
          final body = await response.stream.bytesToString();
          final detail = _extractErrorDetailFromBody(body);
          await logger.info(
            'API stream response non-success',
            <String, Object?>{
              'attempt': attempt + 1,
              'status_code': response.statusCode,
              'detail': detail,
            },
          );
          if (response.statusCode == 404 && _isMissingSessionDetail(detail)) {
            await _recreateSessionAfterMissing(
              operation: 'start_discussion_stream',
              missingSessionId: sessionId,
              responderMode: ResponderMode.aiUserSimulator,
              locale: locale,
            );
            if (attempt == 0) {
              continue;
            }
            throw const SessionExpiredException();
          }
          throw Exception(
            'Discussion stream failed with status ${response.statusCode}: $detail',
          );
        }
        var buffer = '';
        await for (final chunk in response.stream.transform(utf8.decoder)) {
          buffer += chunk;
          final blocks = buffer.split('\n\n');
          buffer = blocks.removeLast();
          for (final block in blocks) {
            final events = _parseSseBlock(block);
            for (final event in events) {
              await logger.info(
                'API stream event',
                <String, Object?>{
                  'event': event.event,
                  'data': event.data,
                },
              );
              yield event;
            }
          }
        }
        if (buffer.trim().isNotEmpty) {
          final trailingEvents = _parseSseBlock(buffer);
          for (final event in trailingEvents) {
            await logger.info(
              'API stream trailing event',
              <String, Object?>{
                'event': event.event,
                'data': event.data,
              },
            );
            yield event;
          }
        }
        return;
      } catch (error, stackTrace) {
        await logger.error(
          'API stream request failed',
          error,
          stackTrace,
          <String, Object?>{
            'action': 'start_discussion_stream',
            'attempt': attempt + 1,
            'url': uri.toString(),
          },
        );
        rethrow;
      } finally {
        client.close();
      }
    }
  }

  Map<String, dynamic> _decodeResponseBody(
    http.Response response, {
    required String action,
  }) {
    try {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } catch (error, stackTrace) {
      unawaited(
        logger.error(
          'Failed to decode API response body',
          error,
          stackTrace,
          <String, Object?>{
            'action': action,
            'status_code': response.statusCode,
            'body': response.body,
          },
        ),
      );
      rethrow;
    }
  }

  String _parseReply(http.Response response, {required String action}) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = _extractErrorDetail(response);
      if (_isMissingSessionDetail(detail)) {
        throw const SessionExpiredException();
      }
      throw Exception(
        'API call failed with status ${response.statusCode}: $detail',
      );
    }

    final body = _decodeResponseBody(response, action: action);
    return body['content'] as String? ?? 'No response message.';
  }

  String _fallbackExportFilename({
    required String kind,
    required String sessionId,
  }) {
    final now = DateTime.now();
    final stamp =
        '${now.year.toString().padLeft(4, '0')}${now.month.toString().padLeft(2, '0')}${now.day.toString().padLeft(2, '0')}${now.hour.toString().padLeft(2, '0')}${now.minute.toString().padLeft(2, '0')}${now.second.toString().padLeft(2, '0')}';
    final docName =
        kind == 'document' ? 'final-document' : 'discussion-summary';
    return '$sessionId-$stamp-$docName.pdf';
  }

  String? _filenameFromContentDisposition(String? headerValue) {
    if (headerValue == null || headerValue.trim().isEmpty) {
      return null;
    }
    final match = RegExp(r'filename="([^"]+)"', caseSensitive: false)
        .firstMatch(headerValue);
    if (match == null) {
      return null;
    }
    final value = match.group(1)?.trim();
    if (value == null || value.isEmpty) {
      return null;
    }
    return value;
  }

  Future<ExportFilePayload> downloadExportPdf({
    required String kind,
    required ResponderMode responderMode,
    required LocaleOption locale,
  }) async {
    if (kind != 'summary' && kind != 'document') {
      throw Exception('Unsupported PDF export kind: $kind');
    }
    final sessionId = _sessionId;
    if (sessionId == null || sessionId.isEmpty) {
      throw Exception('No active session. Start a discussion first.');
    }
    final response = await _get(
      path: '/v1/chat/sessions/$sessionId/export?format=pdf&kind=$kind',
      action: 'export_pdf_$kind',
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = _extractErrorDetail(response);
      if (_isMissingSessionDetail(detail)) {
        await _recreateSessionAfterMissing(
          operation: 'export_pdf_$kind',
          missingSessionId: sessionId,
          responderMode: responderMode,
          locale: locale,
        );
        throw const SessionExpiredException();
      }
      throw Exception(
        'PDF export failed with status ${response.statusCode}: $detail',
      );
    }
    final filename = _filenameFromContentDisposition(
          response.headers['content-disposition'],
        ) ??
        _fallbackExportFilename(kind: kind, sessionId: sessionId);
    final contentType = response.headers['content-type'] ?? 'application/pdf';
    return ExportFilePayload(
      bytes: response.bodyBytes,
      filename: filename,
      contentType: contentType,
    );
  }

  Future<ExportFilePayload> downloadCaseDocument({
    required String caseId,
    required String userId,
    required String docId,
  }) async {
    final response = await _get(
      path: '/v1/cases/$caseId/documents/$docId?user_id=$userId',
      action: 'case_document_download',
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = _extractErrorDetail(response);
      throw Exception(
        'Case document download failed with status ${response.statusCode}: $detail',
      );
    }
    final filename = _filenameFromContentDisposition(
          response.headers['content-disposition'],
        ) ??
        'case-document';
    return ExportFilePayload(
      bytes: response.bodyBytes,
      filename: filename,
      contentType:
          response.headers['content-type'] ?? 'application/octet-stream',
    );
  }

  Future<bool> isDocumentExportReady() async {
    final sessionId = _sessionId;
    if (sessionId == null || sessionId.isEmpty) {
      return false;
    }
    final response = await _get(
      path: '/v1/chat/sessions/$sessionId/result',
      action: 'session_result',
    );
    if (response.statusCode == 404) {
      return false;
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = _extractErrorDetail(response);
      throw Exception(
        'Session result lookup failed with status ${response.statusCode}: $detail',
      );
    }
    final body = _decodeResponseBody(response, action: 'session_result');
    final metadata = body['metadata'];
    if (metadata is! Map) {
      return false;
    }
    return metadata['document_ready'] == true;
  }

  void resetSession() {
    unawaited(
      logger.info(
        'Session reset requested',
        <String, Object?>{'previous_session_id': _sessionId},
      ),
    );
    _sessionId = null;
    _lastCorrelationId = null;
  }
}

class AuthGatePage extends StatefulWidget {
  const AuthGatePage({
    super.key,
    required this.cameras,
    required this.logger,
    required this.apiBaseUrl,
  });

  final List<CameraDescription> cameras;
  final AppLogger logger;
  final String apiBaseUrl;

  @override
  State<AuthGatePage> createState() => _AuthGatePageState();
}

class _AuthGatePageState extends State<AuthGatePage> {
  late final LocalAuthStore _authStore;
  LocalAuthUser? _currentUser;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _authStore = LocalAuthStore(
      baseUri: Uri.parse(widget.apiBaseUrl),
      apiKey: _apiKey,
    );
    unawaited(_loadSession());
  }

  Future<void> _loadSession() async {
    final user = await _authStore.getCurrentUser();
    if (!mounted) {
      return;
    }
    setState(() {
      _currentUser = user;
      _loading = false;
    });
  }

  Future<void> _handleSignedIn(LocalAuthUser user) async {
    if (!mounted) {
      return;
    }
    setState(() {
      _currentUser = user;
    });
  }

  Future<void> _handleSignedOut() async {
    await _authStore.signOut();
    if (!mounted) {
      return;
    }
    setState(() {
      _currentUser = null;
    });
  }

  void _handleProfileUpdated(LocalAuthUser user) {
    if (!mounted) {
      return;
    }
    setState(() {
      _currentUser = user;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
    final user = _currentUser;
    if (user == null) {
      return AuthEntryPage(
        authStore: _authStore,
        logger: widget.logger,
        apiBaseUrl: widget.apiBaseUrl,
        onSignedIn: _handleSignedIn,
      );
    }
    return ChatHomePage(
      cameras: widget.cameras,
      logger: widget.logger,
      apiBaseUrl: widget.apiBaseUrl,
      signedInUser: user,
      authStore: _authStore,
      onSignedOut: _handleSignedOut,
      onProfileUpdated: _handleProfileUpdated,
    );
  }
}

class AuthEntryPage extends StatefulWidget {
  const AuthEntryPage({
    super.key,
    required this.authStore,
    required this.logger,
    required this.apiBaseUrl,
    required this.onSignedIn,
  });

  final LocalAuthStore authStore;
  final AppLogger logger;
  final String apiBaseUrl;
  final ValueChanged<LocalAuthUser> onSignedIn;

  @override
  State<AuthEntryPage> createState() => _AuthEntryPageState();
}

class _AuthEntryPageState extends State<AuthEntryPage>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;
  final TextEditingController _signInPhoneController = TextEditingController();
  final TextEditingController _signInEmailController = TextEditingController();
  final TextEditingController _signInPasswordController =
      TextEditingController();
  final TextEditingController _signUpPhoneController = TextEditingController();
  final TextEditingController _signUpEmailController = TextEditingController();
  final TextEditingController _signUpPasswordController =
      TextEditingController();
  final TextEditingController _signUpFirstNameController =
      TextEditingController();
  final TextEditingController _signUpLastNameController =
      TextEditingController();
  bool _showEmailPasswordFallback = false;
  bool _isBusy = false;
  String _appVersionLabel = 'v0.1.0+1';

  AppStrings get _strings => AppStrings(_defaultLanguage);
  bool get _isLocalExecution => _isLocalApiBaseUrl(widget.apiBaseUrl);

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _tabController.addListener(_handleTabChanged);
    unawaited(_loadRememberedPhoneNumber());
    unawaited(_loadAppVersion());
  }

  @override
  void dispose() {
    _tabController.removeListener(_handleTabChanged);
    _tabController.dispose();
    _signInPhoneController.dispose();
    _signInEmailController.dispose();
    _signInPasswordController.dispose();
    _signUpPhoneController.dispose();
    _signUpEmailController.dispose();
    _signUpPasswordController.dispose();
    _signUpFirstNameController.dispose();
    _signUpLastNameController.dispose();
    super.dispose();
  }

  void _handleTabChanged() {
    if (mounted) {
      setState(() {});
    }
  }

  void _showSnackbar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  Future<void> _loadRememberedPhoneNumber() async {
    final lastPhoneNumber = await widget.authStore.getLastPhoneNumber();
    if (!mounted) {
      return;
    }
    if (lastPhoneNumber != null && lastPhoneNumber.isNotEmpty) {
      _signInPhoneController.text = lastPhoneNumber;
      return;
    }
    if (_isLocalExecution) {
      _signInPhoneController.text = _localAutofillPhoneNumber;
    }
  }

  Future<void> _loadAppVersion() async {
    try {
      final label = await _readAppVersionLabel();
      if (!mounted) {
        return;
      }
      setState(() {
        _appVersionLabel = label;
      });
    } catch (_) {}
  }

  Future<void> _signInByPhone() async {
    if (_isBusy) {
      return;
    }
    setState(() {
      _isBusy = true;
    });
    try {
      final user = await widget.authStore.signInByPhone(
        _signInPhoneController.text,
      );
      if (user != null) {
        await widget.logger.info(
          'User signed in automatically by phone',
          <String, Object?>{'phone': user.phoneNumber},
        );
        widget.onSignedIn(user);
        return;
      }
      if (!mounted) {
        return;
      }
      setState(() {
        _showEmailPasswordFallback = true;
      });
      _showSnackbar(_strings.t('phone_not_found'));
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Sign-in by phone failed',
        error,
        stackTrace,
      );
      _showSnackbar(_strings.t('sign_in_failed', <String, String>{
        'error': '$error',
      }));
    } finally {
      if (mounted) {
        setState(() {
          _isBusy = false;
        });
      }
    }
  }

  Future<void> _signInByEmailPassword() async {
    if (_isBusy) {
      return;
    }
    setState(() {
      _isBusy = true;
    });
    try {
      final user = await widget.authStore.signInByEmailPassword(
        email: _signInEmailController.text,
        password: _signInPasswordController.text,
      );
      if (user == null) {
        _showSnackbar(_strings.t('invalid_email_password'));
        return;
      }
      await widget.logger.info(
        'User signed in by email/password',
        <String, Object?>{'phone': user.phoneNumber, 'email': user.email},
      );
      widget.onSignedIn(user);
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Sign-in by email/password failed',
        error,
        stackTrace,
      );
      _showSnackbar(_strings.t('sign_in_failed', <String, String>{
        'error': '$error',
      }));
    } finally {
      if (mounted) {
        setState(() {
          _isBusy = false;
        });
      }
    }
  }

  Future<void> _signUp() async {
    if (_isBusy) {
      return;
    }
    setState(() {
      _isBusy = true;
    });
    try {
      final user = await widget.authStore.signUp(
        SignUpInput(
          phoneNumber: _signUpPhoneController.text,
          email: _signUpEmailController.text,
          password: _signUpPasswordController.text,
          firstName: _signUpFirstNameController.text,
          lastName: _signUpLastNameController.text,
        ),
      );
      await widget.logger.info(
        'User signed up',
        <String, Object?>{'phone': user.phoneNumber, 'email': user.email},
      );
      widget.onSignedIn(user);
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Sign-up failed',
        error,
        stackTrace,
      );
      _showSnackbar(_strings.t('sign_up_failed', <String, String>{
        'error': '$error',
      }));
    } finally {
      if (mounted) {
        setState(() {
          _isBusy = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final strings = _strings;
    return Scaffold(
      body: Stack(
        children: [
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: <Color>[
                    const Color(0xFF041B59),
                    const Color(0xFF1388E9),
                    const Color(0xFF041B59),
                  ],
                ),
              ),
            ),
          ),
          SafeArea(
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 560),
                child: Card(
                  margin: const EdgeInsets.all(16),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Row(
                          children: [
                            const Expanded(
                              child: Text(
                                'AIJurisDigta',
                                style: TextStyle(
                                  fontSize: 20,
                                  fontWeight: FontWeight.w700,
                                  color: Color(0xFF0A2F6B),
                                ),
                              ),
                            ),
                            Text(
                              _appVersionLabel,
                              style: Theme.of(context)
                                  .textTheme
                                  .bodySmall
                                  ?.copyWith(color: const Color(0xFF4A628A)),
                            ),
                            const SizedBox(width: 12),
                            FilledButton.tonal(
                              onPressed: () {
                                final nextIndex =
                                    _tabController.index == 0 ? 1 : 0;
                                _tabController.animateTo(nextIndex);
                              },
                              child: Text(
                                _tabController.index == 0
                                    ? strings.t('go_to_sign_up')
                                    : strings.t('login'),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        TabBar(
                          controller: _tabController,
                          tabs: [
                            Tab(text: strings.t('auth_sign_in_tab')),
                            Tab(text: strings.t('auth_sign_up_tab')),
                          ],
                        ),
                        const SizedBox(height: 12),
                        SizedBox(
                          height: 420,
                          child: TabBarView(
                            controller: _tabController,
                            children: [
                              SingleChildScrollView(
                                child: Column(
                                  children: [
                                    TextField(
                                      controller: _signInPhoneController,
                                      keyboardType: TextInputType.phone,
                                      autofillHints: const <String>[
                                        AutofillHints.telephoneNumber,
                                        AutofillHints.username,
                                      ],
                                      decoration:
                                          const InputDecoration().copyWith(
                                        labelText: strings.t('phone_number'),
                                        hintText: _isLocalExecution
                                            ? strings.t('phone_number_hint')
                                            : null,
                                      ),
                                    ),
                                    const SizedBox(height: 12),
                                    SizedBox(
                                      width: double.infinity,
                                      child: FilledButton(
                                        onPressed:
                                            _isBusy ? null : _signInByPhone,
                                        child: Text(
                                          _isBusy
                                              ? strings.t('signing_in')
                                              : strings.t('sign_in_by_phone'),
                                        ),
                                      ),
                                    ),
                                    if (_showEmailPasswordFallback) ...[
                                      const SizedBox(height: 16),
                                      const Divider(),
                                      const SizedBox(height: 8),
                                      TextField(
                                        controller: _signInEmailController,
                                        keyboardType:
                                            TextInputType.emailAddress,
                                        autofillHints: const <String>[
                                          AutofillHints.email,
                                          AutofillHints.username,
                                        ],
                                        decoration: InputDecoration(
                                          labelText: strings.t('email'),
                                        ),
                                      ),
                                      const SizedBox(height: 12),
                                      TextField(
                                        controller: _signInPasswordController,
                                        obscureText: true,
                                        autofillHints: const <String>[
                                          AutofillHints.password,
                                        ],
                                        decoration: InputDecoration(
                                          labelText: strings.t('password'),
                                        ),
                                      ),
                                      const SizedBox(height: 12),
                                      SizedBox(
                                        width: double.infinity,
                                        child: OutlinedButton(
                                          onPressed: _isBusy
                                              ? null
                                              : _signInByEmailPassword,
                                          child: Text(
                                            strings
                                                .t('sign_in_by_email_password'),
                                          ),
                                        ),
                                      ),
                                    ],
                                  ],
                                ),
                              ),
                              SingleChildScrollView(
                                child: Column(
                                  children: [
                                    TextField(
                                      controller: _signUpPhoneController,
                                      keyboardType: TextInputType.phone,
                                      autofillHints: const <String>[
                                        AutofillHints.telephoneNumber,
                                      ],
                                      decoration: InputDecoration(
                                        labelText:
                                            strings.t('phone_number_required'),
                                      ),
                                    ),
                                    const SizedBox(height: 12),
                                    TextField(
                                      controller: _signUpEmailController,
                                      keyboardType: TextInputType.emailAddress,
                                      autofillHints: const <String>[
                                        AutofillHints.email,
                                        AutofillHints.newUsername,
                                      ],
                                      decoration: InputDecoration(
                                        labelText: strings.t('email_required'),
                                      ),
                                    ),
                                    const SizedBox(height: 12),
                                    TextField(
                                      controller: _signUpPasswordController,
                                      obscureText: true,
                                      autofillHints: const <String>[
                                        AutofillHints.newPassword,
                                      ],
                                      decoration: InputDecoration(
                                        labelText:
                                            strings.t('password_required'),
                                      ),
                                    ),
                                    const SizedBox(height: 12),
                                    TextField(
                                      controller: _signUpFirstNameController,
                                      decoration: InputDecoration(
                                        labelText:
                                            strings.t('first_name_optional'),
                                      ),
                                    ),
                                    const SizedBox(height: 12),
                                    TextField(
                                      controller: _signUpLastNameController,
                                      decoration: InputDecoration(
                                        labelText:
                                            strings.t('last_name_optional'),
                                      ),
                                    ),
                                    const SizedBox(height: 16),
                                    SizedBox(
                                      width: double.infinity,
                                      child: FilledButton(
                                        onPressed: _isBusy ? null : _signUp,
                                        child: Text(
                                          _isBusy
                                              ? strings.t('signing_up')
                                              : strings.t('create_account'),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class AccountSettingsPage extends StatefulWidget {
  const AccountSettingsPage({
    super.key,
    required this.user,
    required this.authStore,
    required this.selectedLocale,
    required this.locales,
    required this.speaker,
    required this.onLocaleChanged,
    required this.logger,
  });

  final LocalAuthUser user;
  final LocalAuthStore authStore;
  final LocaleOption selectedLocale;
  final List<LocaleOption> locales;
  final JurisdictaSpeaker speaker;
  final Future<void> Function(LocaleOption locale) onLocaleChanged;
  final AppLogger logger;

  @override
  State<AccountSettingsPage> createState() => _AccountSettingsPageState();
}

class _AccountSettingsPageState extends State<AccountSettingsPage> {
  late final TextEditingController _phoneController;
  late final TextEditingController _passwordController;
  late final TextEditingController _firstNameController;
  late final TextEditingController _lastNameController;
  late LocaleOption _selectedLocale;
  bool _isSaving = false;
  bool _isLoadingSubscriptions = false;
  bool _isUpdatingSubscription = false;
  bool _isLoadingSpeakerVoices = false;
  List<SubscriptionPlanInfo> _plans = <SubscriptionPlanInfo>[];
  List<UserSubscriptionInfo> _subscriptions = <UserSubscriptionInfo>[];
  List<JurisdictaSpeakerVoice> _speakerVoices = <JurisdictaSpeakerVoice>[];
  String? _selectedPlanCode;
  String? _selectedSpeakerVoiceId;
  late bool _debugModeEnabled;
  bool _isSharingLogs = false;

  AppStrings get _strings => AppStrings(_selectedLocale.languageCode);

  UserSubscriptionInfo? get _latestSubscription {
    if (_subscriptions.isEmpty) {
      return null;
    }
    return _subscriptions.first;
  }

  @override
  void initState() {
    super.initState();
    _phoneController = TextEditingController(text: widget.user.phoneNumber);
    _passwordController = TextEditingController(text: widget.user.password);
    _firstNameController =
        TextEditingController(text: widget.user.firstName ?? '');
    _lastNameController =
        TextEditingController(text: widget.user.lastName ?? '');
    _selectedLocale = widget.selectedLocale;
    _debugModeEnabled = widget.logger.debugModeEnabled;
    _loadSubscriptions();
    _loadSpeakerVoices();
  }

  Future<void> _loadSubscriptions() async {
    setState(() {
      _isLoadingSubscriptions = true;
    });
    try {
      final plans = await widget.authStore.listSubscriptionPlans();
      final subscriptions = await widget.authStore
          .listUserSubscriptions(userId: widget.user.userId);
      if (!mounted) {
        return;
      }
      setState(() {
        _plans = plans;
        _subscriptions = subscriptions;
        _selectedPlanCode = subscriptions.isNotEmpty
            ? subscriptions.first.planCode
            : (plans.isNotEmpty ? plans.first.planCode : null);
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _plans = <SubscriptionPlanInfo>[];
        _subscriptions = <UserSubscriptionInfo>[];
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoadingSubscriptions = false;
        });
      }
    }
  }

  Future<void> _requestSubscriptionChange() async {
    final selectedPlanCode = _selectedPlanCode;
    if (_isUpdatingSubscription ||
        selectedPlanCode == null ||
        selectedPlanCode.isEmpty) {
      return;
    }
    setState(() {
      _isUpdatingSubscription = true;
    });
    try {
      await widget.authStore.requestSubscriptionChange(
        userId: widget.user.userId,
        planCode: selectedPlanCode,
      );
      await _loadSubscriptions();
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_strings.t('subscription_change_requested'))),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_strings.t('subscription_change_failed',
              <String, String>{'error': '$error'})),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _isUpdatingSubscription = false;
        });
      }
    }
  }


  Future<void> _setDebugModeEnabled(bool enabled) async {
    setState(() {
      _debugModeEnabled = enabled;
    });
    await widget.logger.setDebugModeEnabled(enabled);
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          _strings.t(enabled ? 'debug_mode_enabled' : 'debug_mode_disabled'),
        ),
      ),
    );
  }

  Future<void> _shareLogs() async {
    final path = widget.logger.logFilePath;
    if (_isSharingLogs || path == null || path.isEmpty) {
      return;
    }
    setState(() {
      _isSharingLogs = true;
    });
    try {
      await Share.shareXFiles(
        <XFile>[XFile(path)],
        text: 'JurisDigtA debug log',
      );
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_strings.t('logs_shared'))),
      );
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Failed to share logs',
        error,
        stackTrace,
      );
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _strings.t('share_logs_failed', <String, String>{
              'error': '$error',
            }),
          ),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _isSharingLogs = false;
        });
      }
    }
  }

  Future<void> _loadSpeakerVoices() async {
    setState(() {
      _isLoadingSpeakerVoices = true;
    });
    try {
      final voices = await widget.speaker.listVoices(
        languageCode: _selectedLocale.languageCode,
      );
      final selectedVoiceId = widget.speaker.selectedVoiceIdFor(
        languageCode: _selectedLocale.languageCode,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _speakerVoices = voices;
        _selectedSpeakerVoiceId = selectedVoiceId;
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoadingSpeakerVoices = false;
        });
      }
    }
  }

  Future<void> _changeLocale(LocaleOption locale) async {
    if (_selectedLocale == locale) {
      return;
    }
    setState(() {
      _selectedLocale = locale;
      _speakerVoices = <JurisdictaSpeakerVoice>[];
      _selectedSpeakerVoiceId = null;
    });
    await widget.onLocaleChanged(locale);
    await _loadSpeakerVoices();
  }

  Future<void> _selectSpeakerVoice(String? voiceId) async {
    await widget.speaker.selectVoice(
      languageCode: _selectedLocale.languageCode,
      voiceId: voiceId,
    );
    if (!mounted) {
      return;
    }
    setState(() {
      _selectedSpeakerVoiceId = widget.speaker.selectedVoiceIdFor(
        languageCode: _selectedLocale.languageCode,
      );
    });
  }

  Future<void> _testSpeakerVoice() async {
    final spoke = await widget.speaker.speak(
      text: _strings.t('speaker_test_sample'),
      languageCode: _selectedLocale.languageCode,
    );
    if (!spoke && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_strings.t('speaker_voice_unavailable')),
        ),
      );
    }
  }

  @override
  void dispose() {
    _phoneController.dispose();
    _passwordController.dispose();
    _firstNameController.dispose();
    _lastNameController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_isSaving) {
      return;
    }
    setState(() {
      _isSaving = true;
    });
    try {
      final updated = await widget.authStore.updateUser(
        input: UpdateProfileInput(
          phoneNumber: _phoneController.text,
          password: _passwordController.text,
          firstName: _firstNameController.text,
          lastName: _lastNameController.text,
        ),
      );
      if (!mounted) {
        return;
      }
      Navigator.of(context).pop(updated);
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _strings.t('profile_update_failed', <String, String>{
              'error': '$error',
            }),
          ),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _isSaving = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final strings = _strings;
    return Scaffold(
      appBar: AppBar(title: Text(strings.t('update_sign_in_profile'))),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _phoneController,
            keyboardType: TextInputType.phone,
            decoration: InputDecoration(
              labelText: strings.t('phone_number_required'),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _passwordController,
            obscureText: true,
            decoration: InputDecoration(
              labelText: strings.t('password_required'),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _firstNameController,
            decoration: InputDecoration(
              labelText: strings.t('first_name'),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _lastNameController,
            decoration: InputDecoration(
              labelText: strings.t('last_name'),
            ),
          ),
          const SizedBox(height: 20),
          Text(
            strings.t('language_country'),
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          DropdownButtonFormField<LocaleOption>(
            value: _selectedLocale,
            isExpanded: true,
            onChanged: (locale) {
              if (locale == null) {
                return;
              }
              unawaited(_changeLocale(locale));
            },
            items: widget.locales
                .map(
                  (locale) => DropdownMenuItem<LocaleOption>(
                    value: locale,
                    child: Text(strings.localeLabel(locale)),
                  ),
                )
                .toList(growable: false),
          ),
          const SizedBox(height: 20),
          Text(
            strings.t('speaker_voice_label'),
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          if (_isLoadingSpeakerVoices)
            const LinearProgressIndicator()
          else
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    isExpanded: true,
                    value: _selectedSpeakerVoiceId,
                    hint: Text(strings.t('speaker_voice_unavailable')),
                    items: _speakerVoices
                        .map(
                          (voice) => DropdownMenuItem<String>(
                            value: voice.id,
                            child: Text('${voice.name} (${voice.locale})'),
                          ),
                        )
                        .toList(growable: false),
                    onChanged: _speakerVoices.isEmpty
                        ? null
                        : (value) => unawaited(_selectSpeakerVoice(value)),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton(
                  onPressed:
                      _speakerVoices.isEmpty ? null : () => unawaited(_testSpeakerVoice()),
                  icon: const Icon(Icons.play_arrow),
                  tooltip: strings.t('test_speaker_voice'),
                ),
              ],
            ),
          const SizedBox(height: 20),
          Text(
            strings.t('subscription'),
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          if (_isLoadingSubscriptions)
            const LinearProgressIndicator()
          else ...[
            DropdownButtonFormField<String>(
              value: _selectedPlanCode,
              items: _plans
                  .map((plan) => DropdownMenuItem<String>(
                        value: plan.planCode,
                        child: Text('${plan.displayName} (€${plan.priceEur})'),
                      ))
                  .toList(growable: false),
              onChanged: (value) {
                setState(() {
                  _selectedPlanCode = value;
                });
              },
            ),
            const SizedBox(height: 8),
            Text(
              strings.t('subscription_status', <String, String>{
                'status': _latestSubscription?.status ?? 'unknown',
              }),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed:
                  _isUpdatingSubscription ? null : _requestSubscriptionChange,
              child: Text(strings.t('subscription')),
            ),
          ],
          const SizedBox(height: 20),
          SwitchListTile(
            value: _debugModeEnabled,
            onChanged: _setDebugModeEnabled,
            title: Text(strings.t('debug_mode')),
            subtitle: Text(strings.t('debug_mode_description')),
          ),
          const SizedBox(height: 8),
          FilledButton.tonalIcon(
            onPressed: (_isSharingLogs || !_debugModeEnabled) ? null : _shareLogs,
            icon: _isSharingLogs
                ? const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.ios_share),
            label: Text(strings.t('share_logs')),
          ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _isSaving ? null : _save,
            child: Text(
              _isSaving ? strings.t('saving') : strings.t('save_changes'),
            ),
          ),
        ],
      ),
    );
  }
}

class ChatHomePage extends StatefulWidget {
  const ChatHomePage({
    super.key,
    required this.cameras,
    required this.logger,
    required this.apiBaseUrl,
    required this.signedInUser,
    required this.authStore,
    required this.onSignedOut,
    required this.onProfileUpdated,
  });

  final List<CameraDescription> cameras;
  final AppLogger logger;
  final String apiBaseUrl;
  final LocalAuthUser signedInUser;
  final LocalAuthStore authStore;
  final VoidCallback onSignedOut;
  final ValueChanged<LocalAuthUser> onProfileUpdated;

  @override
  State<ChatHomePage> createState() => _ChatHomePageState();
}

class _ChatHomePageState extends State<ChatHomePage>
    with WidgetsBindingObserver {
  static const double _questionTimeoutSeconds = 3600;
  static const double _maxDiscussionMinutes = 60;
  static const double _communicationMinutes = 60;

  final TextEditingController _inputController = TextEditingController();
  final SpeechToText _speechToText = SpeechToText();
  final ScrollController _messagesScrollController = ScrollController();

  late final ApiClient _apiClient;
  late final FileSaver _fileSaver;
  late final AppUpdater _appUpdater;
  late final JurisdictaSpeaker _speaker;
  late final List<ChatMessage> _messages;
  late ResponderMode _responderMode;
  late LocaleOption _selectedLocale;
  String? _documentPath;
  bool _isSending = false;
  bool _isDownloading = false;
  bool _hasExportReady = false;
  String _appVersionLabel = 'v0.1.0+1';
  bool _updateDialogShown = false;
  bool _isInstallingUpdate = false;
  bool _speechEnabled = false;
  bool _speechInputEnabled = true;
  bool _isListening = false;
  bool _awaitingSpokenName = false;
  bool _isSavingSpokenName = false;
  late LocalAuthUser _signedInUser;
  List<CaseSummary> _cases = <CaseSummary>[];
  CaseSummary? _selectedCase;
  bool _isLoadingCases = false;
  bool _isLoadingCaseHistory = false;
  bool _caseHistoryHasMore = false;
  int _caseHistoryOffset = 0;
  List<CaseDocumentItem> _caseDocuments = <CaseDocumentItem>[];
  final Set<String> _downloadingCaseDocumentIds = <String>{};
  String? _lastErrorCorrelationId;
  String? _pendingUpdateInstallPath;
  String? _pendingUpdateVersion;

  bool get _showLocalResponderSwitch {
    return _isLocalApiBaseUrl(widget.apiBaseUrl);
  }

  AppStrings get _strings => AppStrings(_selectedLocale.languageCode);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _signedInUser = widget.signedInUser;
    _selectedLocale = _localeOptions.firstWhere(
      (option) =>
          option.countryCode == _defaultCountry &&
          option.languageCode == _defaultLanguage,
      orElse: () => _localeOptions.first,
    );
    _responderMode = ResponderMode.realPerson;
    _apiClient = ApiClient(
      baseUri: Uri.parse(widget.apiBaseUrl),
      apiKey: _apiKey,
      logger: widget.logger,
    );
    _fileSaver = createFileSaver();
    _appUpdater = createAppUpdater();
    _speaker = createJurisdictaSpeaker();
    _apiClient.setSignedInUser(_signedInUser.userId);
    final welcomeLanguage =
        _normalizeLanguageCode(_selectedLocale.languageCode);
    _messages = <ChatMessage>[
      _buildWelcomeMessage(languageCode: welcomeLanguage),
    ];
    unawaited(
      widget.logger.info(
        'Initial welcome message added',
        <String, Object?>{'language': welcomeLanguage},
      ),
    );
    unawaited(
      widget.logger.info(
        'Chat home initialized',
        <String, Object?>{
          'api_base_url': widget.apiBaseUrl,
          'log_file': widget.logger.logFilePath,
          'language': welcomeLanguage,
        },
      ),
    );
    unawaited(_initializeSpeechRecognition());
    unawaited(_initializeAssistantSpeech());
    unawaited(_loadSpeakerVoices());
    unawaited(_loadCases());
    unawaited(_loadAppVersion());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scrollToLatest(animated: false);
    });
  }

  void _resetMessagesForCurrentCase() {
    _awaitingSpokenName = false;
    _messages
      ..clear()
      ..add(_buildWelcomeMessage());
  }

  @override
  void didUpdateWidget(covariant ChatHomePage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.signedInUser.phoneNumber != widget.signedInUser.phoneNumber ||
        oldWidget.signedInUser.email != widget.signedInUser.email ||
        oldWidget.signedInUser.firstName != widget.signedInUser.firstName ||
        oldWidget.signedInUser.lastName != widget.signedInUser.lastName) {
      setState(() {
        _signedInUser = widget.signedInUser;
        _updateWelcomeMessageForLocale();
      });
    }
  }

  Future<void> _loadAppVersion() async {
    try {
      final label = await _readAppVersionLabel();
      if (!mounted) {
        return;
      }
      final parsed = SemanticVersion.tryParse(label);
      setState(() {
        _appVersionLabel = label;
      });
      if (parsed != null) {
        unawaited(_checkForGithubUpdate(parsed));
      }
    } catch (_) {}
  }

  Future<void> _selectCase(CaseSummary? selected) async {
    if (!mounted) {
      return;
    }
    setState(() {
      _selectedCase = selected;
      _hasExportReady = false;
      _caseHistoryOffset = 0;
      _caseHistoryHasMore = false;
      _caseDocuments = <CaseDocumentItem>[];
      _apiClient.setActiveCase(selected?.caseId);
      _resetMessagesForCurrentCase();
    });
    if (selected == null) {
      return;
    }
    await _loadCaseHistory(reset: true);
  }

  Future<void> _loadCaseHistory({required bool reset}) async {
    final selected = _selectedCase;
    if (selected == null) {
      return;
    }
    final offset = reset ? 0 : _caseHistoryOffset;
    setState(() {
      _isLoadingCaseHistory = true;
    });
    try {
      final page = await _apiClient.loadCaseHistory(
        caseId: selected.caseId,
        userId: _signedInUser.userId,
        offset: offset,
        limit: 5,
      );
      if (!mounted || _selectedCase?.caseId != selected.caseId) {
        return;
      }
      final loadedMessages = page.messages.map((item) => item.toChatMessage());
      setState(() {
        _caseDocuments = page.documents;
        _caseHistoryHasMore = page.hasMore;
        _caseHistoryOffset = offset + loadedMessages.length;
        if (reset) {
          _messages.clear();
          if (loadedMessages.isEmpty) {
            _resetMessagesForCurrentCase();
          } else {
            _messages.addAll(loadedMessages);
          }
        } else if (loadedMessages.isNotEmpty) {
          _messages.insertAll(0, loadedMessages);
        }
      });
      _scrollToLatest(animated: false);
    } catch (error) {
      _showSnackbar(_strings.t('failed_to_load_case_history', <String, String>{
        'error': '$error',
      }));
    } finally {
      if (mounted) {
        setState(() {
          _isLoadingCaseHistory = false;
        });
      }
    }
  }

  Future<void> _downloadCaseDocument(CaseDocumentItem document) async {
    final selected = _selectedCase;
    if (selected == null) {
      return;
    }
    setState(() {
      _downloadingCaseDocumentIds.add(document.docId);
    });
    try {
      final payload = await _apiClient.downloadCaseDocument(
        caseId: selected.caseId,
        userId: _signedInUser.userId,
        docId: document.docId,
      );
      final savedPath = await _fileSaver.save(
        bytes: payload.bytes,
        fileName: payload.filename,
        contentType: payload.contentType,
      );
      if (savedPath != null && savedPath.isNotEmpty) {
        _showSnackbar(_strings.t('pdf_saved_to', <String, String>{
          'path': savedPath,
        }));
        await _openSavedFile(context, _strings, savedPath);
      } else {
        _showSnackbar(_strings.t('pdf_download_started', <String, String>{
          'filename': payload.filename,
        }));
      }
    } catch (error) {
      _showSnackbar(
        _strings.t('case_document_download_failed', <String, String>{
          'error': '$error',
        }),
      );
    } finally {
      if (mounted) {
        setState(() {
          _downloadingCaseDocumentIds.remove(document.docId);
        });
      }
    }
  }

  Uri _githubLatestReleaseUri() {
    return Uri.parse(
        'https://api.github.com/repos/$_githubOwner/$_githubRepo/releases/latest');
  }

  Future<void> _checkForGithubUpdate(SemanticVersion installed) async {
    try {
      final response = await http.get(
        _githubLatestReleaseUri(),
        headers: <String, String>{
          'Accept': 'application/vnd.github+json',
          'User-Agent': 'AIJurisDigta-Mobile',
        },
      );
      if (response.statusCode == 404) {
        await widget.logger.info(
          'No GitHub release found for update check',
          <String, Object?>{
            'owner': _githubOwner,
            'repo': _githubRepo,
          },
        );
        return;
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        await widget.logger.info(
          'GitHub update check failed',
          <String, Object?>{
            'status_code': response.statusCode,
            'body': response.body,
          },
        );
        return;
      }
      final payload = jsonDecode(response.body) as Map<String, dynamic>;
      if ((payload['draft'] as bool? ?? false) ||
          (payload['prerelease'] as bool? ?? false)) {
        return;
      }
      final releaseInfo = parseGithubReleaseInfo(payload);
      if (releaseInfo == null) {
        await widget.logger.info(
          'GitHub release tag is not parseable for app update',
          <String, Object?>{'tag_name': payload['tag_name']},
        );
        return;
      }
      final latestVersion = releaseInfo.version;
      if (latestVersion.compareTo(installed) <= 0) {
        await widget.logger.info(
          'App is already up to date',
          <String, Object?>{
            'installed': installed.toString(),
            'latest': latestVersion.toString(),
          },
        );
        return;
      }
      if (!mounted || _updateDialogShown) {
        return;
      }
      _updateDialogShown = true;
      await widget.logger.info(
        'New app version available on GitHub',
        <String, Object?>{
          'installed': installed.toString(),
          'latest': latestVersion.toString(),
          'release_url': releaseInfo.releaseUrl,
          'apk_download_url': releaseInfo.apkDownloadUrl,
        },
      );
      await _showUpdateDialog(
        installedVersion: installed.toString(),
        latestVersion: latestVersion.toString(),
        releaseUrl: releaseInfo.releaseUrl,
        apkDownloadUrl: releaseInfo.apkDownloadUrl,
      );
    } catch (error, stackTrace) {
      await widget.logger.error(
        'GitHub update check failed',
        error,
        stackTrace,
      );
    }
  }

  Future<void> _showUpdateDialog({
    required String installedVersion,
    required String latestVersion,
    required String releaseUrl,
    required String? apkDownloadUrl,
  }) async {
    if (!mounted) {
      return;
    }
    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: Text(_strings.t('update_available')),
          content: Text(
            _strings.t('update_body', <String, String>{
              'current': installedVersion,
              'latest': latestVersion,
            }),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: Text(_strings.t('later')),
            ),
            FilledButton(
              onPressed: () async {
                Navigator.of(dialogContext).pop();
                await _startAppUpgrade(
                  latestVersion: latestVersion,
                  releaseUrl: releaseUrl,
                  apkDownloadUrl: apkDownloadUrl,
                );
              },
              child: Text(_strings.t('update')),
            ),
          ],
        );
      },
    );
  }

  Future<void> _startAppUpgrade({
    required String latestVersion,
    required String releaseUrl,
    required String? apkDownloadUrl,
  }) async {
    if (_isInstallingUpdate) {
      return;
    }

    if (!_appUpdater.supportsInAppUpdate) {
      await _openReleasePage(releaseUrl);
      return;
    }

    if (apkDownloadUrl == null || apkDownloadUrl.trim().isEmpty) {
      _showSnackbar(_strings.t('update_apk_missing'));
      await _openReleasePage(releaseUrl);
      return;
    }

    final downloadUri = Uri.tryParse(apkDownloadUrl);
    if (downloadUri == null) {
      _showSnackbar(_strings.t('invalid_release_url'));
      await _openReleasePage(releaseUrl);
      return;
    }

    setState(() {
      _isInstallingUpdate = true;
    });
    try {
      _showSnackbar(
        _strings.t('update_download_started', <String, String>{
          'latest': latestVersion,
        }),
      );
      await widget.logger.info(
        'Starting in-app Android update download',
        <String, Object?>{
          'latest': latestVersion,
          'download_url': apkDownloadUrl,
        },
      );
      final filePath = await _appUpdater.downloadReleaseAsset(
        downloadUri: downloadUri,
        fileName: 'app-release-$latestVersion.apk',
      );
      _pendingUpdateInstallPath = filePath;
      _pendingUpdateVersion = latestVersion;
      await _attemptPendingUpdateInstall();
    } catch (error, stackTrace) {
      await widget.logger.error(
        'In-app Android update failed',
        error,
        stackTrace,
      );
      _showSnackbar(
        _strings.t('update_download_failed', <String, String>{
          'error': '$error',
        }),
      );
      await _openReleasePage(releaseUrl);
    } finally {
      if (mounted) {
        setState(() {
          _isInstallingUpdate = false;
        });
      } else {
        _isInstallingUpdate = false;
      }
    }
  }

  Future<void> _resumePendingUpdateInstall() async {
    try {
      final canInstall = await _appUpdater.canInstallPackages();
      if (canInstall) {
        await _attemptPendingUpdateInstall();
      }
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Failed to resume pending Android update install',
        error,
        stackTrace,
      );
    }
  }

  Future<void> _attemptPendingUpdateInstall() async {
    final filePath = _pendingUpdateInstallPath;
    if (filePath == null || filePath.isEmpty) {
      return;
    }

    try {
      final canInstall = await _appUpdater.canInstallPackages();
      if (!canInstall) {
        await widget.logger.info(
          'Install unknown apps permission required for Android update',
          <String, Object?>{
            'file_path': filePath,
            'latest': _pendingUpdateVersion,
          },
        );
        await _appUpdater.openInstallPermissionSettings();
        _showSnackbar(_strings.t('allow_install_unknown_apps'));
        return;
      }

      await _appUpdater.startInstall(filePath);
      await widget.logger.info(
        'Android installer opened for app upgrade',
        <String, Object?>{
          'file_path': filePath,
          'latest': _pendingUpdateVersion,
        },
      );
      _pendingUpdateInstallPath = null;
      _pendingUpdateVersion = null;
      _showSnackbar(_strings.t('update_install_started'));
    } on PlatformException catch (error, stackTrace) {
      if (error.code == 'signature_mismatch') {
        _showSnackbar(_strings.t('update_install_signature_mismatch'));
        return;
      }
      await widget.logger.error(
        'Failed to start Android update installer',
        error,
        stackTrace,
      );
      _showSnackbar(
        _strings.t('update_install_failed', <String, String>{
          'error': '$error',
        }),
      );
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Failed to start Android update installer',
        error,
        stackTrace,
      );
      _showSnackbar(
        _strings.t('update_install_failed', <String, String>{
          'error': '$error',
        }),
      );
    }
  }

  Future<void> _openReleasePage(String releaseUrl) async {
    final uri = Uri.tryParse(releaseUrl);
    if (uri == null) {
      _showSnackbar(_strings.t('invalid_release_url'));
      return;
    }
    final opened = await launchUrl(
      uri,
      mode: LaunchMode.platformDefault,
    );
    if (!opened) {
      _showSnackbar(_strings.t('could_not_open_update_page'));
    }
  }

  String _localeIdForSpeech(LocaleOption locale) {
    switch (locale.languageCode.toUpperCase()) {
      case 'SK':
        return 'sk_SK';
      case 'CS':
        return 'cs_CZ';
      case 'DE':
      case 'GE':
        return 'de_DE';
      case 'EN':
      default:
        return 'en_US';
    }
  }

  String? get _profileName => resolveStoredProfileName(
        firstName: _signedInUser.firstName,
        lastName: _signedInUser.lastName,
      );

  ChatMessage _buildWelcomeMessage({String? languageCode}) {
    return ChatMessage(
      role: 'assistant',
      content: speechWelcomeMessage(
        languageCode ?? _selectedLocale.languageCode,
        userName: _profileName,
      ),
      agentName: 'Jurisdicta',
    );
  }

  bool _isInitialWelcomeMessage(ChatMessage message) {
    return message.role == 'assistant' &&
        message.agentName == 'Jurisdicta' &&
        message.createdAt == null;
  }

  void _appendAssistantMessage(String content) {
    if (!mounted) {
      return;
    }
    setState(() {
      _messages.add(
        ChatMessage(
          role: 'assistant',
          content: content,
          agentName: 'Jurisdicta',
          createdAt: DateTime.now(),
        ),
      );
    });
    _scrollToLatest();
    unawaited(_speakAssistantMessage(content));
  }

  Future<void> _initializeSpeechRecognition() async {
    final enabled = await _speechToText.initialize(
      onError: _onSpeechError,
      onStatus: _onSpeechStatus,
    );
    if (!mounted) {
      return;
    }
    setState(() {
      _speechEnabled = enabled;
    });
    await widget.logger.info(
      'Speech recognition initialized',
      <String, Object?>{'enabled': enabled},
    );
  }

  Future<void> _initializeAssistantSpeech() async {
    final enabled = await _speaker.initialize();
    if (!enabled) {
      await widget.logger.info('Assistant speech output unavailable');
      return;
    }
    await widget.logger.info('Assistant speech output initialized');
    await _speakAssistantMessage(_messages.first.content);
  }

  Future<void> _loadSpeakerVoices() async {
    if (!mounted) {
      return;
    }
    final voices = await _speaker.listVoices(
      languageCode: _selectedLocale.languageCode,
    );
    final selectedVoiceId = _speaker.selectedVoiceIdFor(
      languageCode: _selectedLocale.languageCode,
    );
    if (!mounted) {
      return;
    }
    await widget.logger.info(
      'Speaker voices loaded',
      <String, Object?>{
        'language': _selectedLocale.languageCode,
        'voice_count': voices.length,
        'selected_voice_id': selectedVoiceId,
      },
    );
  }

  Future<void> _speakAssistantMessage(String content) async {
    final visibleContent = _sanitizeVisibleMessageContent(content);
    if (visibleContent.isEmpty) {
      return;
    }
    final spoke = await _speaker.speak(
      text: visibleContent,
      languageCode: _selectedLocale.languageCode,
    );
    if (!spoke) {
      await widget.logger.info(
        'Assistant speech output skipped',
        <String, Object?>{'message_length': visibleContent.length},
      );
    }
  }

  void _onSpeechResult(SpeechRecognitionResult result) {
    if (!mounted) {
      return;
    }
    setState(() {
      _inputController.text = result.recognizedWords;
      _inputController.selection = TextSelection.fromPosition(
        TextPosition(offset: _inputController.text.length),
      );
    });
    if (_awaitingSpokenName && result.finalResult) {
      unawaited(_storeSpokenName(result.recognizedWords));
    }
  }

  void _onSpeechStatus(String status) {
    if (!mounted) {
      return;
    }
    final isListening = status == 'listening';
    setState(() {
      _isListening = isListening;
    });
    unawaited(
      widget.logger.info(
        'Speech status changed',
        <String, Object?>{'status': status},
      ),
    );
  }

  void _onSpeechError(SpeechRecognitionError error) {
    if (!mounted) {
      return;
    }
    setState(() {
      _isListening = false;
    });
    _showSnackbar(_strings.t('speech_recognition_error', <String, String>{
      'error': error.errorMsg,
    }));
    unawaited(
      widget.logger.error(
        'Speech recognition error',
        Exception(error.errorMsg),
        StackTrace.current,
        <String, Object?>{'permanent': error.permanent},
      ),
    );
  }

  Future<void> _storeSpokenName(String spokenText) async {
    if (_isSavingSpokenName) {
      return;
    }
    final parsed = parseSpokenProfileName(spokenText);
    if (parsed == null) {
      final retryMessage = speechNameRetryMessage(_selectedLocale.languageCode);
      _showSnackbar(retryMessage);
      _appendAssistantMessage(retryMessage);
      return;
    }

    setState(() {
      _isSavingSpokenName = true;
    });
    try {
      final updated = await widget.authStore.updateUser(
        input: UpdateProfileInput(
          phoneNumber: _signedInUser.phoneNumber,
          password: _signedInUser.password,
          firstName: parsed.firstName,
          lastName: parsed.lastName,
        ),
      );
      if (!mounted) {
        return;
      }
      final savedName = resolveStoredProfileName(
            firstName: updated.firstName,
            lastName: updated.lastName,
          ) ??
          parsed.displayName;
      setState(() {
        _signedInUser = updated;
        _awaitingSpokenName = false;
        _inputController.clear();
        _updateWelcomeMessageForLocale();
      });
      widget.onProfileUpdated(updated);
      _appendAssistantMessage(
        speechNameSavedMessage(
          _selectedLocale.languageCode,
          userName: savedName,
        ),
      );
      await widget.logger.info(
        'Speech profile name stored',
        <String, Object?>{
          'user_id': updated.userId,
          'first_name': updated.firstName,
          'last_name': updated.lastName,
        },
      );
    } catch (error, stackTrace) {
      _showSnackbar(_strings.t('profile_update_failed', <String, String>{
        'error': '$error',
      }));
      await widget.logger.error(
        'Speech profile name update failed',
        error,
        stackTrace,
      );
    } finally {
      if (mounted) {
        setState(() {
          _isSavingSpokenName = false;
        });
      }
    }
  }

  Future<void> _toggleSpeechInput() async {
    await _speaker.stop();
    if (!_speechEnabled) {
      _showSnackbar(_strings.t('speech_unavailable'));
      return;
    }
    if (!_speechInputEnabled) {
      _showSnackbar(_strings.t('speech_input_disabled_message'));
      return;
    }
    if (_isListening) {
      await _speechToText.stop();
      return;
    }
    if (_awaitingSpokenName) {
      _inputController.clear();
    } else if (_profileName == null) {
      setState(() {
        _awaitingSpokenName = true;
      });
      _appendAssistantMessage(
        speechNamePromptMessage(_selectedLocale.languageCode),
      );
      _inputController.clear();
    }
    await _speechToText.listen(
      onResult: _onSpeechResult,
      partialResults: true,
      localeId: _localeIdForSpeech(_selectedLocale),
      listenMode: ListenMode.dictation,
    );
  }

  Future<void> _downloadRequestedDocuments() async {
    for (final kind in <String>['summary', 'document']) {
      await _downloadPdf(kind);
    }
  }

  Future<void> _toggleSpeechInputEnabled() async {
    if (!_speechEnabled) {
      _showSnackbar(_strings.t('speech_unavailable'));
      return;
    }

    final nextValue = !_speechInputEnabled;
    if (!nextValue && _isListening) {
      await _speechToText.stop();
    }

    if (!mounted) {
      return;
    }

    setState(() {
      _speechInputEnabled = nextValue;
      if (!nextValue) {
        _awaitingSpokenName = false;
      }
    });

    await widget.logger.info(
      'Speech input toggle changed',
      <String, Object?>{'enabled': nextValue},
    );
  }

  void _updateWelcomeMessageForLocale() {
    if (_messages.isEmpty) {
      return;
    }
    final firstMessage = _messages.first;
    if (!_isInitialWelcomeMessage(firstMessage)) {
      return;
    }
    final welcomeLanguage =
        _normalizeLanguageCode(_selectedLocale.languageCode);
    _messages[0] = _buildWelcomeMessage(languageCode: welcomeLanguage);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_speaker.stop());
    _speechToText.stop();
    _inputController.dispose();
    _messagesScrollController.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed &&
        _pendingUpdateInstallPath != null &&
        !_isInstallingUpdate) {
      unawaited(_resumePendingUpdateInstall());
    }
  }

  void _scrollToLatest({bool animated = true}) {
    if (!_messagesScrollController.hasClients) {
      return;
    }
    final offset = _messagesScrollController.position.maxScrollExtent;
    if (animated) {
      unawaited(
        _messagesScrollController.animateTo(
          offset,
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOut,
        ),
      );
      return;
    }
    _messagesScrollController.jumpTo(offset);
  }

  Future<void> _captureDocument() async {
    if (widget.cameras.isEmpty) {
      await widget.logger
          .info('Document capture requested with no available camera');
      _showSnackbar(_strings.t('no_camera_available'));
      return;
    }

    final path = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(
        builder: (_) => CameraCapturePage(
          camera: widget.cameras.first,
          logger: widget.logger,
          languageCode: _selectedLocale.languageCode,
        ),
      ),
    );
    if (!mounted) {
      return;
    }

    if (path != null) {
      setState(() {
        _documentPath = path;
      });
      await widget.logger.info(
        'Document captured',
        <String, Object?>{'document_path': path},
      );
      _showSnackbar(_strings.t('document_added'));
    }
  }

  Future<void> _sendMessage() async {
    final text = _inputController.text.trim();
    if (text.isEmpty || _isSending) {
      return;
    }
    if (_awaitingSpokenName) {
      await _storeSpokenName(text);
      return;
    }
    if (_selectedCase == null) {
      _showSnackbar(_strings.t('create_or_select_case'));
      return;
    }
    await widget.logger.info(
      'User message submission',
      <String, Object?>{
        'message_length': text.length,
        'has_document_path': _documentPath != null,
        'responder_mode': _responderMode.name,
      },
    );

    setState(() {
      _isSending = true;
      _hasExportReady = false;
      if (_selectedCase != null) {
        _caseHistoryOffset += 1;
      }
      _messages.add(
        ChatMessage(
          role: 'user',
          content: text,
          documentPath: _documentPath,
          createdAt: DateTime.now(),
        ),
      );
    });

    _inputController.clear();
    _scrollToLatest();

    try {
      if (_responderMode == ResponderMode.aiUserSimulator) {
        await widget.logger.info(
          'Starting AI user simulator discussion stream',
          <String, Object?>{
            'question_timeout_seconds': _questionTimeoutSeconds,
            'max_discussion_minutes': _maxDiscussionMinutes,
            'communication_minutes': _communicationMinutes,
          },
        );
        await for (final event in _apiClient.startDiscussionStream(
          instruction: text,
          locale: _selectedLocale,
          questionTimeoutSeconds: _questionTimeoutSeconds,
          maxDiscussionMinutes: _maxDiscussionMinutes,
          communicationMinutes: _communicationMinutes,
          documentPath: _documentPath,
        )) {
          if (event.event == 'message' && event.data is Map) {
            final payload = Map<String, dynamic>.from(event.data as Map);
            final role = (payload['role'] as String? ?? 'assistant')
                .toLowerCase()
                .trim();
            final content = payload['content'] as String? ?? '';
            final visibleContent = _sanitizeVisibleMessageContent(content);
            final agentName = payload['agent_name'] as String?;
            if (visibleContent.isEmpty) {
              continue;
            }
            if (!mounted) {
              continue;
            }
            setState(() {
              if (_selectedCase != null) {
                _caseHistoryOffset += 1;
              }
              _messages.add(
                ChatMessage(
                  role: role,
                  content: visibleContent,
                  agentName: agentName,
                  createdAt: DateTime.now(),
                ),
              );
            });
            _scrollToLatest();
            if (role == 'assistant') {
              unawaited(_speakAssistantMessage(visibleContent));
            }
          }
          if (event.event == 'result' || event.event == 'done') {
            if (mounted) {
              setState(() {
                _hasExportReady = true;
              });
            }
          }
          if (event.event == 'error') {
            throw Exception('Discussion stream reported error: ${event.data}');
          }
        }
      } else {
        final reply = await _apiClient.sendMessage(
          message: text,
          responderMode: _responderMode,
          locale: _selectedLocale,
          documentPath: _documentPath,
        );
        final exportReady = await _apiClient.isDocumentExportReady();
        final visibleReply = _sanitizeVisibleMessageContent(reply);
        if (_selectedCase != null) {
          _caseHistoryOffset += 1;
        }
        await widget.logger.info(
          'Assistant reply received',
          <String, Object?>{
            'reply_length': visibleReply.length,
            'responder_mode': _responderMode.name,
            'document_export_ready': exportReady,
          },
        );
        if (visibleReply.isEmpty) {
          return;
        }
        if (mounted) {
          setState(() {
            _messages.add(
              ChatMessage(
                role: 'assistant',
                content: visibleReply,
                createdAt: DateTime.now(),
              ),
            );
            _hasExportReady = exportReady;
          });
          _scrollToLatest();
          unawaited(_speakAssistantMessage(visibleReply));
        }
      }
    } on SessionExpiredException {
      _showSnackbar(
        _sessionExpiredMessageForLanguage(_selectedLocale.languageCode),
      );
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Failed to send message to API',
        error,
        stackTrace,
        <String, Object?>{
          'api_base_url': widget.apiBaseUrl,
          'responder_mode': _responderMode.name,
        },
      );
      _showApiError(error, apiBaseUrl: widget.apiBaseUrl);
    } finally {
      if (mounted) {
        setState(() {
          _isSending = false;
        });
      }
    }
  }

  Future<void> _downloadPdf(String kind) async {
    if (_isDownloading) {
      return;
    }
    if (!_hasExportReady) {
      _showSnackbar(_strings.t('pdf_not_ready'));
      return;
    }
    setState(() {
      _isDownloading = true;
    });
    try {
      await widget.logger.info(
        'PDF export download requested',
        <String, Object?>{'kind': kind, 'session_id': _apiClient.sessionId},
      );
      final payload = await _apiClient.downloadExportPdf(
        kind: kind,
        responderMode: _responderMode,
        locale: _selectedLocale,
      );
      final savedPath = await _fileSaver.save(
        bytes: payload.bytes,
        fileName: payload.filename,
        contentType: payload.contentType,
      );
      await widget.logger.info(
        'PDF export download completed',
        <String, Object?>{
          'kind': kind,
          'filename': payload.filename,
          'saved_path': savedPath,
          'bytes': payload.bytes.length,
        },
      );
      if (savedPath != null && savedPath.isNotEmpty) {
        _showSnackbar(_strings.t('pdf_saved_to', <String, String>{
          'path': savedPath,
        }));
        await _openSavedFile(context, _strings, savedPath);
      } else {
        _showSnackbar(_strings.t('pdf_download_started', <String, String>{
          'filename': payload.filename,
        }));
      }
    } on SessionExpiredException {
      _showSnackbar(
        _sessionExpiredMessageForLanguage(_selectedLocale.languageCode),
      );
    } catch (error, stackTrace) {
      await widget.logger.error(
        'PDF export download failed',
        error,
        stackTrace,
        <String, Object?>{'kind': kind, 'session_id': _apiClient.sessionId},
      );
      _showSnackbar(_strings.t('pdf_download_failed', <String, String>{
        'error': '$error',
      }));
    } finally {
      if (mounted) {
        setState(() {
          _isDownloading = false;
        });
      }
    }
  }

  Future<void> _openAccountSettings() async {
    final updated = await Navigator.of(context).push<LocalAuthUser>(
      MaterialPageRoute<LocalAuthUser>(
        builder: (_) => AccountSettingsPage(
          user: _signedInUser,
          authStore: widget.authStore,
          selectedLocale: _selectedLocale,
          locales: _localeOptions,
          speaker: _speaker,
          onLocaleChanged: _handleLocaleChanged,
          logger: widget.logger,
        ),
      ),
    );
    if (updated == null) {
      return;
    }
    setState(() {
      _signedInUser = updated;
    });
    widget.onProfileUpdated(updated);
    await widget.logger.info(
      'Signed-in profile updated',
      <String, Object?>{
        'phone': updated.phoneNumber,
        'email': updated.email,
      },
    );
  }

  Future<void> _handleLocaleChanged(LocaleOption locale) async {
    if (!mounted) {
      return;
    }
    setState(() {
      _selectedLocale = locale;
      _updateWelcomeMessageForLocale();
      _hasExportReady = false;
    });
    if (_isListening) {
      await _speechToText.stop();
    }
    await _loadSpeakerVoices();
    await widget.logger.info(
      'Locale changed',
      <String, Object?>{
        'country': locale.countryCode,
        'language': locale.languageCode,
      },
    );
    _apiClient.resetSession();
  }

  Future<void> _loadCases() async {
    setState(() {
      _isLoadingCases = true;
    });
    try {
      final cases = await _apiClient.listCases(userId: _signedInUser.userId);
      if (!mounted) {
        return;
      }
      final selected = cases.isNotEmpty ? cases.first : null;
      setState(() {
        _cases = cases;
      });
      await _selectCase(selected);
    } catch (error) {
      _showSnackbar(_strings.t('failed_to_load_cases', <String, String>{
        'error': '$error',
      }));
    } finally {
      if (mounted) {
        setState(() {
          _isLoadingCases = false;
        });
      }
    }
  }

  Future<void> _createCase() async {
    if (_cases.length >= 5) {
      _showSnackbar(_strings.t('maximum_cases'));
      return;
    }
    final controller = TextEditingController();
    final strings = _strings;
    final title = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(strings.t('create_case')),
        content: TextField(
          controller: controller,
          decoration: InputDecoration(labelText: strings.t('case_name')),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(strings.t('cancel')),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: Text(strings.t('create')),
          ),
        ],
      ),
    );
    if (title == null || title.trim().isEmpty) return;
    try {
      final created = await _apiClient.createCase(
          userId: _signedInUser.userId, title: title.trim());
      setState(() {
        _cases = <CaseSummary>[created, ..._cases];
      });
      await _selectCase(created);
      _showSnackbar(_strings.t('case_created'));
    } catch (error) {
      _showSnackbar('$error');
    }
  }

  Future<void> _renameSelectedCase() async {
    final selected = _selectedCase;
    if (selected == null) return;
    final controller = TextEditingController(text: selected.title);
    final strings = _strings;
    final title = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(strings.t('rename_case')),
        content: TextField(controller: controller),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(strings.t('cancel')),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: Text(strings.t('save')),
          ),
        ],
      ),
    );
    if (title == null || title.trim().isEmpty) return;
    try {
      final updated = await _apiClient.renameCase(
          caseId: selected.caseId,
          userId: _signedInUser.userId,
          title: title.trim());
      setState(() {
        _cases = _cases
            .map((c) => c.caseId == updated.caseId ? updated : c)
            .toList();
        _selectedCase = updated;
      });
    } catch (error) {
      _showSnackbar(_strings.t('rename_case_failed', <String, String>{
        'error': '$error',
      }));
    }
  }

  Future<void> _deleteSelectedCase() async {
    final selected = _selectedCase;
    if (selected == null) return;
    try {
      await _apiClient.deleteCase(
          caseId: selected.caseId, userId: _signedInUser.userId);
      final remainingCases =
          _cases.where((c) => c.caseId != selected.caseId).toList();
      final nextSelected =
          remainingCases.isNotEmpty ? remainingCases.first : null;
      setState(() {
        _cases = remainingCases;
      });
      await _selectCase(nextSelected);
      _showSnackbar(_strings.t('case_deleted'));
    } catch (error) {
      _showSnackbar(_strings.t('delete_case_failed', <String, String>{
        'error': '$error',
      }));
    }
  }

  Future<void> _signOut() async {
    _apiClient.resetSession();
    await widget.logger.info(
      'Signed-in user requested sign out',
      <String, Object?>{
        'phone': _signedInUser.phoneNumber,
        'email': _signedInUser.email,
      },
    );
    widget.onSignedOut();
  }

  void _showSnackbar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  Future<void> _copyLastErrorCorrelationId() async {
    final id = _lastErrorCorrelationId;
    if (id == null || id.isEmpty) {
      return;
    }
    await Clipboard.setData(ClipboardData(text: id));
    if (!mounted) {
      return;
    }
    _showSnackbar(_strings.t('request_id_copied', <String, String>{'id': id}));
  }

  void _showApiError(Object error, {required String apiBaseUrl}) {
    final String correlationId =
        _apiClient.lastCorrelationId ?? _apiClient.flowCorrelationId;
    if (mounted) {
      setState(() {
        _lastErrorCorrelationId = correlationId;
      });
    } else {
      _lastErrorCorrelationId = correlationId;
    }
    if (correlationId.isNotEmpty) {
      _showSnackbar(
        _strings.t('failed_to_reach_api_with_correlation', <String, String>{
          'url': apiBaseUrl,
          'error': '$error',
          'id': correlationId,
        }),
      );
      return;
    }
    _showSnackbar(_strings.t('failed_to_reach_api', <String, String>{
      'url': apiBaseUrl,
      'error': '$error',
    }));
  }

  @override
  Widget build(BuildContext context) {
    final strings = _strings;
    return Scaffold(
      body: Stack(
        children: [
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: <Color>[
                    const Color(0xFF041B59),
                    const Color(0xFF1388E9),
                    const Color(0xFF041B59),
                  ],
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: Opacity(
              opacity: 0.08,
              child: SvgPicture.asset(
                'assets/branding/hero-footer.svg',
                fit: BoxFit.cover,
              ),
            ),
          ),
          SafeArea(
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
                  child: Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.94),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Row(
                      children: [
                        const Expanded(
                          child: Text(
                            'AIJurisDigta',
                            style: TextStyle(
                              fontSize: 20,
                              fontWeight: FontWeight.w700,
                              color: Color(0xFF0A2F6B),
                            ),
                          ),
                        ),
                        Text(
                          _appVersionLabel,
                          style: Theme.of(context)
                              .textTheme
                              .bodySmall
                              ?.copyWith(color: const Color(0xFF4A628A)),
                        ),
                        const SizedBox(width: 8),
                        if (_lastErrorCorrelationId != null &&
                            _lastErrorCorrelationId!.isNotEmpty)
                          Tooltip(
                            message:
                                strings.t('request_id_label', <String, String>{
                              'id': _lastErrorCorrelationId!,
                            }),
                            child: TextButton.icon(
                              onPressed: _copyLastErrorCorrelationId,
                              icon: const Icon(Icons.tag),
                              label: Text(strings.t('show_request_id')),
                            ),
                          ),
                        TextButton.icon(
                          onPressed: _signOut,
                          icon: const Icon(Icons.logout),
                          label: Text(strings.t('sign_out')),
                        ),
                      ],
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
                  child: Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.94),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Column(
                      children: [
                        Align(
                          alignment: Alignment.centerLeft,
                          child: Tooltip(
                            message: strings.t('speech_input_toggle_label'),
                            child: FilledButton.tonalIcon(
                              onPressed: _speechEnabled
                                  ? () => unawaited(
                                        _toggleSpeechInputEnabled(),
                                      )
                                  : null,
                              icon: Icon(
                                _speechInputEnabled ? Icons.mic : Icons.mic_off,
                              ),
                              label: Text(
                                _speechInputEnabled
                                    ? strings.t('speech_input_enabled')
                                    : strings.t('speech_input_disabled'),
                              ),
                            ),
                          ),
                        ),
                        if (_showLocalResponderSwitch) ...[
                          const SizedBox(height: 10),
                          Row(
                            children: [
                              Text(strings.t('local_mode')),
                              const SizedBox(width: 8),
                              Expanded(
                                child: DropdownButton<ResponderMode>(
                                  isExpanded: true,
                                  value: _responderMode,
                                  onChanged: (mode) {
                                    if (mode == null) {
                                      return;
                                    }
                                    setState(() {
                                      _responderMode = mode;
                                      _hasExportReady = false;
                                    });
                                    unawaited(
                                      widget.logger.info(
                                        'Responder mode changed',
                                        <String, Object?>{
                                          'responder_mode': mode.name,
                                        },
                                      ),
                                    );
                                    _apiClient.resetSession();
                                  },
                                  items: [
                                    DropdownMenuItem(
                                      value: ResponderMode.realPerson,
                                      child: Text(strings.t('real_agent')),
                                    ),
                                    DropdownMenuItem(
                                      value: ResponderMode.aiUserSimulator,
                                      child: Text(
                                        strings.t('ai_user_simulator_agent'),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.94),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      children: [
                        Expanded(
                          child: _isLoadingCases
                              ? const LinearProgressIndicator()
                              : DropdownButton<CaseSummary>(
                                  isExpanded: true,
                                  value: _selectedCase,
                                  hint: Text(strings.t('select_case')),
                                  items: _cases
                                      .map((item) =>
                                          DropdownMenuItem<CaseSummary>(
                                            value: item,
                                            child: Text(item.title),
                                          ))
                                      .toList(),
                                  onChanged: (value) =>
                                      unawaited(_selectCase(value)),
                                ),
                        ),
                        IconButton(
                          onPressed: _createCase,
                          icon: const Icon(Icons.add),
                          tooltip: strings.t('create_case'),
                        ),
                        IconButton(
                          onPressed: _selectedCase == null
                              ? null
                              : _renameSelectedCase,
                          icon: const Icon(Icons.edit),
                          tooltip: strings.t('rename_case'),
                        ),
                        IconButton(
                          onPressed: _selectedCase == null
                              ? null
                              : _deleteSelectedCase,
                          icon: const Icon(Icons.delete_outline),
                          tooltip: strings.t('delete_case'),
                        ),
                      ],
                    ),
                  ),
                ),
                if (_documentPath != null)
                  MaterialBanner(
                    content: Text(
                      strings.t('attached_document', <String, String>{
                        'path': _documentPath!,
                      }),
                    ),
                    leading: const Icon(Icons.attachment),
                    actions: [
                      TextButton(
                        onPressed: () {
                          setState(() {
                            _documentPath = null;
                          });
                          unawaited(
                            widget.logger
                                .info('Attached document path cleared'),
                          );
                        },
                        child: Text(strings.t('clear')),
                      ),
                    ],
                  ),
                Expanded(
                  child: Scrollbar(
                    controller: _messagesScrollController,
                    thumbVisibility: true,
                    trackVisibility: true,
                    interactive: true,
                    child: ListView.builder(
                      controller: _messagesScrollController,
                      padding: const EdgeInsets.all(12),
                      itemCount:
                          _messages.length + (_caseHistoryHasMore ? 1 : 0),
                      itemBuilder: (context, index) {
                        if (index == _messages.length) {
                          return Align(
                            alignment: Alignment.center,
                            child: Padding(
                              padding: const EdgeInsets.only(bottom: 12),
                              child: FilledButton.tonalIcon(
                                onPressed: _isLoadingCaseHistory
                                    ? null
                                    : () => unawaited(
                                          _loadCaseHistory(reset: false),
                                        ),
                                icon: _isLoadingCaseHistory
                                    ? const SizedBox(
                                        width: 14,
                                        height: 14,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                        ),
                                      )
                                    : const Icon(Icons.arrow_downward),
                                label: Text(strings.t('show_next_5_messages')),
                              ),
                            ),
                          );
                        }
                        final message = _messages[index];
                        final displayContent = _displayContentForMessage(
                          message,
                        );
                        final isUser = message.role == 'user';
                        final speaker =
                            isUser ? strings.t('you') : strings.t('assistant');
                        return Align(
                          alignment: isUser
                              ? Alignment.centerRight
                              : Alignment.centerLeft,
                          child: Container(
                            constraints: const BoxConstraints(maxWidth: 320),
                            margin: const EdgeInsets.only(bottom: 10),
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: isUser
                                  ? Theme.of(context)
                                      .colorScheme
                                      .primaryContainer
                                  : Theme.of(context)
                                      .colorScheme
                                      .surfaceContainerHighest,
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  speaker,
                                  style:
                                      Theme.of(context).textTheme.labelMedium,
                                ),
                                const SizedBox(height: 4),
                                Text(displayContent),
                                if (message.documentPath != null)
                                  Padding(
                                    padding: const EdgeInsets.only(top: 8),
                                    child: Text(
                                      strings
                                          .t('document_label', <String, String>{
                                        'path': message.documentPath!,
                                      }),
                                      style:
                                          Theme.of(context).textTheme.bodySmall,
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                ),
                if (_caseDocuments.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 2, 12, 8),
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: _caseDocuments
                            .map(
                              (document) => FilledButton.tonalIcon(
                                onPressed: _downloadingCaseDocumentIds
                                        .contains(document.docId)
                                    ? null
                                    : () => _downloadCaseDocument(document),
                                icon: _downloadingCaseDocumentIds
                                        .contains(document.docId)
                                    ? const SizedBox(
                                        width: 14,
                                        height: 14,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                        ),
                                      )
                                    : const Icon(Icons.download_outlined),
                                label: Text(document.originalFilename),
                              ),
                            )
                            .toList(),
                      ),
                    ),
                  ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 2, 12, 12),
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      FilledButton.tonalIcon(
                        onPressed: _openAccountSettings,
                        icon: const Icon(Icons.manage_accounts),
                        label: Text(strings.t('account')),
                      ),
                      FilledButton.tonalIcon(
                        onPressed:
                            (_isDownloading || _isSending || !_hasExportReady)
                                ? null
                                : _downloadRequestedDocuments,
                        icon: _isDownloading
                            ? const SizedBox(
                                width: 14,
                                height: 14,
                                child:
                                    CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.description),
                        label: Text(strings.t('export_documents')),
                      ),
                    ],
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 2, 12, 12),
                  child: Row(
                    children: [
                      IconButton(
                        onPressed: _captureDocument,
                        icon: const Icon(Icons.document_scanner),
                        tooltip: strings.t('upload_documents'),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: TextField(
                          controller: _inputController,
                          minLines: 1,
                          maxLines: 1,
                          keyboardType: TextInputType.text,
                          textInputAction: TextInputAction.send,
                          onSubmitted: (_) => _sendMessage(),
                          decoration: InputDecoration(
                            hintText:
                                _responderMode == ResponderMode.aiUserSimulator
                                    ? strings.t('case_input_discussion')
                                    : strings.t('case_input_question'),
                            filled: true,
                            fillColor: Colors.white,
                            border: const OutlineInputBorder(),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      IconButton(
                        onPressed: _speechEnabled ? _toggleSpeechInput : null,
                        icon: Icon(
                          _isListening ? Icons.mic : Icons.mic_none,
                          color: _isListening
                              ? Theme.of(context).colorScheme.primary
                              : null,
                        ),
                        tooltip: _isListening
                            ? strings.t('stop_speech_input')
                            : strings.t('speech_input'),
                      ),
                      const SizedBox(width: 8),
                      IconButton(
                        onPressed: _isSending ? null : _sendMessage,
                        icon: _isSending
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child:
                                    CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.send),
                        tooltip: _responderMode == ResponderMode.aiUserSimulator
                            ? strings.t('start_ai_discussion')
                            : strings.t('send_to_api'),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class CameraCapturePage extends StatefulWidget {
  const CameraCapturePage({
    super.key,
    required this.camera,
    required this.logger,
    required this.languageCode,
  });

  final CameraDescription camera;
  final AppLogger logger;
  final String languageCode;

  @override
  State<CameraCapturePage> createState() => _CameraCapturePageState();
}

class _CameraCapturePageState extends State<CameraCapturePage> {
  CameraController? _controller;
  Future<void>? _initializeControllerFuture;
  String? _cameraErrorMessage;

  AppStrings get _strings => AppStrings(widget.languageCode);

  @override
  void initState() {
    super.initState();
    _controller = CameraController(widget.camera, ResolutionPreset.medium);
    _initializeControllerFuture = _initializeCamera();
  }

  Future<void> _initializeCamera() async {
    final controller = _controller;
    if (controller == null) {
      return;
    }

    try {
      await controller.initialize();
    } on CameraException catch (error, stackTrace) {
      await widget.logger.error(
        'Camera initialization failed',
        error,
        stackTrace,
        <String, Object?>{'camera_error_code': error.code},
      );
      final message = _cameraErrorMessageFor(error);
      if (mounted) {
        setState(() {
          _cameraErrorMessage = message;
        });
      }
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Unexpected camera initialization failure',
        error,
        stackTrace,
      );
      if (mounted) {
        setState(() {
          _cameraErrorMessage = _strings.t('camera_unavailable');
        });
      }
    }
  }

  String _cameraErrorMessageFor(CameraException error) {
    switch (error.code) {
      case 'cameraNotReadable':
        return _strings.t('camera_busy');
      case 'CameraAccessDenied':
      case 'cameraAccessDenied':
        return _strings.t('camera_access_denied');
      default:
        return _strings.t('camera_error_with_reason', <String, String>{
          'reason': error.description ?? error.code,
        });
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  Future<void> _takePicture() async {
    final controller = _controller;
    if (controller == null) {
      return;
    }

    try {
      await _initializeControllerFuture;
      if (_cameraErrorMessage != null) {
        return;
      }
      final image = await controller.takePicture();
      if (mounted) {
        Navigator.of(context).pop(image.path);
      }
    } on CameraException catch (error, stackTrace) {
      await widget.logger.error(
        'Camera capture failed',
        error,
        stackTrace,
        <String, Object?>{'camera_error_code': error.code},
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(_cameraErrorMessageFor(error))),
        );
      }
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Unexpected camera capture failure',
        error,
        stackTrace,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(_strings.t('camera_capture_failed'))),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final strings = _strings;
    return Scaffold(
      appBar: AppBar(title: Text(strings.t('capture_document'))),
      body: FutureBuilder<void>(
        future: _initializeControllerFuture,
        builder: (context, snapshot) {
          if (_cameraErrorMessage != null) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  _cameraErrorMessage!,
                  textAlign: TextAlign.center,
                ),
              ),
            );
          }

          if (snapshot.connectionState == ConnectionState.done &&
              _controller != null) {
            return Stack(
              children: [
                Positioned.fill(child: CameraPreview(_controller!)),
                Positioned(
                  bottom: 24,
                  left: 0,
                  right: 0,
                  child: Center(
                    child: FloatingActionButton.extended(
                      onPressed: _takePicture,
                      icon: const Icon(Icons.camera),
                      label: Text(strings.t('use_photo')),
                    ),
                  ),
                ),
              ],
            );
          }

          if (snapshot.hasError) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  strings.t('camera_error_with_reason', <String, String>{
                    'reason': '${snapshot.error}',
                  }),
                  textAlign: TextAlign.center,
                ),
              ),
            );
          }

          return const Center(child: CircularProgressIndicator());
        },
      ),
    );
  }
}
