import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:share_plus/share_plus.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'package:url_launcher/url_launcher.dart';

import 'api/app_status.dart';
import 'app/app_locale.dart';
import 'state/mobile_app_providers.dart';
import 'audio/jurisdicta_speaker.dart';
import 'speech_service.dart';
import 'auth/local_auth_store.dart';
import 'chat/generated_document_message.dart';
import 'chat/profile_service.dart';
import 'chat/rule_engine.dart';
import 'chat/speech_flow.dart';
import 'chat/voice_session_orchestrator.dart';
import 'logging/app_logger.dart';
import 'platform/app_updater.dart';
import 'platform/device_phone_number.dart';
import 'platform/file_opener.dart';
import 'platform/file_saver.dart';
import 'update/github_release.dart';

bool _isOfflineError(Object? error) {
  return isLikelyOfflineError(error);
}

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
const String _localAutofillPhoneNumber = '+421944400166';
const String _dataProcessingNoticeUrl =
    'https://www.jurisdigta.eu/#data-processing-consent';
const String _dataProcessingConsentVersion = '2026-05-06';
final FileOpener _savedFileOpener = createFileOpener();

const Map<String, String> _sessionExpiredMessagesByLanguage = <String, String>{
  'SK':
      'Relácia vypršala. Vytvorili sme novú reláciu. Prosím, odošlite poslednú správu znova.',
  'EN':
      'Your session expired. A new session was created. Please send your last message again.',
  'GE':
      'Ihre Sitzung ist abgelaufen. Eine neue Sitzung wurde erstellt. Bitte senden Sie Ihre letzte Nachricht erneut.',
};

String _normalizeLanguageCode(String languageCode) {
  return normalizeAppLanguageCode(languageCode);
}

String _sessionExpiredMessageForLanguage(String languageCode) {
  final normalized = _normalizeLanguageCode(languageCode);
  return _sessionExpiredMessagesByLanguage[normalized] ??
      _sessionExpiredMessagesByLanguage[fallbackAppLanguageCode]!;
}

String _defaultApiBaseUrl() {
  return defaultApiBaseUrlForEnvironment(
    override: _apiBaseUrlOverride,
    isWeb: kIsWeb,
    targetPlatform: defaultTargetPlatform,
  );
}

@visibleForTesting
String defaultApiBaseUrlForEnvironment({
  required String override,
  required bool isWeb,
  required TargetPlatform targetPlatform,
}) {
  if (override.trim().isNotEmpty) {
    return normalizeApiBaseUrlForEnvironment(override.trim());
  }
  if (isWeb || targetPlatform != TargetPlatform.android) {
    return 'http://127.0.0.1:8080';
  }
  return 'http://10.0.2.2:8080';
}

@visibleForTesting
String normalizeApiBaseUrlForEnvironment(String value) {
  final trimmed = value.trim();
  final uri = Uri.tryParse(trimmed);
  if (uri == null || !uri.hasScheme) {
    return trimmed;
  }
  final host = uri.host.toLowerCase();
  final isLoopback = host == '127.0.0.1' ||
      host == 'localhost' ||
      host == '10.0.2.2' ||
      host == '0.0.0.0';
  if (uri.scheme.toLowerCase() != 'https' || !isLoopback) {
    return trimmed;
  }
  return uri.replace(scheme: 'http').toString();
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

class AppStrings {
  AppStrings(String languageCode)
      : languageCode = _normalizeLanguageCode(languageCode);

  final String languageCode;

  static const Map<String, Map<String, String>> _localized =
      <String, Map<String, String>>{
    'SK': <String, String>{
      'auth_sign_in_tab': 'Prihlásenie',
      'auth_sign_up_tab': 'Registrácia',
      'phone_number': 'Telefónne číslo',
      'phone_number_required': 'Telefónne číslo *',
      'phone_number_hint': _localAutofillPhoneNumber,
      'email': 'E-mail',
      'email_required': 'E-mail *',
      'password': 'Heslo',
      'password_required': 'Heslo *',
      'first_name': 'Meno',
      'first_name_optional': 'Meno (voliteľné)',
      'last_name': 'Priezvisko',
      'last_name_optional': 'Priezvisko (voliteľné)',
      'address': 'Adresa',
      'city': 'Mesto',
      'country': 'Krajina',
      'zip_code': 'PSC',
      'tax_number': 'DIC',
      'identity_card_number': 'Cislo obcianskeho preukazu',
      'date_of_birth': 'Datum narodenia',
      'social_security_number': 'Rodne cislo',
      'signing_in': 'Prihlasujem...',
      'login': 'Prihlásenie',
      'sign_in_by_phone': 'Prihlásiť cez telefón',
      'send_sign_in_code': 'Poslať prihlasovací kód',
      'verify_sign_in_code': 'Prihlásiť kódom',
      'sign_in_code_required': 'Prihlasovací kód *',
      'sign_in_code_sent': 'Prihlasovací kód bol odoslaný na e-mail.',
      'sign_in_code_send_failed':
          'Odoslanie prihlasovacieho kódu zlyhalo: {{error}}',
      'invalid_sign_in_code': 'Neplatný prihlasovací kód.',
      'sign_in_by_email_password': 'Prihlásiť cez e-mail a heslo',
      'sign_in_failed': 'Prihlásenie zlyhalo: {{error}}',
      'phone_not_found':
          'Telefónne číslo sa nenašlo. Prihláste sa e-mailom a heslom.',
      'invalid_email_password': 'Neplatný e-mail alebo heslo.',
      'signing_up': 'Registrujem...',
      'go_to_sign_up': 'Registrácia',
      'create_account': 'Vytvoriť účet',
      'sign_up_failed': 'Registrácia zlyhala: {{error}}',
      'verification_code_required': 'Overovací kód *',
      'send_code': 'Poslať kód',
      'code_sent': 'Kód bol odoslaný na e-mail.',
      'send_code_failed': 'Odoslanie kódu zlyhalo: {{error}}',
      'data_processing_consent_label':
          'Súhlasím so spracovaním osobných a finančných údajov podľa právneho oznámenia.',
      'data_processing_consent_link': 'Pozrieť právne oznámenie',
      'data_processing_consent_required':
          'Pred registráciou musíte potvrdiť právne oznámenie.',
      'account': 'Profile',
      'sign_out': 'Odhlásiť sa',
      'save_changes': 'Uložiť zmeny',
      'language_changed': 'Jazyk bol zmenený na {{language}}.',
      'profile_updated_success': 'Profil bol aktualizovaný.',
      'saving': 'Ukladám...',
      'update_sign_in_profile': 'Upraviť prihlasovací profil',
      'profile_update_failed': 'Aktualizácia profilu zlyhala: {{error}}',
      'profile_name_changed':
          'Vidím, že ste zmenili meno. Dobrý deň, {{name}}.',
      'profile_voice_patch_invalid':
          'Zmenu profilu som nerozpoznala. Povedzte napríklad: Zmeň adresu na Hlavná 12.',
      'profile_voice_patch_recap':
          'Mám zmeniť {{field}} na {{value}}? Ak áno, povedzte Áno. Ak nie, povedzte Nie.',
      'profile_voice_patch_cancelled': 'Zmenu profilu som zrušila.',
      'profile_voice_patch_confirm_first_name': 'meno',
      'profile_voice_patch_confirm_last_name': 'priezvisko',
      'profile_voice_patch_confirm_address': 'adresu',
      'debug_mode': 'Debug režim',
      'debug_mode_description':
          'V debug režime sa všetky logy ukladajú do súboru na Android zariadení.',
      'debug_mode_enabled': 'Debug režim zapnutý.',
      'debug_mode_disabled': 'Debug režim vypnutý.',
      'share_logs': 'Zdieľať logy',
      'logs_shared': 'Zdieľanie logov bolo spustené.',
      'share_logs_failed': 'Zdieľanie logov zlyhalo: {{error}}',
      'subscription': 'Predplatné',
      'subscription_change_requested':
          'Zmena predplatného bola odoslaná (pending).',
      'subscription_change_failed': 'Zmena predplatného zlyhala: {{error}}',
      'subscription_status': 'Stav: {{status}}',
      'update_available': 'Dostupná aktualizácia',
      'update_body':
          'K dispozícii je nová verzia.\n\n{{current}} -> {{latest}}',
      'later': 'Neskôr',
      'skip_until_restart': 'Preskočiť do nového štartu',
      'update': 'Aktualizovať',
      'invalid_release_url': 'Adresa aktualizácie je neplatná.',
      'could_not_open_update_page':
          'Stránku s aktualizáciou sa nepodarilo otvoriť.',
      'update_apk_missing':
          'Release neobsahuje Android APK súbor. Otváram stránku release.',
      'update_download_started': 'Sťahujem aktualizáciu {{latest}}...',
      'update_download_progress':
          'Sťahovanie {{percent}}% ({{received}} / {{total}} MB)',
      'update_download_finishing':
          'Sťahovanie dokončené. Pripravujem inštaláciu...',
      'update_install_permission_check':
          'Kontrolujem povolenie na inštaláciu Android APK.',
      'update_install_permission_required':
          'Povoľte inštaláciu z tejto aplikácie a vráťte sa späť.',
      'update_install_started':
          'Android inštalátor bol otvorený. Potvrďte aktualizáciu.',
      'update_download_failed': 'Sťahovanie aktualizácie zlyhalo: {{error}}',
      'update_install_failed': 'Spustenie aktualizácie zlyhalo: {{error}}',
      'update_install_signature_mismatch':
          'Nainštalovaná aplikácia má iný podpis ako aktualizácia. Odinštalujte aktuálnu aplikáciu a potom nainštalujte novú verziu.',
      'allow_install_unknown_apps':
          'V nastaveniach Androidu povoľte inštalácie z tejto aplikácie a vráťte sa späť.',
      'speech_recognition_error': 'Chyba rozpoznávania reči: {{error}}',
      'speech_unavailable':
          'Rozpoznávanie reči na tomto zariadení nie je dostupné.',
      'speech_input_toggle_label': 'Vstup hlasom',
      'speech_input_enabled': 'Vstup hlasom zapnutý',
      'speech_input_disabled': 'Vstup hlasom vypnutý',
      'speech_input_disabled_message':
          'Vstup hlasom je vypnutý. Zapnite ho tlačidlom Vstup hlasom.',
      'speech_input_auto_stopped':
          'Hlasový vstup sa pozastavil. Klepnite na mikrofón pre pokračovanie.',
      'speech_send_confirmation_prompt':
          'Už minútu som nezachytila ďalšiu reč. Ak chcete správu odoslať, povedzte Posli. Ak ju chcete zmazať, povedzte Zrus vsetko.',
      'speech_draft_cancelled': 'Rozpracovanú hlasovú správu som zmazala.',
      'speaker_output': 'Hlasový výstup asistenta',
      'speaker_voice_label': 'Hlas asistenta',
      'speaker_voice_unavailable': 'Pre zvolený jazyk nie je dostupný hlas.',
      'test_speaker_voice': 'Vyskúšať hlas',
      'speaker_test_sample':
          'Dobrý deň, som Jurisdicta a toto je ukážka hlasu.',
      'no_camera_available': 'Na tomto zariadení nie je dostupná kamera.',
      'document_added': 'Dokument bol pridaný z kamery.',
      'create_or_select_case':
          'Pred odoslaním správy vytvorte alebo vyberte prípad.',
      'create_or_select_case_message':
          'Pred odoslaním správy vytvorte alebo vyberte prípad. Môžete povedať napríklad: Vytvor mi nový prípad s názvom splnomocnenie.',
      'failed_to_reach_api':
          'Nepodarilo sa spojiť s API na adrese {{url}}: {{error}}',
      'no_internet_connection':
          'Nie je internetové pripojenie. Skontrolujte pripojenie a skúste znova.',
      'api_health_failed': 'API hlási chybu: {{error}}',
      'failed_to_reach_api_with_correlation':
          'Nepodarilo sa spojiť s API na adrese {{url}}: {{error}} (ID: {{id}})',
      'checking_api': 'Kontrolujem API...',
      'api_unavailable_title': 'API nie je dostupné',
      'api_retry_in': 'Ďalší pokus o {{seconds}} s',
      'retry_now': 'Skúsiť znova',
      'request_id_label': 'ID korelácie: {{id}}',
      'show_request_id': 'ID',
      'copy_request_id': 'Kopírovať ID korelácie',
      'request_id_copied': 'ID korelácie bolo skopírované: {{id}}',
      'pdf_not_ready':
          'PDF ešte nie je pripravené. Najprv dokončite AI diskusiu.',
      'pdf_saved_to': 'PDF uložené do {{path}}',
      'pdf_download_started': 'Sťahovanie PDF spustené: {{filename}}',
      'pdf_download_failed': 'Sťahovanie PDF zlyhalo: {{error}}',
      'document_pdf_offer':
          'Návrh dokumentu som do chatu nezobrazila. Chcete ho vidieť vo formáte PDF? Použite tlačidlo PDF dokument.',
      'open_saved_file_failed': 'Súbor sa nepodarilo otvoriť.',
      'downloaded_files_title': 'Stiahnuté súbory',
      'downloaded_files_subtitle': 'Vyberte súbor, ktorý chcete teraz otvoriť.',
      'failed_to_load_cases': 'Nepodarilo sa načítať prípady: {{error}}',
      'failed_to_load_case_history':
          'Nepodarilo sa načítať históriu prípadu: {{error}}',
      'maximum_cases':
          'Maximum je 5 prípadov. Najprv odstráň existujúci prípad.',
      'create_case': 'Vytvoriť prípad',
      'delete_case': 'Odstrániť prípad',
      'case_name': 'Názov prípadu',
      'cancel': 'Zrušiť',
      'create': 'Vytvoriť',
      'case_created': 'Prípad bol vytvorený.',
      'case_voice_name_prompt': 'Povedzte prosím názov nového prípadu.',
      'case_voice_created': 'Vytvorila som nový prípad {{name}}.',
      'case_voice_created_continue':
          'Vytvorila som nový prípad {{name}}. Prosím, pokračujte svojou otázkou alebo nahrajte dokumenty.',
      'case_auto_created':
          'Automaticky som vytvorila nový prípad {{name}} pre túto diskusiu.',
      'case_archive_confirmation':
          'Aktuálny prípad {{name}} bude archivovaný. Chcete vytvoriť nový prípad? Odpovedzte prosím áno alebo nie.',
      'case_archive_confirmation_named':
          'Aktuálny prípad {{current}} bude archivovaný. Chcete vytvoriť nový prípad s názvom {{name}}? Odpovedzte prosím áno alebo nie.',
      'case_archive_confirmation_retry':
          'Prosím, odpovedzte áno alebo nie. Mám archivovať aktuálny prípad a vytvoriť nový?',
      'case_archive_cancelled': 'Dobre, ponechám aktuálny prípad aktívny.',
      'case_voice_name_retry':
          'Nezachytila som názov prípadu dostatočne presne. Povedzte prosím názov nového prípadu.',
      'rename_case': 'Premenovať prípad',
      'save': 'Uložiť',
      'rename_case_failed': 'Premenovanie prípadu zlyhalo: {{error}}',
      'open_case_document': 'Otvoriť {{filename}}',
      'no_case_documents': 'Prípad zatiaľ neobsahuje dokumenty.',
      'document_status_uploaded': 'Nahrané',
      'document_status_processing': 'Spracováva sa',
      'document_status_processed': 'Spracované',
      'document_status_failed': 'Chyba spracovania',
      'document_status_unknown': 'Neznámy stav',
      'document_status_ready': 'Text a vektor pripravené pre analýzu.',
      'document_status_pending_message':
          'Operáciu s dokumentmi teraz neviem vykonať. Tieto dokumenty sa ešte spracúvajú: {{documents}}',
      'document_status_report_intro': 'Stav dokumentov v tomto prípade:',
      'document_status_report_empty':
          'Tento prípad zatiaľ neobsahuje dokumenty.',
      'case_deleted': 'Prípad bol odstránený.',
      'delete_case_failed': 'Odstránenie prípadu zlyhalo: {{error}}',
      'select_case': 'Vyberte prípad',
      'case_history': 'História prípadu',
      'case_documents': 'Dokumenty prípadu',
      'case_validation_title': 'Validacia pripadu',
      'validation_accuracy_label': 'Presnost',
      'validation_summary_label': 'Zhrnutie validacie',
      'law_citations_title': 'Relevantné právne citácie',
      'law_citation_open': 'Otvoriť plné znenie',
      'law_citation_effective_from': 'Účinné od',
      'law_citation_version': 'Verzia',
      'law_citation_open_failed': 'Súbor zákona sa nepodarilo otvoriť.',
      'knowledge_updated_label': 'Pravne data aktualizovane',
      'model_version_label': 'Verzia modelu',
      'law_date_label': 'Law Date',
      'show_next_5_messages': 'Zobraziť ďalších 5 správ',
      'download_case_document': 'Stiahnuť {{filename}}',
      'share_case_document': 'Zdieľať {{filename}}',
      'case_document_shared': 'Dokument bol odoslaný na zdieľanie.',
      'case_document_share_failed': 'Zdieľanie dokumentu zlyhalo: {{error}}',
      'case_document_download_failed':
          'Sťahovanie dokumentu zlyhalo: {{error}}',
      'attached_document': 'Priložený dokument: {{path}}',
      'clear': 'VYMAZAT',
      'you': 'Vy',
      'assistant': 'Asistent',
      'frontend_agent': 'Frontend',
      'backend_agent': 'Backend',
      'frontend_thinking_message': 'Premyslam...',
      'backend_processing_fallback_message': 'Spracovavam...',
      'document_label': 'Dokument: {{path}}',
      'language_country': 'Jazyk a krajina',
      'local_mode': 'Lokálny režim',
      'real_agent': 'Reálny agent',
      'ai_user_simulator_agent': 'AI simulátor používateľa',
      'summary_pdf': 'PDF zhrnutie',
      'document_pdf': 'PDF dokument',
      'export_documents': 'Dokumenty',
      'upload_documents': 'Nahrať dokumenty',
      'case_input_discussion': 'Popíšte prípad pre spustenie diskusie...',
      'case_input_question': 'Položte právnu otázku...',
      'stop_speech_input': 'Zastaviť hlasový vstup',
      'speech_input': 'Pridať otázku alebo odpoveď hlasom',
      'start_ai_discussion': 'Spustiť AI diskusiu',
      'send_to_api': 'Odoslať do API',
      'capture_document': 'Zachytiť dokument',
      'documents_uploading': 'Dokumenty sa nahrávajú.',
      'documents_uploaded': 'Dokumenty sú nahrané.',
      'documents_upload_error': 'Nahrávanie dokumentov zlyhalo.',
      'use_photo': 'Použiť fotku',
      'camera_unavailable':
          'Kameru sa nepodarilo inicializovať. Skúste znova alebo použite iné zariadenie.',
      'camera_busy':
          'Kamera je obsadená alebo nedostupná. Zatvorte iné aplikácie a skúste znova.',
      'camera_access_denied':
          'Prístup ku kamere bol zamietnutý. Povoľte kameru v prehliadači a skúste znova.',
      'camera_error_with_reason':
          'Kameru sa nepodarilo inicializovať. {{reason}}',
      'camera_capture_failed':
          'Obrázok sa nepodarilo zachytiť. Skúste znova alebo použite iné zariadenie.',
      'locale_SK': 'Slovensko (SK)',
      'locale_CZ': 'Česko (CS)',
      'locale_DE': 'Nemecko (DE)',
      'locale_US': 'Spojené štáty (EN)',
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
      'address': 'Address',
      'city': 'City',
      'country': 'Country',
      'zip_code': 'ZIP code',
      'tax_number': 'Tax number',
      'identity_card_number': 'Identity card number',
      'date_of_birth': 'Date of birth',
      'social_security_number': 'Social security number',
      'signing_in': 'Signing in...',
      'login': 'Login',
      'sign_in_by_phone': 'Sign in by phone',
      'send_sign_in_code': 'Send sign-in code',
      'verify_sign_in_code': 'Sign in with code',
      'sign_in_code_required': 'Sign-in code *',
      'sign_in_code_sent': 'Sign-in code was sent to email.',
      'sign_in_code_send_failed': 'Sending sign-in code failed: {{error}}',
      'invalid_sign_in_code': 'Invalid sign-in code.',
      'sign_in_by_email_password': 'Sign in by email/password',
      'sign_in_failed': 'Sign in failed: {{error}}',
      'phone_not_found':
          'Phone number not found. Sign in using email and password.',
      'invalid_email_password': 'Invalid email or password.',
      'signing_up': 'Signing up...',
      'go_to_sign_up': 'Sign up',
      'create_account': 'Create account',
      'sign_up_failed': 'Sign up failed: {{error}}',
      'verification_code_required': 'Verification code *',
      'send_code': 'Send code',
      'code_sent': 'Code was sent to email.',
      'send_code_failed': 'Sending code failed: {{error}}',
      'data_processing_consent_label':
          'I agree with processing of personal and financial data according to the legal notice.',
      'data_processing_consent_link': 'Review legal notice',
      'data_processing_consent_required':
          'You must confirm the legal notice before registration.',
      'account': 'Profile',
      'sign_out': 'Sign out',
      'save_changes': 'Save changes',
      'language_changed': 'Language changed to {{language}}.',
      'profile_updated_success': 'Profile updated.',
      'saving': 'Saving...',
      'update_sign_in_profile': 'Update sign in profile',
      'profile_update_failed': 'Profile update failed: {{error}}',
      'profile_name_changed': 'I see you changed a name, hello {{name}}.',
      'profile_voice_patch_invalid':
          'I did not recognize the profile change. For example, say: Change address to Main Street 12.',
      'profile_voice_patch_recap':
          'Should I change {{field}} to {{value}}? Say Yes to confirm, or No to cancel.',
      'profile_voice_patch_cancelled': 'I cancelled the profile change.',
      'profile_voice_patch_confirm_first_name': 'first name',
      'profile_voice_patch_confirm_last_name': 'last name',
      'profile_voice_patch_confirm_address': 'address',
      'debug_mode': 'Debug mode',
      'debug_mode_description':
          'In debug mode, all logs are written to a file on Android.',
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
      'skip_until_restart': 'Skip to new start',
      'update': 'Update',
      'invalid_release_url': 'Release URL is invalid.',
      'could_not_open_update_page': 'Could not open update page.',
      'update_apk_missing':
          'This release does not include an Android APK. Opening the release page.',
      'update_download_started': 'Downloading update {{latest}}...',
      'update_download_progress':
          'Downloading {{percent}}% ({{received}} / {{total}} MB)',
      'update_download_finishing':
          'Download finished. Preparing installation...',
      'update_install_permission_check':
          'Checking Android install permission for the APK.',
      'update_install_permission_required':
          'Allow installs from this app and return to continue.',
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
      'speech_input_auto_stopped':
          'Speech input paused. Tap the microphone to continue.',
      'speech_send_confirmation_prompt':
          'I have not heard anything else for one minute. Say Send to send the message, or say Cancel everything to clear it.',
      'speech_draft_cancelled': 'I cleared the dictated message.',
      'speaker_output': 'Assistant voice output',
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
      'create_or_select_case_message':
          'Create or select a case before sending messages. For example, you can say: Create a new case with name power of attorney.',
      'failed_to_reach_api': 'Failed to reach API at {{url}}: {{error}}',
      'no_internet_connection':
          'No internet connection. Check your connection and try again.',
      'api_health_failed': 'API reported an unhealthy state: {{error}}',
      'failed_to_reach_api_with_correlation':
          'Failed to reach API at {{url}}: {{error}} (ID: {{id}})',
      'checking_api': 'Checking API...',
      'api_unavailable_title': 'API unavailable',
      'api_retry_in': 'Retrying in {{seconds}} s',
      'retry_now': 'Retry now',
      'request_id_label': 'Correlation ID: {{id}}',
      'show_request_id': 'ID',
      'copy_request_id': 'Copy ID',
      'request_id_copied': 'Correlation ID copied: {{id}}',
      'pdf_not_ready':
          'PDF is not ready yet. Complete the AI discussion first.',
      'pdf_saved_to': 'PDF saved to {{path}}',
      'pdf_download_started': 'PDF download started: {{filename}}',
      'pdf_download_failed': 'Failed to download PDF: {{error}}',
      'document_pdf_offer':
          'I did not show the generated document in chat. Do you want to see it as PDF? Use the Document PDF button.',
      'open_saved_file_failed': 'Could not open the saved file.',
      'downloaded_files_title': 'Downloaded files',
      'downloaded_files_subtitle': 'Choose the file you want to open now.',
      'available_documents_title': 'Documents to download',
      'available_documents_subtitle': 'Choose the document you want to open.',
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
      'case_voice_name_prompt': 'Please say the new case name.',
      'case_voice_created': 'I created a new case {{name}}.',
      'case_voice_created_continue':
          'I created a new case {{name}}. Please continue with your question or upload documents.',
      'case_auto_created':
          'I automatically created a new case {{name}} for this discussion.',
      'case_archive_confirmation':
          'The current case {{name}} will be archived. Do you want me to create a new case? Please answer yes or no.',
      'case_archive_confirmation_named':
          'The current case {{current}} will be archived. Do you want me to create a new case named {{name}}? Please answer yes or no.',
      'case_archive_confirmation_retry':
          'Please answer yes or no. Should I archive the current case and create a new one?',
      'case_archive_cancelled': 'Okay, I will keep the current case active.',
      'case_voice_name_retry':
          'I did not catch the case name clearly enough. Please say the new case name.',
      'rename_case': 'Rename case',
      'save': 'Save',
      'rename_case_failed': 'Failed to rename case: {{error}}',
      'open_case_document': 'Open {{filename}}',
      'no_case_documents': 'This case does not contain documents yet.',
      'document_status_uploaded': 'Uploaded',
      'document_status_processing': 'Processing',
      'document_status_processed': 'Processed',
      'document_status_failed': 'Processing failed',
      'document_status_unknown': 'Unknown status',
      'document_status_ready': 'Text and vector are ready for analysis.',
      'document_status_pending_message':
          'I cannot perform a document operation yet. These documents are still processing: {{documents}}',
      'document_status_report_intro': 'Document status for this case:',
      'document_status_report_empty':
          'This case does not contain documents yet.',
      'case_deleted': 'Case deleted.',
      'delete_case_failed': 'Failed to delete case: {{error}}',
      'select_case': 'Select case',
      'case_history': 'Case history',
      'case_documents': 'Case documents',
      'case_validation_title': 'Case validation',
      'validation_accuracy_label': 'Accuracy',
      'validation_summary_label': 'Validation summary',
      'law_citations_title': 'Relevant legal citations',
      'law_citation_open': 'Open full law',
      'law_citation_effective_from': 'Effective from',
      'law_citation_version': 'Version',
      'law_citation_open_failed': 'Could not open the law file.',
      'knowledge_updated_label': 'Legal data updated',
      'model_version_label': 'Model version',
      'law_date_label': 'Law Date',
      'show_next_5_messages': 'Show next 5 messages',
      'download_case_document': 'Download {{filename}}',
      'share_case_document': 'Share {{filename}}',
      'case_document_shared': 'Document was shared.',
      'case_document_share_failed': 'Document share failed: {{error}}',
      'case_document_download_failed':
          'Failed to download case document: {{error}}',
      'attached_document': 'Attached document: {{path}}',
      'clear': 'CLEAR',
      'you': 'You',
      'assistant': 'Assistant',
      'frontend_agent': 'Frontend',
      'backend_agent': 'Backend',
      'frontend_thinking_message': 'Thinking...',
      'backend_processing_fallback_message': 'Processing...',
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
      'documents_uploading': 'Documents are uploading.',
      'documents_uploaded': 'Documents are uploaded.',
      'documents_upload_error': 'Document upload failed.',
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
      'address': 'Adresse',
      'city': 'Stadt',
      'country': 'Land',
      'zip_code': 'PLZ',
      'tax_number': 'Steuernummer',
      'identity_card_number': 'Ausweisnummer',
      'date_of_birth': 'Geburtsdatum',
      'social_security_number': 'Personenkennzahl',
      'signing_in': 'Anmeldung läuft...',
      'login': 'Login',
      'sign_in_by_phone': 'Mit Telefonnummer anmelden',
      'send_sign_in_code': 'Login-Code senden',
      'verify_sign_in_code': 'Mit Code anmelden',
      'sign_in_code_required': 'Login-Code *',
      'sign_in_code_sent': 'Login-Code wurde per E-Mail gesendet.',
      'sign_in_code_send_failed': 'Login-Code senden fehlgeschlagen: {{error}}',
      'invalid_sign_in_code': 'Ungültiger Login-Code.',
      'sign_in_by_email_password': 'Mit E-Mail und Passwort anmelden',
      'sign_in_failed': 'Anmeldung fehlgeschlagen: {{error}}',
      'phone_not_found':
          'Telefonnummer nicht gefunden. Bitte mit E-Mail und Passwort anmelden.',
      'invalid_email_password': 'Ungültige E-Mail oder falsches Passwort.',
      'signing_up': 'Registrierung läuft...',
      'go_to_sign_up': 'Registrieren',
      'create_account': 'Konto erstellen',
      'sign_up_failed': 'Registrierung fehlgeschlagen: {{error}}',
      'verification_code_required': 'Bestätigungscode *',
      'send_code': 'Code senden',
      'code_sent': 'Code wurde per E-Mail gesendet.',
      'send_code_failed': 'Code senden fehlgeschlagen: {{error}}',
      'data_processing_consent_label':
          'Ich stimme der Verarbeitung personenbezogener und finanzieller Daten gemäß Rechtshinweis zu.',
      'data_processing_consent_link': 'Rechtshinweis ansehen',
      'data_processing_consent_required':
          'Bitte bestätigen Sie den Rechtshinweis vor der Registrierung.',
      'account': 'Profile',
      'sign_out': 'Abmelden',
      'save_changes': 'Aenderungen speichern',
      'language_changed': 'Sprache wurde auf {{language}} geaendert.',
      'profile_updated_success': 'Profil wurde aktualisiert.',
      'saving': 'Speichere...',
      'update_sign_in_profile': 'Anmeldeprofil aktualisieren',
      'profile_update_failed': 'Profilaktualisierung fehlgeschlagen: {{error}}',
      'profile_name_changed':
          'Ich sehe, dass Sie den Namen geändert haben. Hallo {{name}}.',
      'profile_voice_patch_invalid':
          'Ich habe die Profiländerung nicht erkannt. Sagen Sie zum Beispiel: Ändere meine Adresse zu Hauptstrasse 12.',
      'profile_voice_patch_recap':
          'Soll ich {{field}} zu {{value}} ändern? Sagen Sie Ja zum Bestätigen oder Nein zum Abbrechen.',
      'profile_voice_patch_cancelled':
          'Ich habe die Profiländerung abgebrochen.',
      'profile_voice_patch_confirm_first_name': 'Vorname',
      'profile_voice_patch_confirm_last_name': 'Nachname',
      'profile_voice_patch_confirm_address': 'Adresse',
      'debug_mode': 'Debug-Modus',
      'debug_mode_description':
          'Im Debug-Modus werden alle Logs in eine Datei auf Android geschrieben.',
      'debug_mode_enabled': 'Debug-Modus aktiviert.',
      'debug_mode_disabled': 'Debug-Modus deaktiviert.',
      'share_logs': 'Logs teilen',
      'logs_shared': 'Log-Freigabe wurde gestartet.',
      'share_logs_failed': 'Logs konnten nicht geteilt werden: {{error}}',
      'subscription': 'Abonnement',
      'subscription_change_requested': 'Abo-Änderung gesendet (pending).',
      'subscription_change_failed': 'Abo-Änderung fehlgeschlagen: {{error}}',
      'subscription_status': 'Status: {{status}}',
      'update_available': 'Update verfügbar',
      'update_body':
          'Eine neuere Version ist verfügbar.\n\n{{current}} -> {{latest}}',
      'later': 'Später',
      'skip_until_restart': 'Bis zum Neustart überspringen',
      'update': 'Aktualisieren',
      'invalid_release_url': 'Release-URL ist ungültig.',
      'could_not_open_update_page':
          'Update-Seite konnte nicht geöffnet werden.',
      'update_apk_missing':
          'Dieses Release enthält keine Android-APK. Die Release-Seite wird geöffnet.',
      'update_download_started': 'Update {{latest}} wird heruntergeladen...',
      'update_download_progress':
          'Download {{percent}}% ({{received}} / {{total}} MB)',
      'update_download_finishing':
          'Download abgeschlossen. Installation wird vorbereitet...',
      'update_install_permission_check':
          'Android-Berechtigung zur APK-Installation wird geprüft.',
      'update_install_permission_required':
          'Erlauben Sie Installationen aus dieser App und kehren Sie zurück.',
      'update_install_started':
          'Android-Installer wurde geöffnet. Bestätigen Sie das Update.',
      'update_download_failed':
          'Das Update konnte nicht heruntergeladen werden: {{error}}',
      'update_install_failed':
          'Das Update konnte nicht gestartet werden: {{error}}',
      'update_install_signature_mismatch':
          'Die Signatur der installierten App unterscheidet sich von der Update-APK. Deinstallieren Sie die aktuelle App und installieren Sie dann die neue Version.',
      'allow_install_unknown_apps':
          'Erlauben Sie Installationen aus dieser App in den Android-Einstellungen und kehren Sie dann zur App zurück.',
      'speech_recognition_error': 'Fehler bei der Spracherkennung: {{error}}',
      'speech_unavailable':
          'Spracherkennung ist auf diesem Gerät nicht verfügbar.',
      'speech_input_toggle_label': 'Spracheingabe',
      'speech_input_enabled': 'Spracheingabe an',
      'speech_input_disabled': 'Spracheingabe aus',
      'speech_input_disabled_message':
          'Spracheingabe ist ausgeschaltet. Aktivieren Sie sie mit der Schaltfläche Spracheingabe.',
      'speech_input_auto_stopped':
          'Die Spracheingabe wurde pausiert. Tippen Sie auf das Mikrofon, um fortzufahren.',
      'speech_send_confirmation_prompt':
          'Ich habe eine Minute lang nichts Weiteres gehört. Sagen Sie Senden, um die Nachricht zu senden, oder Alles abbrechen, um sie zu löschen.',
      'speech_draft_cancelled': 'Ich habe die diktierte Nachricht gelöscht.',
      'speaker_output': 'Sprachausgabe des Assistenten',
      'speaker_voice_label': 'Assistentenstimme',
      'speaker_voice_unavailable':
          'Für die gewählte Sprache ist keine passende Stimme verfügbar.',
      'test_speaker_voice': 'Stimme testen',
      'speaker_test_sample':
          'Guten Tag, ich bin Jurisdicta und dies ist eine Sprachprobe.',
      'no_camera_available': 'Auf diesem Gerät ist keine Kamera verfügbar.',
      'document_added': 'Dokument wurde von der Kamera hinzugefügt.',
      'create_or_select_case':
          'Erstellen oder wählen Sie zuerst einen Fall aus.',
      'create_or_select_case_message':
          'Erstellen oder wählen Sie zuerst einen Fall aus. Sie können zum Beispiel sagen: Erstelle einen neuen Fall mit dem Namen Vollmacht.',
      'failed_to_reach_api':
          'API unter {{url}} konnte nicht erreicht werden: {{error}}',
      'no_internet_connection':
          'Keine Internetverbindung. Prüfen Sie die Verbindung und versuchen Sie es erneut.',
      'api_health_failed': 'API meldet einen ungesunden Status: {{error}}',
      'failed_to_reach_api_with_correlation':
          'API unter {{url}} konnte nicht erreicht werden: {{error}} (ID: {{id}})',
      'checking_api': 'API wird geprüft...',
      'api_unavailable_title': 'API ist nicht verfügbar',
      'api_retry_in': 'Nächster Versuch in {{seconds}} s',
      'retry_now': 'Erneut versuchen',
      'request_id_label': 'Correlation-ID: {{id}}',
      'show_request_id': 'ID',
      'copy_request_id': 'ID kopieren',
      'request_id_copied': 'Correlation-ID kopiert: {{id}}',
      'pdf_not_ready':
          'PDF ist noch nicht bereit. Schließen Sie zuerst die AI-Diskussion ab.',
      'pdf_saved_to': 'PDF gespeichert unter {{path}}',
      'pdf_download_started': 'PDF-Download gestartet: {{filename}}',
      'pdf_download_failed': 'PDF-Download fehlgeschlagen: {{error}}',
      'document_pdf_offer':
          'Ich habe den erzeugten Dokumententext nicht im Chat angezeigt. Möchten Sie ihn als PDF sehen? Verwenden Sie die Schaltfläche PDF Dokument.',
      'open_saved_file_failed':
          'Gespeicherte Datei konnte nicht geöffnet werden.',
      'downloaded_files_title': 'Heruntergeladene Dateien',
      'downloaded_files_subtitle':
          'Wählen Sie die Datei aus, die jetzt geöffnet werden soll.',
      'failed_to_load_cases': 'Fälle konnten nicht geladen werden: {{error}}',
      'failed_to_load_case_history':
          'Fallhistorie konnte nicht geladen werden: {{error}}',
      'maximum_cases':
          'Maximal 5 Fälle erlaubt. Löschen Sie zuerst einen bestehenden Fall.',
      'create_case': 'Fall erstellen',
      'delete_case': 'Fall löschen',
      'case_name': 'Fallname',
      'cancel': 'Abbrechen',
      'create': 'Erstellen',
      'case_created': 'Fall wurde erstellt.',
      'case_voice_name_prompt': 'Bitte sagen Sie den Namen des neuen Falls.',
      'case_voice_created': 'Ich habe einen neuen Fall {{name}} erstellt.',
      'case_voice_created_continue':
          'Ich habe einen neuen Fall {{name}} erstellt. Bitte fahren Sie mit Ihrer Frage fort oder laden Sie Dokumente hoch.',
      'case_auto_created':
          'Ich habe für diese Diskussion automatisch einen neuen Fall {{name}} erstellt.',
      'case_archive_confirmation':
          'Der aktuelle Fall {{name}} wird archiviert. Soll ich einen neuen Fall erstellen? Bitte antworten Sie mit Ja oder Nein.',
      'case_archive_confirmation_named':
          'Der aktuelle Fall {{current}} wird archiviert. Soll ich einen neuen Fall mit dem Namen {{name}} erstellen? Bitte antworten Sie mit Ja oder Nein.',
      'case_archive_confirmation_retry':
          'Bitte antworten Sie mit Ja oder Nein. Soll ich den aktuellen Fall archivieren und einen neuen erstellen?',
      'case_archive_cancelled':
          'In Ordnung, ich lasse den aktuellen Fall aktiv.',
      'case_voice_name_retry':
          'Ich habe den Fallnamen nicht klar genug verstanden. Bitte sagen Sie den Namen des neuen Falls.',
      'rename_case': 'Fall umbenennen',
      'save': 'Speichern',
      'rename_case_failed': 'Umbenennen des Falls fehlgeschlagen: {{error}}',
      'open_case_document': '{{filename}} öffnen',
      'no_case_documents': 'Dieser Fall enthält noch keine Dokumente.',
      'document_status_uploaded': 'Hochgeladen',
      'document_status_processing': 'Wird verarbeitet',
      'document_status_processed': 'Verarbeitet',
      'document_status_failed': 'Verarbeitung fehlgeschlagen',
      'document_status_unknown': 'Unbekannter Status',
      'document_status_ready': 'Text und Vektor sind für die Analyse bereit.',
      'document_status_pending_message':
          'Ich kann die Dokumentoperation noch nicht ausführen. Diese Dokumente werden noch verarbeitet: {{documents}}',
      'document_status_report_intro': 'Dokumentstatus für diesen Fall:',
      'document_status_report_empty':
          'Dieser Fall enthält noch keine Dokumente.',
      'case_deleted': 'Fall wurde gelöscht.',
      'delete_case_failed': 'Löschen des Falls fehlgeschlagen: {{error}}',
      'select_case': 'Fall auswählen',
      'case_history': 'Fallhistorie',
      'case_documents': 'Falldokumente',
      'case_validation_title': 'Fallvalidierung',
      'validation_accuracy_label': 'Genauigkeit',
      'validation_summary_label': 'Validierungszusammenfassung',
      'law_citations_title': 'Relevante Gesetzeszitate',
      'law_citation_open': 'Vollständiges Gesetz öffnen',
      'law_citation_effective_from': 'Wirksam ab',
      'law_citation_version': 'Version',
      'law_citation_open_failed':
          'Die Gesetzesdatei konnte nicht geöffnet werden.',
      'knowledge_updated_label': 'Rechtsdaten aktualisiert',
      'model_version_label': 'Modellversion',
      'law_date_label': 'Law Date',
      'show_next_5_messages': 'Weitere 5 Nachrichten zeigen',
      'download_case_document': '{{filename}} herunterladen',
      'share_case_document': '{{filename}} teilen',
      'case_document_shared': 'Dokument wurde geteilt.',
      'case_document_share_failed':
          'Dokument konnte nicht geteilt werden: {{error}}',
      'case_document_download_failed':
          'Download des Dokuments fehlgeschlagen: {{error}}',
      'attached_document': 'Angehängtes Dokument: {{path}}',
      'clear': 'LÖSCHEN',
      'you': 'Sie',
      'assistant': 'Assistent',
      'frontend_agent': 'Frontend',
      'backend_agent': 'Backend',
      'frontend_thinking_message': 'Ich denke nach...',
      'backend_processing_fallback_message': 'Verarbeite Anfrage...',
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
      'speech_input': 'Frage oder Antwort per Sprache hinzufügen',
      'start_ai_discussion': 'AI-Diskussion starten',
      'send_to_api': 'An API senden',
      'capture_document': 'Dokument erfassen',
      'documents_uploading': 'Dokumente werden hochgeladen.',
      'documents_uploaded': 'Dokumente sind hochgeladen.',
      'documents_upload_error':
          'Das Hochladen der Dokumente ist fehlgeschlagen.',
      'use_photo': 'Foto verwenden',
      'camera_unavailable':
          'Kamera konnte nicht initialisiert werden. Bitte erneut versuchen oder ein anderes Gerät verwenden.',
      'camera_busy':
          'Kamera ist belegt oder nicht verfügbar. Schließen Sie andere Apps und versuchen Sie es erneut.',
      'camera_access_denied':
          'Kamerazugriff wurde verweigert. Erlauben Sie den Zugriff im Browser und versuchen Sie es erneut.',
      'camera_error_with_reason':
          'Kamera konnte nicht initialisiert werden. {{reason}}',
      'camera_capture_failed':
          'Bild konnte nicht aufgenommen werden. Bitte erneut versuchen oder ein anderes Gerät verwenden.',
      'locale_SK': 'Slowakei (SK)',
      'locale_CZ': 'Tschechien (CS)',
      'locale_DE': 'Deutschland (DE)',
      'locale_US': 'Vereinigte Staaten (EN)',
    },
  };

  String t(String key,
      [Map<String, String> params = const <String, String>{}]) {
    final bundle =
        _localized[languageCode] ?? _localized[fallbackAppLanguageCode]!;
    var value = bundle[key] ?? _localized[fallbackAppLanguageCode]![key] ?? key;
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
  runApp(
    ProviderScope(
      child: AIJurisdictionMobileApp(
        cameras: cameras,
        logger: logger,
        apiBaseUrl: apiBaseUrl,
      ),
    ),
  );
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
  try {
    final opened = await _savedFileOpener.open(savedPath);
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

class _SavedLocalFile {
  const _SavedLocalFile({
    required this.fileName,
    required this.savedPath,
    required this.contentType,
  });

  final String fileName;
  final String savedPath;
  final String contentType;
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
      title: 'Jurisdigta AI Agent',
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
    this.localId,
  });

  final String role;
  final String content;
  final String? agentName;
  final String? documentPath;
  final DateTime? createdAt;
  final String? localId;
}

const String _caseDocumentsStatusMessageId = 'case-documents-status';
const String _caseValidationMessageId = 'case-validation-status';

class _PendingDocumentUploadBatch {
  const _PendingDocumentUploadBatch({
    required this.caseId,
    required this.uploadedDocIds,
    required this.statusMessageId,
  });

  final String caseId;
  final Set<String> uploadedDocIds;
  final String statusMessageId;
}

class _DocumentUploadWaitResult {
  const _DocumentUploadWaitResult({
    required this.completed,
    required this.hasFailures,
  });

  final bool completed;
  final bool hasFailures;
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

bool _containsDocumentPayloadMarkers(String content) {
  final lowered = content.toLowerCase();
  return lowered.contains('case_update_json') ||
      lowered.contains('```json') ||
      lowered.contains('"case_update"') ||
      lowered.contains('"document_ready"');
}

bool _looksLikeGeneratedDocumentDraft(String content) {
  final trimmed = content.trim();
  if (trimmed.isEmpty) {
    return false;
  }
  final lines = trimmed
      .split('\n')
      .map((line) => line.trim())
      .where((line) => line.isNotEmpty)
      .toList();
  if (lines.length < 6) {
    return false;
  }
  final lowered = trimmed.toLowerCase();
  final hasDocumentKeyword = <String>[
    'splnomocnenie',
    'plna moc',
    'zmluva',
    'dohoda',
    'agreement',
    'power of attorney',
    'contract',
    'memorandum',
    'petition',
    'declaration',
    'vollmacht',
    'vertrag',
    'erklaerung',
    'document',
  ].any(lowered.contains);
  final hasStructuredSections = <String>[
        '1.',
        '2.',
        'i.',
        'ii.',
        'clanok',
        'article',
        'section',
        'abschnitt',
      ].where(lowered.contains).length >=
      2;
  return trimmed.length >= 350 && (hasDocumentKeyword || hasStructuredSections);
}

String _documentAutoAnalysisPrompt({
  required String languageCode,
  required String countryCode,
}) {
  final normalized = _normalizeLanguageCode(languageCode);
  if (normalized == 'SK') {
    return 'Prosim zhrn a analyzuj vsetky nahrane dokumenty podla prava $countryCode. '
        'Vypis pravne problemy, rozpory, rizika, chybajuce udaje alebo chybajuce casti. '
        'Ak je dokument zastarany oproti novsej pravnej uprave, vysvetli co treba aktualizovat.';
  }
  if (normalized == 'GE') {
    return 'Bitte fasse alle hochgeladenen Dokumente nach dem Recht von $countryCode zusammen und analysiere sie. '
        'Nenne rechtliche Probleme, Widersprueche, Risiken sowie fehlende Angaben oder fehlende Teile. '
        'Wenn ein Dokument gegenueber neuerem Recht veraltet ist, erklaere bitte, was aktualisiert werden muss.';
  }
  return 'Please summarize and analyze all uploaded documents under $countryCode law. '
      'List legal problems, inconsistencies, risks, missing information, and missing clauses. '
      'If any uploaded text is outdated compared with newer law, explain what should be updated.';
}

bool _isInternalDocumentAutoAnalysisPrompt(String content) {
  final trimmed = content.trim();
  if (trimmed.isEmpty) {
    return false;
  }
  return trimmed.startsWith(
        'Please summarize and analyze all uploaded documents under ',
      ) ||
      trimmed.startsWith(
        'Prosim zhrn a analyzuj vsetky nahrane dokumenty podla prava ',
      ) ||
      trimmed.startsWith(
        'Bitte fasse alle hochgeladenen Dokumente nach dem Recht von ',
      );
}

String _formatSessionTimestamp(String? value) {
  if (value == null || value.trim().isEmpty) {
    return '-';
  }
  final parsed = DateTime.tryParse(value.trim());
  if (parsed == null) {
    return value.trim();
  }
  final local = parsed.toLocal();
  final year = local.year.toString().padLeft(4, '0');
  final month = local.month.toString().padLeft(2, '0');
  final day = local.day.toString().padLeft(2, '0');
  final hour = local.hour.toString().padLeft(2, '0');
  final minute = local.minute.toString().padLeft(2, '0');
  return '$year-$month-$day $hour:$minute';
}

String _formatFooterLawDate(String? value) {
  return _formatSessionTimestamp(value);
}

String _formatAccuracy(double? value) {
  if (value == null) {
    return '-';
  }
  return '${value.toStringAsFixed(1)}%';
}

double? _parseDoubleValue(Object? value) {
  if (value is num) {
    return value.toDouble();
  }
  if (value is String) {
    return double.tryParse(value);
  }
  return null;
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

  ChatMessage? toChatMessage() {
    if (role.toLowerCase() == 'user' &&
        _isInternalDocumentAutoAnalysisPrompt(content)) {
      return null;
    }
    final visibleContent = role.toLowerCase() == 'assistant'
        ? stripInternalGeneratedDocumentNotice(content)
        : content;
    if (visibleContent.trim().isEmpty) {
      return null;
    }
    return ChatMessage(
      role: role,
      content: visibleContent,
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
    required this.processingStatus,
    this.processingError,
    this.processedAt,
    required this.createdAt,
  });

  final String docId;
  final String kind;
  final int version;
  final String originalFilename;
  final String processingStatus;
  final String? processingError;
  final String? processedAt;
  final String createdAt;

  bool get isProcessed => processingStatus.toLowerCase() == 'processed';

  static CaseDocumentItem fromJson(Map<String, dynamic> json) {
    return CaseDocumentItem(
      docId: json['doc_id'] as String? ?? '',
      kind: json['kind'] as String? ?? '',
      version: json['version'] as int? ?? 0,
      originalFilename: json['original_filename'] as String? ?? 'document',
      processingStatus: json['processing_status'] as String? ?? 'uploaded',
      processingError: json['processing_error'] as String?,
      processedAt: json['processed_at'] as String?,
      createdAt: json['created_at'] as String? ?? '',
    );
  }
}

class CaseDocumentContext {
  const CaseDocumentContext({
    required this.processedDocuments,
    required this.unprocessedDocuments,
  });

  final List<String> processedDocuments;
  final List<String> unprocessedDocuments;

  static CaseDocumentContext fromJson(Map<String, dynamic> json) {
    final processed =
        (json['processed_documents'] as List<dynamic>? ?? const <dynamic>[])
            .whereType<String>()
            .toList();
    final unprocessed =
        (json['unprocessed_documents'] as List<dynamic>? ?? const <dynamic>[])
            .whereType<String>()
            .toList();
    return CaseDocumentContext(
      processedDocuments: processed,
      unprocessedDocuments: unprocessed,
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

class CaseEditDialogResult {
  const CaseEditDialogResult({
    this.renamedTitle,
    this.documentToOpen,
  });

  final String? renamedTitle;
  final CaseDocumentItem? documentToOpen;
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

class DocumentExportOption {
  const DocumentExportOption({
    required this.index,
    required this.filename,
    required this.title,
  });

  final int index;
  final String filename;
  final String title;

  static DocumentExportOption fromJson(Map<String, dynamic> json) {
    return DocumentExportOption(
      index: json['index'] as int? ?? 0,
      filename: json['filename'] as String? ?? 'document.pdf',
      title: json['title'] as String? ?? 'Document',
    );
  }
}

class _DocumentDownloadOption {
  const _DocumentDownloadOption.sessionExport(this.export)
      : caseDocument = null;

  const _DocumentDownloadOption.caseDocument(this.caseDocument) : export = null;

  final DocumentExportOption? export;
  final CaseDocumentItem? caseDocument;

  String get title => export?.title ?? caseDocument?.originalFilename ?? '';

  String get subtitle =>
      export?.filename ?? caseDocument?.processingStatus ?? '';
}

class SessionResultDetails {
  const SessionResultDetails({
    required this.finalRecommendation,
    required this.judgeRationale,
    required this.documentReady,
    required this.validationAccuracy,
    required this.validationSummary,
    required this.knowledgeLastUpdatedAt,
    required this.coreVersion,
    required this.lawCitations,
  });

  final String finalRecommendation;
  final String judgeRationale;
  final bool documentReady;
  final double? validationAccuracy;
  final String? validationSummary;
  final String? knowledgeLastUpdatedAt;
  final String? coreVersion;
  final List<LawCitationDetails> lawCitations;

  bool get hasValidationData =>
      validationAccuracy != null ||
      (validationSummary != null && validationSummary!.trim().isNotEmpty) ||
      (knowledgeLastUpdatedAt != null &&
          knowledgeLastUpdatedAt!.trim().isNotEmpty) ||
      (coreVersion != null && coreVersion!.trim().isNotEmpty);

  static SessionResultDetails fromJson(Map<String, dynamic> json) {
    final metadata = Map<String, dynamic>.from(
      json['metadata'] as Map? ?? const <String, dynamic>{},
    );
    final rawLawCitations =
        metadata['law_citations'] as List? ?? const <Object>[];
    return SessionResultDetails(
      finalRecommendation: json['final_recommendation'] as String? ?? '',
      judgeRationale: json['judge_rationale'] as String? ?? '',
      documentReady: metadata['document_ready'] == true,
      validationAccuracy: _parseDoubleValue(metadata['validation_accuracy']),
      validationSummary: metadata['validation_summary'] as String?,
      knowledgeLastUpdatedAt: metadata['knowledge_last_updated_at'] as String?,
      coreVersion: metadata['core_version'] as String?,
      lawCitations: rawLawCitations
          .whereType<Map>()
          .map((item) => LawCitationDetails.fromJson(
                Map<String, dynamic>.from(item.cast<String, dynamic>()),
              ))
          .toList(),
    );
  }
}

class LawCitationDetails {
  const LawCitationDetails({
    required this.label,
    required this.summary,
    required this.openUrl,
    required this.officialSourceUrl,
    required this.effectiveFrom,
    required this.versionToken,
  });

  final String label;
  final String summary;
  final String openUrl;
  final String officialSourceUrl;
  final String effectiveFrom;
  final String versionToken;

  static LawCitationDetails fromJson(Map<String, dynamic> json) {
    return LawCitationDetails(
      label: json['label'] as String? ?? '',
      summary: json['summary'] as String? ?? '',
      openUrl: json['open_url'] as String? ?? '',
      officialSourceUrl: json['official_source_url'] as String? ?? '',
      effectiveFrom: json['effective_from'] as String? ?? '',
      versionToken: json['version_token'] as String? ?? '',
    );
  }
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
        'processing_purpose': action,
        'trace_id': _flowCorrelationId,
        'request_id': requestId,
        'method': 'POST',
        'url': uri.toString(),
        'headers': _headersForLog(requestId),
        'payload_metadata': _payloadMetadata(payload),
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
          'processing_purpose': action,
          'trace_id': _lastCorrelationId ?? _flowCorrelationId,
          'request_id': requestId,
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
          'processing_purpose': action,
          'url': uri.toString(),
          'trace_id': _flowCorrelationId,
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
        'processing_purpose': action,
        'trace_id': _flowCorrelationId,
        'request_id': requestId,
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
          'processing_purpose': action,
          'trace_id': _lastCorrelationId ?? _flowCorrelationId,
          'request_id': requestId,
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
          'processing_purpose': action,
          'url': uri.toString(),
          'trace_id': _flowCorrelationId,
          'correlation_id': _flowCorrelationId,
          'request_id': requestId,
        },
      );
      rethrow;
    }
  }

  Map<String, Object?> _payloadMetadata(Map<String, Object?> payload) {
    return <String, Object?>{
      'field_count': payload.length,
      'fields': payload.keys.toList(growable: false),
      if (payload['content'] is String)
        'content_length': (payload['content'] as String).length,
      if (payload['message'] is String)
        'message_length': (payload['message'] as String).length,
    };
  }

  Future<ApiHealthCheckResult> checkHealth() async {
    try {
      final response = await _get(
        path: '/health',
        action: 'health_check',
      );
      return parseApiHealthCheckResult(
        statusCode: response.statusCode,
        responseBody: response.body,
      );
    } catch (error) {
      return ApiHealthCheckResult.unhealthy(
        errorMessage: '$error',
        isNetworkError: true,
        isOfflineError: _isOfflineError(error),
      );
    }
  }

  Future<ApiSystemVersionInfo> fetchApiSystemVersionInfo({
    required String countryCode,
  }) async {
    final payload = await _fetchVersionPayload();
    final normalizedCountryCode = countryCode.trim().toLowerCase();
    final countryPayload = _versionCountryPayload(
      payload: payload,
      countryCode: normalizedCountryCode,
    );
    final rawLastLawUpdateDate = _optionalTrimmedString(
      countryPayload['last_law_update_date'],
    );
    final rawModelKnowledgeCutoffDate = _optionalTrimmedString(
      countryPayload['model_knowledge_cutoff_date'],
    );
    return ApiSystemVersionInfo(
      countryCode: countryCode.trim().toUpperCase(),
      lastLawUpdateDate:
          rawLastLawUpdateDate == null || rawLastLawUpdateDate.isEmpty
              ? null
              : rawLastLawUpdateDate,
      modelKnowledgeCutoffDate: rawModelKnowledgeCutoffDate == null ||
              rawModelKnowledgeCutoffDate.isEmpty
          ? null
          : rawModelKnowledgeCutoffDate,
    );
  }

  Future<MobileAppUpdateInfo?> fetchMobileAppUpdateInfo({
    required SemanticVersion installed,
  }) async {
    final payload = await _fetchVersionPayload();
    final releaseUrl =
        (payload['mobile_app_release_url'] as String? ?? '').trim();
    final rawApkDownloadUrl =
        (payload['mobile_app_apk_download_url'] as String?)?.trim();
    final apkDownloadUrl =
        rawApkDownloadUrl == null || rawApkDownloadUrl.isEmpty
            ? null
            : rawApkDownloadUrl;
    final githubRelease = await _fetchLatestGithubReleaseInfo(
      releaseUrl: releaseUrl,
    );
    if (githubRelease != null) {
      if (!githubRelease.isMobileAppRelease ||
          githubRelease.version.compareTo(installed) <= 0) {
        return null;
      }
      return MobileAppUpdateInfo(
        version: githubRelease.version,
        releaseUrl: githubRelease.releaseUrl,
        apkDownloadUrl: githubRelease.apkDownloadUrl,
      );
    }
    final versionValue = payload['mobile_app_version'] as String? ?? '';
    final latestVersion = SemanticVersion.tryParse(versionValue);
    if (latestVersion == null ||
        latestVersion.compareTo(installed) <= 0 ||
        apkDownloadUrl == null) {
      return null;
    }
    return MobileAppUpdateInfo(
      version: latestVersion,
      releaseUrl: releaseUrl,
      apkDownloadUrl: apkDownloadUrl,
    );
  }

  Future<Map<String, dynamic>> _fetchVersionPayload() async {
    final response = await _get(
      path: '/version',
      action: 'version_check',
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception(
          'Version check failed with status ${response.statusCode}.');
    }
    return _decodeResponseBody(response, action: 'version_check');
  }

  Map<String, dynamic> _versionCountryPayload({
    required Map<String, dynamic> payload,
    required String countryCode,
  }) {
    final lawsByCountry = payload['laws_by_country'];
    if (lawsByCountry is Map) {
      final nested = lawsByCountry[countryCode];
      if (nested is Map<String, dynamic>) {
        return nested;
      }
      if (nested is Map) {
        return Map<String, dynamic>.from(nested);
      }
    }
    return payload;
  }

  String? _optionalTrimmedString(Object? value) {
    final normalized = (value as String?)?.trim();
    if (normalized == null || normalized.isEmpty) {
      return null;
    }
    return normalized;
  }

  Future<GithubReleaseInfo?> _fetchLatestGithubReleaseInfo({
    required String releaseUrl,
  }) async {
    final githubApiUri = githubLatestReleaseApiUriFromReleaseUrl(releaseUrl);
    if (githubApiUri == null) {
      return null;
    }

    await logger.info(
      'GitHub release check request',
      <String, Object?>{
        'url': githubApiUri.toString(),
      },
    );
    try {
      final response = await http.get(
        githubApiUri,
        headers: const <String, String>{
          'Accept': 'application/vnd.github+json',
          'User-Agent': 'aijurisdiction-mobile',
        },
      );
      await logger.info(
        'GitHub release check response',
        <String, Object?>{
          'status_code': response.statusCode,
          'content_type': response.headers['content-type'],
          'bytes': response.bodyBytes.length,
        },
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return null;
      }
      return parseGithubReleaseResponseBody(response.body);
    } catch (error, stackTrace) {
      await logger.error(
        'GitHub release check failed',
        error,
        stackTrace,
        <String, Object?>{
          'url': githubApiUri.toString(),
        },
      );
      return null;
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

  Stream<StreamEvent> startReadUserTurnStream({
    required String instruction,
    required LocaleOption locale,
    required double questionTimeoutSeconds,
    required double maxDiscussionMinutes,
    required double communicationMinutes,
    String? documentPath,
  }) async* {
    final payload = <String, Object?>{
      'instruction': instruction,
      'documents': <Object?>[],
      'question_timeout_seconds': questionTimeoutSeconds,
      'max_discussion_minutes': maxDiscussionMinutes,
      'communication_minutes': communicationMinutes,
      'user_simulation_mode': 'ReadUser',
    };
    if (documentPath != null && documentPath.trim().isNotEmpty) {
      await logger.info(
        'ReadUser turn stream started with local document path context',
        <String, Object?>{'document_path': documentPath},
      );
    }

    for (var attempt = 0; attempt < 2; attempt++) {
      final sessionId = await _ensureSession(
        responderMode: ResponderMode.realPerson,
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
          'action': 'read_user_turn_stream',
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
              'action': 'read_user_turn_stream',
              'attempt': attempt + 1,
              'status_code': response.statusCode,
              'detail': detail,
            },
          );
          if (response.statusCode == 404 && _isMissingSessionDetail(detail)) {
            await _recreateSessionAfterMissing(
              operation: 'read_user_turn_stream',
              missingSessionId: sessionId,
              responderMode: ResponderMode.realPerson,
              locale: locale,
            );
            if (attempt == 0) {
              continue;
            }
            throw const SessionExpiredException();
          }
          throw Exception(
            'ReadUser turn stream failed with status ${response.statusCode}: $detail',
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
                  'action': 'read_user_turn_stream',
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
                'action': 'read_user_turn_stream',
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
            'action': 'read_user_turn_stream',
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

    final utf8Match = RegExp(
      r"filename\*=UTF-8''([^;]+)",
      caseSensitive: false,
    ).firstMatch(headerValue);
    if (utf8Match != null) {
      final encoded = utf8Match.group(1)?.trim();
      if (encoded != null && encoded.isNotEmpty) {
        return Uri.decodeComponent(encoded).trim();
      }
    }

    final quotedMatch = RegExp(
      r'filename="([^"]+)"',
      caseSensitive: false,
    ).firstMatch(headerValue);
    if (quotedMatch != null) {
      final quoted = quotedMatch.group(1)?.trim();
      if (quoted != null && quoted.isNotEmpty) {
        return quoted;
      }
    }

    final plainMatch = RegExp(r'filename=([^;]+)', caseSensitive: false)
        .firstMatch(headerValue);
    final plain = plainMatch?.group(1)?.trim();
    if (plain == null || plain.isEmpty) {
      return null;
    }
    return plain.replaceAll('"', '').trim();
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

  Future<List<DocumentExportOption>> listDocumentExportOptions() async {
    final sessionId = _sessionId;
    if (sessionId == null || sessionId.isEmpty) {
      return const <DocumentExportOption>[];
    }
    final response = await _get(
      path: '/v1/chat/sessions/$sessionId/export/documents',
      action: 'list_document_exports',
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = _extractErrorDetail(response);
      throw Exception(
        'Document export list failed with status ${response.statusCode}: $detail',
      );
    }
    final decoded =
        _decodeResponseBody(response, action: 'list_document_exports');
    final rawDocuments =
        decoded['documents'] as List<dynamic>? ?? const <dynamic>[];
    return rawDocuments
        .whereType<Map>()
        .map((item) => DocumentExportOption.fromJson(
              Map<String, dynamic>.from(item.cast<String, dynamic>()),
            ))
        .toList(growable: false);
  }

  Future<ExportFilePayload> downloadDocumentExportPdf({
    required int index,
    required ResponderMode responderMode,
    required LocaleOption locale,
  }) async {
    final sessionId = _sessionId;
    if (sessionId == null || sessionId.isEmpty) {
      throw Exception('No active session. Start a discussion first.');
    }
    final response = await _get(
      path: '/v1/chat/sessions/$sessionId/export/documents/$index',
      action: 'export_document_pdf_$index',
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = _extractErrorDetail(response);
      if (_isMissingSessionDetail(detail)) {
        await _recreateSessionAfterMissing(
          operation: 'export_document_pdf_$index',
          missingSessionId: sessionId,
          responderMode: responderMode,
          locale: locale,
        );
        throw const SessionExpiredException();
      }
      throw Exception(
        'Document PDF export failed with status ${response.statusCode}: $detail',
      );
    }
    final filename = _filenameFromContentDisposition(
          response.headers['content-disposition'],
        ) ??
        'document.pdf';
    return ExportFilePayload(
      bytes: response.bodyBytes,
      filename: filename,
      contentType: response.headers['content-type'] ?? 'application/pdf',
    );
  }

  Future<List<CaseDocumentItem>> uploadCaseDocuments({
    required String caseId,
    required String userId,
    required List<PlatformFile> files,
  }) async {
    final uri = baseUri.resolve('/v1/cases/$caseId/documents?user_id=$userId');
    final requestId = _generateRequestId();
    final request = http.MultipartRequest('POST', uri)
      ..headers.addAll(<String, String>{
        'x-api-key': apiKey,
        'x-correlation-id': _flowCorrelationId,
        'x-request-id': requestId,
      });
    for (final file in files) {
      final filename = file.name.trim().isEmpty ? 'document' : file.name;
      if (file.bytes != null) {
        request.files.add(http.MultipartFile.fromBytes('files', file.bytes!,
            filename: filename));
      } else if (file.path != null && file.path!.isNotEmpty) {
        request.files.add(await http.MultipartFile.fromPath('files', file.path!,
            filename: filename));
      }
    }
    final streamed = await request.send();
    _recordCorrelationId(streamed);
    final response = await http.Response.fromStream(streamed);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = _extractErrorDetail(response);
      throw Exception(
          'Case document upload failed with status ${response.statusCode}: $detail');
    }
    final decoded =
        _decodeResponseBody(response, action: 'case_document_upload');
    final rawUploaded =
        decoded['uploaded'] as List<dynamic>? ?? const <dynamic>[];
    return rawUploaded
        .whereType<Map>()
        .map((value) =>
            CaseDocumentItem.fromJson(Map<String, dynamic>.from(value)))
        .toList();
  }

  Future<CaseDocumentContext> loadCaseDocumentContext({
    required String caseId,
    required String userId,
  }) async {
    final response = await _get(
      path: '/v1/cases/$caseId/documents/context?user_id=$userId',
      action: 'case_document_context',
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception(
          'Case document context failed with status ${response.statusCode}.');
    }
    return CaseDocumentContext.fromJson(
      _decodeResponseBody(response, action: 'case_document_context'),
    );
  }

  Future<List<CaseDocumentItem>> loadCaseDocumentsSnapshot({
    required String caseId,
    required String userId,
  }) async {
    final response = await _get(
      path: '/v1/cases/$caseId/history?user_id=$userId&offset=0&limit=1',
      action: 'case_documents_snapshot',
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception(
          'Case documents snapshot failed with status ${response.statusCode}.');
    }
    return CaseHistoryPage.fromJson(
      _decodeResponseBody(response, action: 'case_documents_snapshot'),
    ).documents;
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

  Future<ExportFilePayload> downloadGeneratedCaseDocumentPdf({
    required String caseId,
    required String userId,
    required String docId,
  }) async {
    final response = await _get(
      path: '/v1/cases/$caseId/documents/$docId/pdf?user_id=$userId',
      action: 'generated_case_document_pdf_download',
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = _extractErrorDetail(response);
      throw Exception(
        'Generated case document PDF download failed with status ${response.statusCode}: $detail',
      );
    }
    final filename = _filenameFromContentDisposition(
          response.headers['content-disposition'],
        ) ??
        'case-document.pdf';
    return ExportFilePayload(
      bytes: response.bodyBytes,
      filename: filename,
      contentType: response.headers['content-type'] ?? 'application/pdf',
    );
  }

  Future<bool> isDocumentExportReady() async {
    final result = await loadSessionResultDetails();
    return result?.documentReady ?? false;
  }

  Future<SessionResultDetails?> loadSessionResultDetails() async {
    final sessionId = _sessionId;
    if (sessionId == null || sessionId.isEmpty) {
      return null;
    }
    final response = await _get(
      path: '/v1/chat/sessions/$sessionId/result',
      action: 'session_result',
    );
    if (response.statusCode == 404) {
      return null;
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = _extractErrorDetail(response);
      throw Exception(
        'Session result lookup failed with status ${response.statusCode}: $detail',
      );
    }
    return SessionResultDetails.fromJson(
      _decodeResponseBody(response, action: 'session_result'),
    );
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
  late final ApiClient _apiClient;
  LocalAuthUser? _currentUser;
  bool _loading = true;
  bool _apiReady = false;
  bool _checkingApi = true;
  String? _apiHealthError;
  bool _apiHealthIsNetworkError = false;
  bool _apiHealthIsOfflineError = false;
  int? _apiHealthRetrySeconds;
  int _apiHealthFailureCount = 0;
  Timer? _apiHealthRetryTimer;

  AppStrings get _strings => AppStrings(_defaultLanguage);

  @override
  void initState() {
    super.initState();
    _authStore = LocalAuthStore(
      baseUri: Uri.parse(widget.apiBaseUrl),
      apiKey: _apiKey,
    );
    _apiClient = ApiClient(
      baseUri: Uri.parse(widget.apiBaseUrl),
      apiKey: _apiKey,
      logger: widget.logger,
    );
    unawaited(_startApiHealthGate());
  }

  Future<void> _loadSession() async {
    final user = await _authStore.getCurrentUser();
    if (!mounted) {
      return;
    }
    ProviderScope.containerOf(context, listen: false)
        .read(signedInUserProvider.notifier)
        .setUser(user);
    setState(() {
      _currentUser = user;
      _loading = false;
    });
  }

  Future<void> _startApiHealthGate() async {
    await _checkApiHealthUntilReady();
  }

  Future<void> _checkApiHealthUntilReady() async {
    _apiHealthRetryTimer?.cancel();
    if (!mounted) {
      return;
    }
    setState(() {
      _checkingApi = true;
      _apiHealthRetrySeconds = null;
    });
    final healthResult = await _apiClient.checkHealth();
    if (!mounted) {
      return;
    }
    if (healthResult.isHealthy) {
      setState(() {
        _apiReady = true;
        _checkingApi = false;
        _apiHealthError = null;
        _apiHealthIsNetworkError = false;
        _apiHealthIsOfflineError = false;
        _apiHealthRetrySeconds = null;
      });
      _apiHealthFailureCount = 0;
      await _loadSession();
      return;
    }
    final retrySeconds = apiHealthRetryDelaySeconds(_apiHealthFailureCount);
    _apiHealthFailureCount += 1;
    setState(() {
      _apiReady = false;
      _checkingApi = false;
      _apiHealthError = healthResult.errorMessage;
      _apiHealthIsNetworkError = healthResult.isNetworkError;
      _apiHealthIsOfflineError = healthResult.isOfflineError;
      _apiHealthRetrySeconds = retrySeconds;
    });
    await widget.logger.info(
      'Startup API health check failed',
      <String, Object?>{
        'api_base_url': widget.apiBaseUrl,
        'error': healthResult.errorMessage,
        'is_network_error': healthResult.isNetworkError,
        'is_offline_error': healthResult.isOfflineError,
        'retry_seconds': retrySeconds,
      },
    );
    _scheduleApiHealthRetry(retrySeconds);
  }

  void _scheduleApiHealthRetry(int retrySeconds) {
    var remaining = retrySeconds;
    _apiHealthRetryTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }
      if (remaining <= 1) {
        timer.cancel();
        unawaited(_checkApiHealthUntilReady());
        return;
      }
      remaining -= 1;
      setState(() {
        _apiHealthRetrySeconds = remaining;
      });
    });
  }

  Widget _buildApiUnavailableScaffold() {
    final errorMessage = _apiHealthError == null
        ? _strings.t('checking_api')
        : _apiHealthIsOfflineError
            ? _strings.t('no_internet_connection')
            : _apiHealthIsNetworkError
                ? _strings.t('failed_to_reach_api', <String, String>{
                    'url': widget.apiBaseUrl,
                    'error': _apiHealthError!,
                  })
                : _strings.t('api_health_failed', <String, String>{
                    'error': _apiHealthError!,
                  });
    return Scaffold(
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (_checkingApi)
                const CircularProgressIndicator()
              else
                const Icon(Icons.cloud_off, size: 56),
              const SizedBox(height: 16),
              Text(
                _checkingApi
                    ? _strings.t('checking_api')
                    : _strings.t('api_unavailable_title'),
                style: Theme.of(context).textTheme.titleLarge,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              Text(
                errorMessage,
                textAlign: TextAlign.center,
              ),
              if (_apiHealthRetrySeconds != null) ...[
                const SizedBox(height: 12),
                Text(
                  _strings.t('api_retry_in', <String, String>{
                    'seconds': '${_apiHealthRetrySeconds!}',
                  }),
                  textAlign: TextAlign.center,
                ),
              ],
              if (!_checkingApi) ...[
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: () {
                    unawaited(_checkApiHealthUntilReady());
                  },
                  child: Text(_strings.t('retry_now')),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _handleSignedIn(LocalAuthUser user) async {
    if (!mounted) {
      return;
    }
    ProviderScope.containerOf(context, listen: false)
        .read(signedInUserProvider.notifier)
        .setUser(user);
    setState(() {
      _currentUser = user;
    });
  }

  Future<void> _handleSignedOut() async {
    await _authStore.signOut();
    if (!mounted) {
      return;
    }
    ProviderScope.containerOf(context, listen: false)
        .read(signedInUserProvider.notifier)
        .setUser(null);
    setState(() {
      _currentUser = null;
    });
  }

  void _handleProfileUpdated(LocalAuthUser user) {
    if (!mounted) {
      return;
    }
    ProviderScope.containerOf(context, listen: false)
        .read(signedInUserProvider.notifier)
        .setUser(user);
    setState(() {
      _currentUser = user;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!_apiReady) {
      return _buildApiUnavailableScaffold();
    }
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

  @override
  void dispose() {
    _apiHealthRetryTimer?.cancel();
    super.dispose();
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
  final DevicePhoneNumberService _devicePhoneNumberService =
      const DevicePhoneNumberService();
  final TextEditingController _signInPhoneController = TextEditingController();
  final TextEditingController _signInCodeController = TextEditingController();
  final TextEditingController _signUpPhoneController = TextEditingController();
  final TextEditingController _signUpEmailController = TextEditingController();
  final TextEditingController _signUpPasswordController =
      TextEditingController();
  final TextEditingController _signUpVerificationCodeController =
      TextEditingController();
  final TextEditingController _signUpFirstNameController =
      TextEditingController();
  final TextEditingController _signUpLastNameController =
      TextEditingController();
  bool _showPhoneOtpSignIn = false;
  bool _dataProcessingConsentAccepted = false;
  bool _isBusy = false;
  String _appVersionLabel = 'v0.1.5+43';
  String? _devicePhoneNumber;
  String? _deviceBindingId;

  AppStrings get _strings => AppStrings(_defaultLanguage);
  bool get _isLocalExecution => _isLocalApiBaseUrl(widget.apiBaseUrl);
  bool get _isAndroidDevice =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;
  bool get _lockPhoneNumberToDevice =>
      _isAndroidDevice &&
      _devicePhoneNumber != null &&
      _devicePhoneNumber!.trim().isNotEmpty;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _tabController.addListener(_handleTabChanged);
    unawaited(_loadInitialPhoneNumbers());
    unawaited(_loadAppVersion());
  }

  @override
  void dispose() {
    _tabController.removeListener(_handleTabChanged);
    _tabController.dispose();
    _signInPhoneController.dispose();
    _signInCodeController.dispose();
    _signUpPhoneController.dispose();
    _signUpEmailController.dispose();
    _signUpPasswordController.dispose();
    _signUpVerificationCodeController.dispose();
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

  Future<void> _loadInitialPhoneNumbers() async {
    final lastPhoneNumber = await widget.authStore.getLastPhoneNumber();
    final devicePhoneNumber =
        await _devicePhoneNumberService.getDevicePhoneNumber();
    final deviceBindingId = await widget.authStore.getOrCreateDeviceBindingId();
    if (!mounted) {
      return;
    }
    setState(() {
      _devicePhoneNumber = devicePhoneNumber;
      _deviceBindingId = deviceBindingId;
    });
    if (devicePhoneNumber != null && devicePhoneNumber.isNotEmpty) {
      _signInPhoneController.text = devicePhoneNumber;
      _signUpPhoneController.text = devicePhoneNumber;
    } else if (lastPhoneNumber != null && lastPhoneNumber.isNotEmpty) {
      _signInPhoneController.text = lastPhoneNumber;
    } else if (_isLocalExecution) {
      _signInPhoneController.text = _localAutofillPhoneNumber;
    }
    if (!_lockPhoneNumberToDevice &&
        _signUpPhoneController.text.trim().isEmpty &&
        _isLocalExecution) {
      _signUpPhoneController.text = _localAutofillPhoneNumber;
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
      final deviceBindingId = _deviceBindingId ??
          await widget.authStore.getOrCreateDeviceBindingId();
      final silentUser = await widget.authStore.signInByDeviceToken(
        phoneNumber: _signInPhoneController.text,
        deviceId: deviceBindingId,
      );
      if (silentUser != null) {
        await widget.logger.info(
          'User signed in by device-bound token',
          <String, Object?>{'phone': silentUser.phoneNumber},
        );
        widget.onSignedIn(silentUser);
        return;
      }
      await widget.authStore.sendSignInCode(
        phoneNumber: _signInPhoneController.text,
        deviceId: deviceBindingId,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _showPhoneOtpSignIn = true;
      });
      _showSnackbar(_strings.t('sign_in_code_sent'));
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Sign-in by phone failed',
        error,
        stackTrace,
      );
      _showSnackbar(_strings.t('sign_in_code_send_failed', <String, String>{
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

  Future<void> _signInByPhoneOtp() async {
    if (_isBusy) {
      return;
    }
    setState(() {
      _isBusy = true;
    });
    try {
      final deviceBindingId = _deviceBindingId ??
          await widget.authStore.getOrCreateDeviceBindingId();
      final user = await widget.authStore.signInByPhoneOtp(
        phoneNumber: _signInPhoneController.text,
        verificationCode: _signInCodeController.text,
        deviceId: deviceBindingId,
      );
      if (user == null) {
        _showSnackbar(_strings.t('invalid_sign_in_code'));
        return;
      }
      widget.onSignedIn(user);
    } catch (error, stackTrace) {
      await widget.logger
          .error('Sign-in by phone OTP failed', error, stackTrace);
      _showSnackbar(
          _strings.t('sign_in_failed', <String, String>{'error': '$error'}));
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
    if (!_dataProcessingConsentAccepted) {
      _showSnackbar(_strings.t('data_processing_consent_required'));
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
          verificationCode: _signUpVerificationCodeController.text,
          firstName: _signUpFirstNameController.text,
          lastName: _signUpLastNameController.text,
          dataProcessingConsentAccepted: _dataProcessingConsentAccepted,
          dataProcessingConsentVersion: _dataProcessingConsentVersion,
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

  Future<void> _sendRegistrationCode() async {
    if (_isBusy) {
      return;
    }
    setState(() {
      _isBusy = true;
    });
    try {
      await widget.authStore.sendRegistrationCode(
        email: _signUpEmailController.text,
      );
      _showSnackbar(_strings.t('code_sent'));
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Send registration code failed',
        error,
        stackTrace,
      );
      _showSnackbar(_strings.t('send_code_failed', <String, String>{
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
          const Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: <Color>[
                    Color(0xFF041B59),
                    Color(0xFF1388E9),
                    Color(0xFF041B59),
                  ],
                ),
              ),
            ),
          ),
          SafeArea(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final mediaQuery = MediaQuery.of(context);
                final isPortrait =
                    mediaQuery.orientation == Orientation.portrait;
                final authPanelHeight = max(
                  360.0,
                  min(
                    constraints.maxHeight - (isPortrait ? 220 : 180),
                    560.0,
                  ),
                );
                return SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  child: ConstrainedBox(
                    constraints: BoxConstraints(
                      minHeight: max(0, constraints.maxHeight - 32),
                    ),
                    child: Center(
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 560),
                        child: Card(
                          margin: const EdgeInsets.symmetric(horizontal: 16),
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
                                          ?.copyWith(
                                            color: const Color(0xFF4A628A),
                                          ),
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
                                  height: authPanelHeight,
                                  child: AutofillGroup(
                                    child: TabBarView(
                                      controller: _tabController,
                                      children: [
                                        SingleChildScrollView(
                                          child: Column(
                                            children: [
                                              TextField(
                                                controller:
                                                    _signInPhoneController,
                                                keyboardType:
                                                    TextInputType.phone,
                                                readOnly:
                                                    _lockPhoneNumberToDevice,
                                                canRequestFocus:
                                                    !_lockPhoneNumberToDevice,
                                                enableInteractiveSelection:
                                                    !_lockPhoneNumberToDevice,
                                                autofillHints: const <String>[
                                                  AutofillHints.telephoneNumber,
                                                  AutofillHints
                                                      .telephoneNumberDevice,
                                                  AutofillHints.username,
                                                ],
                                                decoration:
                                                    const InputDecoration()
                                                        .copyWith(
                                                  labelText:
                                                      strings.t('phone_number'),
                                                  hintText: _isLocalExecution
                                                      ? strings.t(
                                                          'phone_number_hint',
                                                        )
                                                      : null,
                                                  suffixIcon:
                                                      _lockPhoneNumberToDevice
                                                          ? const Icon(
                                                              Icons
                                                                  .lock_outline,
                                                            )
                                                          : null,
                                                ),
                                              ),
                                              const SizedBox(height: 12),
                                              SizedBox(
                                                width: double.infinity,
                                                child: FilledButton(
                                                  onPressed: _isBusy
                                                      ? null
                                                      : _signInByPhone,
                                                  child: Text(
                                                    _isBusy
                                                        ? strings
                                                            .t('signing_in')
                                                        : strings.t(
                                                            'send_sign_in_code',
                                                          ),
                                                  ),
                                                ),
                                              ),
                                              if (_showPhoneOtpSignIn) ...[
                                                const SizedBox(height: 16),
                                                const Divider(),
                                                const SizedBox(height: 8),
                                                TextField(
                                                  controller:
                                                      _signInCodeController,
                                                  keyboardType:
                                                      TextInputType.number,
                                                  autofillHints: const <String>[
                                                    AutofillHints.oneTimeCode,
                                                  ],
                                                  textAlignVertical:
                                                      TextAlignVertical.top,
                                                  decoration: InputDecoration(
                                                    labelText: strings.t(
                                                      'sign_in_code_required',
                                                    ),
                                                  ),
                                                ),
                                                const SizedBox(height: 12),
                                                SizedBox(
                                                  width: double.infinity,
                                                  child: OutlinedButton(
                                                    onPressed: _isBusy
                                                        ? null
                                                        : _signInByPhoneOtp,
                                                    child: Text(
                                                      strings.t(
                                                        'verify_sign_in_code',
                                                      ),
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
                                                controller:
                                                    _signUpPhoneController,
                                                keyboardType:
                                                    TextInputType.phone,
                                                readOnly:
                                                    _lockPhoneNumberToDevice,
                                                canRequestFocus:
                                                    !_lockPhoneNumberToDevice,
                                                enableInteractiveSelection:
                                                    !_lockPhoneNumberToDevice,
                                                autofillHints: const <String>[
                                                  AutofillHints.telephoneNumber,
                                                  AutofillHints
                                                      .telephoneNumberDevice,
                                                ],
                                                textAlignVertical:
                                                    TextAlignVertical.top,
                                                decoration: InputDecoration(
                                                  labelText: strings.t(
                                                    'phone_number_required',
                                                  ),
                                                  suffixIcon:
                                                      _lockPhoneNumberToDevice
                                                          ? const Icon(
                                                              Icons
                                                                  .lock_outline,
                                                            )
                                                          : null,
                                                ),
                                              ),
                                              const SizedBox(height: 12),
                                              TextField(
                                                controller:
                                                    _signUpEmailController,
                                                keyboardType:
                                                    TextInputType.emailAddress,
                                                autofillHints: const <String>[
                                                  AutofillHints.email,
                                                  AutofillHints.newUsername,
                                                ],
                                                textAlignVertical:
                                                    TextAlignVertical.top,
                                                decoration: InputDecoration(
                                                  labelText: strings.t(
                                                    'email_required',
                                                  ),
                                                ),
                                              ),
                                              const SizedBox(height: 12),
                                              TextField(
                                                controller:
                                                    _signUpPasswordController,
                                                obscureText: true,
                                                autofillHints: const <String>[
                                                  AutofillHints.newPassword,
                                                ],
                                                textAlignVertical:
                                                    TextAlignVertical.top,
                                                decoration: InputDecoration(
                                                  labelText: strings.t(
                                                    'password_required',
                                                  ),
                                                ),
                                              ),
                                              const SizedBox(height: 12),
                                              Row(
                                                children: [
                                                  Expanded(
                                                    child: TextField(
                                                      controller:
                                                          _signUpVerificationCodeController,
                                                      keyboardType:
                                                          TextInputType.number,
                                                      decoration:
                                                          InputDecoration(
                                                        labelText: strings.t(
                                                          'verification_code_required',
                                                        ),
                                                      ),
                                                    ),
                                                  ),
                                                  const SizedBox(width: 8),
                                                  FilledButton.tonal(
                                                    onPressed: _isBusy
                                                        ? null
                                                        : _sendRegistrationCode,
                                                    child: Text(
                                                      strings.t('send_code'),
                                                    ),
                                                  ),
                                                ],
                                              ),
                                              const SizedBox(height: 12),
                                              TextField(
                                                controller:
                                                    _signUpFirstNameController,
                                                textAlignVertical:
                                                    TextAlignVertical.top,
                                                decoration: InputDecoration(
                                                  labelText: strings.t(
                                                    'first_name_optional',
                                                  ),
                                                ),
                                              ),
                                              const SizedBox(height: 12),
                                              TextField(
                                                controller:
                                                    _signUpLastNameController,
                                                textAlignVertical:
                                                    TextAlignVertical.top,
                                                decoration: InputDecoration(
                                                  labelText: strings.t(
                                                    'last_name_optional',
                                                  ),
                                                ),
                                              ),
                                              const SizedBox(height: 16),
                                              CheckboxListTile(
                                                contentPadding: EdgeInsets.zero,
                                                value:
                                                    _dataProcessingConsentAccepted,
                                                onChanged: (value) {
                                                  setState(() {
                                                    _dataProcessingConsentAccepted =
                                                        value ?? false;
                                                  });
                                                },
                                                title: Text(strings.t(
                                                  'data_processing_consent_label',
                                                )),
                                              ),
                                              Align(
                                                alignment: Alignment.centerLeft,
                                                child: TextButton(
                                                  onPressed: () {
                                                    launchUrl(
                                                      Uri.parse(
                                                        _dataProcessingNoticeUrl,
                                                      ),
                                                      mode: LaunchMode
                                                          .externalApplication,
                                                    );
                                                  },
                                                  child: Text(
                                                    strings.t(
                                                      'data_processing_consent_link',
                                                    ),
                                                  ),
                                                ),
                                              ),
                                              const SizedBox(height: 8),
                                              SizedBox(
                                                width: double.infinity,
                                                child: FilledButton(
                                                  onPressed:
                                                      _isBusy ? null : _signUp,
                                                  child: Text(
                                                    _isBusy
                                                        ? strings
                                                            .t('signing_up')
                                                        : strings.t(
                                                            'create_account',
                                                          ),
                                                  ),
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                );
              },
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
    required this.speakerOutputEnabled,
    required this.onSpeakerOutputChanged,
    required this.onLocaleChanged,
    required this.logger,
  });

  final LocalAuthUser user;
  final LocalAuthStore authStore;
  final LocaleOption selectedLocale;
  final List<LocaleOption> locales;
  final JurisdictaSpeaker speaker;
  final bool speakerOutputEnabled;
  final Future<void> Function(bool enabled) onSpeakerOutputChanged;
  final Future<void> Function(LocaleOption locale) onLocaleChanged;
  final AppLogger logger;

  @override
  State<AccountSettingsPage> createState() => _AccountSettingsPageState();
}

class _AccountSettingsPageState extends State<AccountSettingsPage> {
  late final TextEditingController _phoneController;
  late final TextEditingController _emailController;
  late final TextEditingController _passwordController;
  late final TextEditingController _firstNameController;
  late final TextEditingController _lastNameController;
  late final TextEditingController _addressController;
  late final TextEditingController _cityController;
  late final TextEditingController _countryController;
  late final TextEditingController _zipCodeController;
  late final TextEditingController _taxNumberController;
  late final TextEditingController _identityCardNumberController;
  late final TextEditingController _dateOfBirthController;
  late final TextEditingController _socialSecurityNumberController;
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
  late bool _speakerOutputEnabled;
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
    _emailController = TextEditingController(text: widget.user.email);
    _passwordController = TextEditingController(text: widget.user.password);
    _firstNameController =
        TextEditingController(text: widget.user.firstName ?? '');
    _lastNameController =
        TextEditingController(text: widget.user.lastName ?? '');
    _addressController = TextEditingController(text: widget.user.address ?? '');
    _cityController = TextEditingController(text: widget.user.city ?? '');
    _countryController = TextEditingController(text: widget.user.country ?? '');
    _zipCodeController = TextEditingController(text: widget.user.zipCode ?? '');
    _taxNumberController =
        TextEditingController(text: widget.user.taxNumber ?? '');
    _identityCardNumberController =
        TextEditingController(text: widget.user.identityCardNumber ?? '');
    _dateOfBirthController =
        TextEditingController(text: widget.user.dateOfBirth ?? '');
    _socialSecurityNumberController =
        TextEditingController(text: widget.user.socialSecurityNumber ?? '');
    _selectedLocale = widget.selectedLocale;
    _speakerOutputEnabled = widget.speakerOutputEnabled;
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

  Future<void> _setSpeakerOutputEnabled(bool enabled) async {
    setState(() {
      _speakerOutputEnabled = enabled;
    });
    await widget.onSpeakerOutputChanged(enabled);
  }

  @override
  void dispose() {
    _phoneController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _firstNameController.dispose();
    _lastNameController.dispose();
    _addressController.dispose();
    _cityController.dispose();
    _countryController.dispose();
    _zipCodeController.dispose();
    _taxNumberController.dispose();
    _identityCardNumberController.dispose();
    _dateOfBirthController.dispose();
    _socialSecurityNumberController.dispose();
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
          address: _addressController.text,
          city: _cityController.text,
          country: _countryController.text,
          zipCode: _zipCodeController.text,
          taxNumber: _taxNumberController.text,
          identityCardNumber: _identityCardNumberController.text,
          dateOfBirth: _dateOfBirthController.text,
          socialSecurityNumber: _socialSecurityNumberController.text,
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
            readOnly: true,
            textAlignVertical: TextAlignVertical.top,
            decoration: InputDecoration(
              labelText: strings.t('phone_number'),
              suffixIcon: const Icon(Icons.lock_outline),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _emailController,
            keyboardType: TextInputType.emailAddress,
            readOnly: true,
            textAlignVertical: TextAlignVertical.top,
            decoration: InputDecoration(
              labelText: strings.t('email'),
              suffixIcon: const Icon(Icons.lock_outline),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _passwordController,
            obscureText: true,
            textAlignVertical: TextAlignVertical.top,
            decoration: InputDecoration(
              labelText: strings.t('password_required'),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _firstNameController,
            textAlignVertical: TextAlignVertical.top,
            decoration: InputDecoration(
              labelText: strings.t('first_name'),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _lastNameController,
            textAlignVertical: TextAlignVertical.top,
            decoration: InputDecoration(
              labelText: strings.t('last_name'),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _addressController,
            textAlignVertical: TextAlignVertical.top,
            decoration: InputDecoration(
              labelText: strings.t('address'),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _cityController,
            textAlignVertical: TextAlignVertical.top,
            decoration: InputDecoration(
              labelText: strings.t('city'),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _zipCodeController,
                  textAlignVertical: TextAlignVertical.top,
                  decoration: InputDecoration(
                    labelText: strings.t('zip_code'),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  controller: _countryController,
                  textAlignVertical: TextAlignVertical.top,
                  decoration: InputDecoration(
                    labelText: strings.t('country'),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _taxNumberController,
            textAlignVertical: TextAlignVertical.top,
            decoration: InputDecoration(
              labelText: strings.t('tax_number'),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _identityCardNumberController,
            textAlignVertical: TextAlignVertical.top,
            decoration: InputDecoration(
              labelText: strings.t('identity_card_number'),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _dateOfBirthController,
            keyboardType: TextInputType.datetime,
            textAlignVertical: TextAlignVertical.top,
            decoration: InputDecoration(
              labelText: strings.t('date_of_birth'),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _socialSecurityNumberController,
            textAlignVertical: TextAlignVertical.top,
            decoration: InputDecoration(
              labelText: strings.t('social_security_number'),
            ),
          ),
          const SizedBox(height: 20),
          Text(
            strings.t('language_country'),
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          DropdownButtonFormField<LocaleOption>(
            initialValue: _selectedLocale,
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
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            value: _speakerOutputEnabled,
            onChanged: (value) => unawaited(_setSpeakerOutputEnabled(value)),
            title: Text(strings.t('speaker_output')),
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
                    initialValue: _selectedSpeakerVoiceId,
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
                  onPressed: _speakerVoices.isEmpty
                      ? null
                      : () => unawaited(_testSpeakerVoice()),
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
              initialValue: _selectedPlanCode,
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
            onPressed:
                (_isSharingLogs || !_debugModeEnabled) ? null : _shareLogs,
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
  static const String _selectedCaseKeyPrefix = 'mobile_selected_case_v1';
  static const double _questionTimeoutSeconds = 3600;
  static const double _maxDiscussionMinutes = 60;
  static const double _communicationMinutes = 60;
  static const Duration _speechSilenceTimeout = Duration(minutes: 10);
  static const Duration _speechSendPromptDelay = Duration(seconds: 10);
  static const Duration _speechMaxListenDuration = Duration(minutes: 30);

  final TextEditingController _inputController = TextEditingController();
  final FocusNode _inputFocusNode = FocusNode();
  final RuleEngine _ruleEngine = const RuleEngine();
  late final VoiceSessionOrchestrator _voiceSessionOrchestrator;
  late final ProfileService _profileService;
  late final JurisdictaSpeechService _speechService;
  final ScrollController _messagesScrollController = ScrollController();

  late final ApiClient _apiClient;
  late final FileSaver _fileSaver;
  late final AppUpdater _appUpdater;
  late final JurisdictaSpeaker _speaker;
  late final JurisdictaSpeechRecognizer _speechRecognizer;
  late final List<ChatMessage> _messages;
  late ResponderMode _responderMode;
  late LocaleOption _selectedLocale;
  String? _documentPath;
  bool _isSending = false;
  bool _isDownloading = false;
  bool _hasExportReady = false;
  String? _latestGeneratedCaseDocumentId;
  String _appVersionLabel = 'v0.1.5+41';
  String? _systemLastLawUpdateDate;
  String? _systemModelKnowledgeCutoffDate;
  bool _updateDialogShown = false;
  bool _skipUpdateChecksUntilRestart = false;
  bool _isInstallingUpdate = false;
  String? _updateProgressMessage;
  String? _updateProgressDetail;
  double? _updateDownloadProgress;
  bool _speakerOutputEnabled = false;
  bool _speechEnabled = false;
  bool _speechInputEnabled = false;
  bool _isListening = false;
  bool _stoppingSpeechManually = false;
  bool _awaitingSpokenName = false;
  bool _awaitingProfileField = false;
  bool _awaitingProfilePatchConfirmation = false;
  SpokenProfilePatch? _pendingProfilePatch;
  bool _awaitingCaseArchiveConfirmation = false;
  bool _awaitingSpokenCaseTitle = false;
  bool _isSavingSpokenName = false;
  late LocalAuthUser _signedInUser;
  List<CaseSummary> _cases = <CaseSummary>[];
  CaseSummary? _selectedCase;
  bool _isLoadingCases = false;
  bool _isLoadingCaseHistory = false;
  bool _caseHistoryHasMore = false;
  int _caseHistoryOffset = 0;
  List<CaseDocumentItem> _caseDocuments = <CaseDocumentItem>[];
  SessionResultDetails? _latestSessionResult;
  final Set<String> _downloadingCaseDocumentIds = <String>{};
  final List<_PendingDocumentUploadBatch> _queuedDocumentUploadBatches =
      <_PendingDocumentUploadBatch>[];
  String? _lastErrorCorrelationId;
  SemanticVersion? _installedAppVersion;
  String? _pendingUpdateInstallPath;
  String? _pendingUpdateVersion;
  Timer? _updateCheckTimer;
  String? _lastDictatedSpeechDraft;
  String? _pendingNewCaseTitle;
  String? _lastFinalSpeechResult;
  String? _lastHandledSpeechText;
  DateTime? _speechRecognitionStartedAt;
  Completer<void>? _speechStopCompleter;
  Timer? _speechSendPromptTimer;
  bool _submitSpeechOnStop = true;
  bool _processSpeechOnStop = true;
  bool _resumeSpeechInputAfterSend = false;
  bool _updateCheckInProgress = false;
  bool _documentAutoAnalysisInProgress = false;
  int _localMessageSequence = 0;
  bool _inputComposerExpanded = false;

  bool get _showLocalResponderSwitch {
    return _isLocalApiBaseUrl(widget.apiBaseUrl);
  }

  bool get _isInputComposerExpanded =>
      _inputComposerExpanded || (_isListening && !_speakerOutputEnabled);

  AppStrings get _strings => AppStrings(_selectedLocale.languageCode);

  void _setInputComposerExpanded(bool value, {bool unfocus = false}) {
    if (unfocus) {
      _inputFocusNode.unfocus();
    }
    if (!mounted || _inputComposerExpanded == value) {
      return;
    }
    setState(() {
      _inputComposerExpanded = value;
    });
  }

  void _handleInputFocusChanged() {
    if (_inputFocusNode.hasFocus) {
      _setInputComposerExpanded(true);
      return;
    }
    if (!_isListening) {
      _setInputComposerExpanded(false);
    }
  }

  void _scheduleSpeechSendPrompt() {
    _speechSendPromptTimer?.cancel();
    _speechSendPromptTimer = null;
  }

  void _cancelSpeechSendPrompt() {
    _speechSendPromptTimer?.cancel();
    _speechSendPromptTimer = null;
  }

  Future<void> _onVoiceSilenceThresholdReached(
    VoiceSilenceThresholdEvent event,
  ) async {
    if (!mounted || !_speechInputEnabled) {
      return;
    }
    if (_isListening) {
      await _stopSpeechListening(
        submitAfterStop: false,
        processStoppedInput: false,
      );
      if (!mounted) {
        return;
      }
    }
    _appendAssistantMessage(event.prompt, speak: false);
    await _speaker.stop();
    await _speakAssistantMessage(
      event.prompt,
      resumeSpeechInputOnCompletion: true,
    );
  }

  String? _voiceSessionStatusLabel() {
    if (!_speechInputEnabled && !_isListening) {
      return null;
    }
    final labels = switch (_voiceSessionOrchestrator.phase) {
      VoiceSessionPhase.listening => <String, String>{
          'SK': 'počúvam',
          'EN': 'listening',
          'GE': 'ich höre zu',
        },
      VoiceSessionPhase.processing => <String, String>{
          'SK': 'spracovávam',
          'EN': 'processing',
          'GE': 'verarbeite',
        },
      VoiceSessionPhase.awaitingConfirmation => <String, String>{
          'SK': 'čakám na potvrdenie',
          'EN': 'waiting for confirmation',
          'GE': 'warte auf Bestätigung',
        },
      VoiceSessionPhase.idle => <String, String>{
          'SK': 'hlas pripravený',
          'EN': 'voice ready',
          'GE': 'Sprache bereit',
        },
    };
    final languageCode = _normalizeLanguageCode(_selectedLocale.languageCode);
    return labels[languageCode] ?? labels[fallbackAppLanguageCode];
  }

  void _clearSpeechDraft() {
    _cancelSpeechSendPrompt();
    _inputController.clear();
    _lastDictatedSpeechDraft = null;
    _lastFinalSpeechResult = null;
    _lastHandledSpeechText = null;
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _signedInUser = widget.signedInUser;
    _selectedLocale = appLocaleOptions.firstWhere(
      (option) =>
          option.countryCode == _defaultCountry &&
          option.languageCode == _defaultLanguage,
      orElse: () => appLocaleOptions.first,
    );
    _responderMode = ResponderMode.realPerson;
    _apiClient = ApiClient(
      baseUri: Uri.parse(widget.apiBaseUrl),
      apiKey: _apiKey,
      logger: widget.logger,
    );
    _fileSaver = createFileSaver();
    _appUpdater = createAppUpdater();
    _profileService = ProfileService.localAuthStore(
      authStore: widget.authStore,
    );
    final voiceConsentGiven =
        (_signedInUser.dataProcessingConsentAt ?? '').trim().isNotEmpty;
    _speechService = const SpeechServiceFactory().create(
      config: SpeechServiceConfig.fromEnvironment().copyWith(
        consentGiven: voiceConsentGiven,
        storeAudioEnabled: false,
        redactSensitiveEntitiesBeforeSend: true,
      ),
    );
    _speaker = _speechService.speaker;
    _speechRecognizer = _speechService.recognizer;
    _voiceSessionOrchestrator = VoiceSessionOrchestrator(
      ruleEngine: _ruleEngine,
      silenceThreshold: _speechSendPromptDelay,
      onSilenceThresholdReached: _onVoiceSilenceThresholdReached,
      onStateChanged: () {
        if (mounted) {
          setState(() {});
        }
      },
    );
    _inputFocusNode.addListener(_handleInputFocusChanged);
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
          'trace_id': _apiClient.flowCorrelationId,
          'processing_purpose': 'mobile_chat_voice_session',
          'voice_compliance':
              _speechService.config.complianceFlags.toLogContext(),
        },
      ),
    );
    unawaited(_initializeSpeechRecognition());
    unawaited(_initializeAssistantSpeech());
    unawaited(_loadSpeakerVoices());
    unawaited(_loadCases());
    unawaited(_loadAppVersion());
    unawaited(_refreshSystemLawDate());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      ProviderScope.containerOf(context, listen: false)
          .read(appLocaleProvider.notifier)
          .setLocale(_selectedLocale);
      _scrollToLatest(animated: false);
    });
  }

  void _resetMessagesForCurrentCase() {
    _awaitingSpokenName = false;
    _latestSessionResult = null;
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
        _installedAppVersion = parsed;
      });
      if (parsed != null) {
        _startPeriodicUpdateChecks();
        unawaited(_checkForApiUpdate());
      }
    } catch (_) {}
  }

  Future<void> _refreshSystemLawDate() async {
    try {
      final info = await _apiClient.fetchApiSystemVersionInfo(
        countryCode: _selectedLocale.countryCode,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _systemLastLawUpdateDate = info.lastLawUpdateDate;
        _systemModelKnowledgeCutoffDate = info.modelKnowledgeCutoffDate;
      });
    } catch (_) {}
  }

  String? _effectiveSystemLawDate() {
    final lastLaw = _systemLastLawUpdateDate?.trim();
    if (lastLaw != null && lastLaw.isNotEmpty) {
      return lastLaw;
    }
    final modelCutoff = _systemModelKnowledgeCutoffDate?.trim();
    if (modelCutoff != null && modelCutoff.isNotEmpty) {
      return modelCutoff;
    }
    return null;
  }

  Future<void> _selectCase(CaseSummary? selected) async {
    if (!mounted) {
      return;
    }
    setState(() {
      _selectedCase = selected;
      _hasExportReady = false;
      _latestGeneratedCaseDocumentId = null;
      _caseHistoryOffset = 0;
      _caseHistoryHasMore = false;
      _caseDocuments = <CaseDocumentItem>[];
      _latestSessionResult = null;
      _queuedDocumentUploadBatches.clear();
      _apiClient.setActiveCase(selected?.caseId);
      _resetMessagesForCurrentCase();
    });
    await _persistSelectedCaseId(selected?.caseId);
    if (selected == null) {
      return;
    }
    await _loadCaseHistory(reset: true);
    await _refreshSessionResultDetails();
  }

  Future<void> _loadCaseHistory({required bool reset}) async {
    final selected = _selectedCase;
    if (selected == null) {
      return;
    }
    final offset = reset ? 0 : _caseHistoryOffset;
    final previousScrollOffset = !reset && _messagesScrollController.hasClients
        ? _messagesScrollController.offset
        : null;
    final previousMaxScrollExtent =
        !reset && _messagesScrollController.hasClients
            ? _messagesScrollController.position.maxScrollExtent
            : null;
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
      final loadedMessages = page.messages
          .map((item) => item.toChatMessage())
          .whereType<ChatMessage>()
          .toList(growable: false);
      String? generatedDocumentId;
      for (final message in page.messages.reversed) {
        generatedDocumentId = _acceptedGeneratedCaseDocumentId(message.content);
        if (generatedDocumentId != null) {
          break;
        }
      }
      generatedDocumentId ??= _latestGeneratedDocumentIdFromCaseDocuments(
        page.documents,
      );
      setState(() {
        _caseDocuments = page.documents;
        if (generatedDocumentId != null) {
          _latestGeneratedCaseDocumentId = generatedDocumentId;
          _hasExportReady = true;
        }
        _caseHistoryHasMore = page.hasMore;
        _caseHistoryOffset = offset + page.messages.length;
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
      _syncCaseDocumentStatusThreadMessage(scrollToEnd: false);
      if (reset) {
        _scrollToLatest(animated: false);
      } else if (loadedMessages.isNotEmpty &&
          previousScrollOffset != null &&
          previousMaxScrollExtent != null) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!_messagesScrollController.hasClients) {
            return;
          }
          final maxScrollExtent =
              _messagesScrollController.position.maxScrollExtent;
          final delta = maxScrollExtent - previousMaxScrollExtent;
          final targetOffset = previousScrollOffset + delta;
          final clampedOffset = targetOffset.clamp(0.0, maxScrollExtent);
          _messagesScrollController.jumpTo(clampedOffset.toDouble());
        });
      }
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

  String? _latestGeneratedDocumentIdFromCaseDocuments(
    List<CaseDocumentItem> documents,
  ) {
    for (final document in documents.reversed) {
      if (document.kind == 'technical_payload' && document.docId.isNotEmpty) {
        return document.docId;
      }
    }
    return null;
  }

  Future<void> _downloadCaseDocument(CaseDocumentItem document) async {
    await _downloadCaseDocumentById(document.docId);
  }

  Future<void> _downloadCaseDocumentById(String docId) async {
    final selected = _selectedCase;
    if (selected == null || docId.trim().isEmpty) {
      return;
    }
    setState(() {
      _downloadingCaseDocumentIds.add(docId);
    });
    try {
      final payload = await _apiClient.downloadCaseDocument(
        caseId: selected.caseId,
        userId: _signedInUser.userId,
        docId: docId,
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
        if (!mounted) {
          return;
        }
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
          _downloadingCaseDocumentIds.remove(docId);
        });
      }
    }
  }

  Future<void> _shareCaseDocument(CaseDocumentItem document) async {
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
      final tempDir = await Directory.systemTemp.createTemp('aij-share-');
      final file = File('${tempDir.path}/${payload.filename}');
      await file.writeAsBytes(payload.bytes, flush: true);
      await Share.shareXFiles(<XFile>[XFile(file.path)],
          text: payload.filename);
      _showSnackbar(_strings.t('case_document_shared'));
    } catch (error) {
      _showSnackbar(
        _strings.t('case_document_share_failed', <String, String>{
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

  void _startPeriodicUpdateChecks() {
    _updateCheckTimer?.cancel();
    _updateCheckTimer = Timer.periodic(const Duration(minutes: 1), (_) {
      unawaited(_checkForApiUpdate());
    });
  }

  Future<void> _checkForApiUpdate() async {
    final installed = _installedAppVersion;
    if (installed == null ||
        _updateCheckInProgress ||
        _skipUpdateChecksUntilRestart) {
      return;
    }
    _updateCheckInProgress = true;
    try {
      final healthResult = await _apiClient.checkHealth();
      if (!healthResult.isHealthy) {
        await widget.logger.info(
          'Skipping API update check because API health is not ready',
          <String, Object?>{
            'api_base_url': widget.apiBaseUrl,
            'error': healthResult.errorMessage,
            'is_network_error': healthResult.isNetworkError,
          },
        );
        return;
      }
      final systemVersionInfo = await _apiClient.fetchApiSystemVersionInfo(
        countryCode: _selectedLocale.countryCode,
      );
      if (mounted) {
        setState(() {
          _systemLastLawUpdateDate = systemVersionInfo.lastLawUpdateDate;
          _systemModelKnowledgeCutoffDate =
              systemVersionInfo.modelKnowledgeCutoffDate;
        });
      }
      final updateInfo = await _apiClient.fetchMobileAppUpdateInfo(
        installed: installed,
      );
      if (updateInfo == null) {
        await widget.logger.info(
          'App is already up to date according to API',
          <String, Object?>{
            'installed': installed.toString(),
          },
        );
        return;
      }
      if (!mounted || _updateDialogShown) {
        return;
      }
      _updateDialogShown = true;
      await widget.logger.info(
        'New app version available via API',
        <String, Object?>{
          'installed': installed.toString(),
          'latest': updateInfo.version.toString(),
          'release_url': updateInfo.releaseUrl,
          'apk_download_url': updateInfo.apkDownloadUrl,
        },
      );
      await _showUpdateDialog(
        installedVersion: installed.toString(),
        latestVersion: updateInfo.version.toString(),
        releaseUrl: updateInfo.releaseUrl,
        apkDownloadUrl: updateInfo.apkDownloadUrl,
      );
    } catch (error, stackTrace) {
      await widget.logger.error(
        'API update check failed',
        error,
        stackTrace,
      );
    } finally {
      _updateCheckInProgress = false;
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
    var skipUntilRestart = false;
    final startUpgrade = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return StatefulBuilder(
          builder: (dialogContext, setDialogState) => AlertDialog(
            title: Text(_strings.t('update_available')),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _strings.t('update_body', <String, String>{
                    'current': installedVersion,
                    'latest': latestVersion,
                  }),
                ),
                const SizedBox(height: 12),
                CheckboxListTile(
                  value: skipUntilRestart,
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                  controlAffinity: ListTileControlAffinity.leading,
                  title: Text(_strings.t('skip_until_restart')),
                  onChanged: (value) {
                    setDialogState(() {
                      skipUntilRestart = value ?? false;
                    });
                  },
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(false),
                child: Text(_strings.t('later')),
              ),
              FilledButton(
                onPressed: () => Navigator.of(dialogContext).pop(true),
                child: Text(_strings.t('update')),
              ),
            ],
          ),
        );
      },
    );
    if (skipUntilRestart) {
      _skipUpdateChecksUntilRestart = true;
      _updateCheckTimer?.cancel();
      await widget.logger.info(
        'API update monitoring skipped until next app start',
        <String, Object?>{'latest': latestVersion},
      );
    }
    if (startUpgrade == true) {
      await _startAppUpgrade(
        latestVersion: latestVersion,
        releaseUrl: releaseUrl,
        apkDownloadUrl: apkDownloadUrl,
      );
    }
  }

  void _setUpgradeProgress({
    required String message,
    String? detail,
    double? progress,
  }) {
    if (!mounted) {
      _updateProgressMessage = message;
      _updateProgressDetail = detail;
      _updateDownloadProgress = progress;
      return;
    }
    setState(() {
      _updateProgressMessage = message;
      _updateProgressDetail = detail;
      _updateDownloadProgress = progress;
    });
  }

  String _formatMegabytes(int bytes) {
    final value = bytes / (1024 * 1024);
    return value.toStringAsFixed(value >= 10 ? 0 : 1);
  }

  Widget _buildUpgradeProgressCard(ThemeData theme, AppStrings strings) {
    final progress = _updateDownloadProgress;
    final message = _updateProgressMessage;
    if (message == null) {
      return const SizedBox.shrink();
    }
    final progressLabel =
        progress == null ? '...' : '${(progress * 100).clamp(0, 100).round()}%';
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(12, 8, 12, 0),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFD6E4FF)),
        boxShadow: const [
          BoxShadow(
            color: Color(0x14000000),
            blurRadius: 8,
            offset: Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.system_update_alt,
                color: theme.colorScheme.primary,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  strings.t('update_available'),
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              Text(
                progressLabel,
                style: theme.textTheme.labelMedium?.copyWith(
                  color: theme.colorScheme.primary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(message, style: theme.textTheme.bodyMedium),
          if (_updateProgressDetail != null) ...[
            const SizedBox(height: 4),
            Text(
              _updateProgressDetail!,
              style: theme.textTheme.bodySmall?.copyWith(
                color: const Color(0xFF4A628A),
              ),
            ),
          ],
          const SizedBox(height: 10),
          progress == null
              ? const LinearProgressIndicator()
              : LinearProgressIndicator(value: progress.clamp(0.0, 1.0)),
        ],
      ),
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
      _setUpgradeProgress(
        message: _strings.t('update_download_started', <String, String>{
          'latest': latestVersion,
        }),
        progress: 0,
      );
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
        onProgress: (progress) {
          final fraction = progress.fractionComplete;
          _setUpgradeProgress(
            message: _strings.t('update_download_progress', <String, String>{
              'percent': fraction == null
                  ? '?'
                  : '${(fraction * 100).clamp(0, 100).round()}',
              'received': _formatMegabytes(progress.receivedBytes),
              'total': progress.totalBytes <= 0
                  ? '?'
                  : _formatMegabytes(progress.totalBytes),
            }),
            detail: apkDownloadUrl,
            progress: fraction,
          );
        },
      );
      _setUpgradeProgress(
        message: _strings.t('update_download_finishing'),
        detail: filePath,
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
      _setUpgradeProgress(
        message: _strings.t('update_download_failed', <String, String>{
          'error': '$error',
        }),
        detail: apkDownloadUrl,
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
      _setUpgradeProgress(
        message: _strings.t('update_install_permission_check'),
        detail: filePath,
      );
      final canInstall = await _appUpdater.canInstallPackages();
      if (!canInstall) {
        await widget.logger.info(
          'Install unknown apps permission required for Android update',
          <String, Object?>{
            'file_path': filePath,
            'latest': _pendingUpdateVersion,
          },
        );
        _setUpgradeProgress(
          message: _strings.t('update_install_permission_required'),
          detail: filePath,
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
      _setUpgradeProgress(
        message: _strings.t('update_install_started'),
        detail: filePath,
        progress: 1,
      );
      _showSnackbar(_strings.t('update_install_started'));
    } on PlatformException catch (error, stackTrace) {
      if (error.code == 'signature_mismatch') {
        _setUpgradeProgress(
          message: _strings.t('update_install_signature_mismatch'),
          detail: filePath,
        );
        _showSnackbar(_strings.t('update_install_signature_mismatch'));
        return;
      }
      await widget.logger.error(
        'Failed to start Android update installer',
        error,
        stackTrace,
      );
      _setUpgradeProgress(
        message: _strings.t('update_install_failed', <String, String>{
          'error': '$error',
        }),
        detail: filePath,
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
      _setUpgradeProgress(
        message: _strings.t('update_install_failed', <String, String>{
          'error': '$error',
        }),
        detail: filePath,
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

  void _appendAssistantMessage(String content, {bool speak = true}) {
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
    if (speak) {
      unawaited(
        _speakAssistantMessage(
          content,
          resumeSpeechInputOnCompletion: _speakerOutputEnabled,
        ),
      );
    }
  }

  void _appendUserMessageLocally(String content) {
    final trimmed = content.trim();
    if (!mounted || trimmed.isEmpty) {
      return;
    }
    setState(() {
      _messages.add(
        ChatMessage(
          role: 'user',
          content: trimmed,
          documentPath: _documentPath,
          createdAt: DateTime.now(),
        ),
      );
    });
    _scrollToLatest();
  }

  String _appendFrontendThinkingMessage() {
    final messageId = _nextLocalMessageId('frontend-thinking');
    if (!mounted) {
      return messageId;
    }
    setState(() {
      _messages.add(
        ChatMessage(
          role: 'assistant',
          content: _strings.t('frontend_thinking_message'),
          agentName: _strings.t('frontend_agent'),
          createdAt: DateTime.now(),
          localId: messageId,
        ),
      );
    });
    _scrollToLatest();
    return messageId;
  }

  void _appendBackendProcessingMessage(String message) {
    final trimmed = message.trim();
    if (!mounted || trimmed.isEmpty) {
      return;
    }
    setState(() {
      _messages.add(
        ChatMessage(
          role: 'assistant',
          content: trimmed,
          agentName: _strings.t('backend_agent'),
          createdAt: DateTime.now(),
        ),
      );
    });
    _scrollToLatest();
  }

  String _nextLocalMessageId(String prefix) {
    _localMessageSequence += 1;
    return '$prefix-${DateTime.now().microsecondsSinceEpoch}-$_localMessageSequence';
  }

  String _appendDocumentUploadStatusMessage(String content) {
    final messageId = _nextLocalMessageId('upload');
    if (!mounted) {
      return messageId;
    }
    setState(() {
      _messages.add(
        ChatMessage(
          role: 'assistant',
          content: content,
          agentName: 'Jurisdicta',
          createdAt: DateTime.now(),
          localId: messageId,
        ),
      );
    });
    _scrollToLatest();
    return messageId;
  }

  Future<void> _updateDocumentUploadStatusMessage(
    String messageId, {
    required String content,
    bool speak = false,
  }) async {
    if (!mounted) {
      return;
    }
    var updated = false;
    setState(() {
      final index =
          _messages.indexWhere((message) => message.localId == messageId);
      if (index < 0) {
        return;
      }
      final existing = _messages[index];
      _messages[index] = ChatMessage(
        role: existing.role,
        content: content,
        agentName: existing.agentName,
        documentPath: existing.documentPath,
        createdAt: existing.createdAt,
        localId: existing.localId,
      );
      updated = true;
    });
    if (!updated) {
      return;
    }
    _scrollToLatest();
    if (speak) {
      await _speaker.stop();
      await _speakAssistantMessage(content);
    }
  }

  void _removeThreadMessage(String messageId) {
    if (!mounted) {
      return;
    }
    setState(() {
      _messages.removeWhere((message) => message.localId == messageId);
    });
  }

  void _upsertThreadAssistantMessage({
    required String messageId,
    required String content,
    bool scrollToEnd = false,
  }) {
    if (!mounted) {
      return;
    }
    final trimmed = content.trim();
    setState(() {
      _messages.removeWhere((message) => message.localId == messageId);
      if (trimmed.isEmpty) {
        return;
      }
      _messages.add(
        ChatMessage(
          role: 'assistant',
          content: trimmed,
          agentName: 'Jurisdicta',
          createdAt: DateTime.now(),
          localId: messageId,
        ),
      );
    });
    if (trimmed.isNotEmpty && scrollToEnd) {
      _scrollToLatest();
    }
  }

  String _buildCaseValidationThreadMessage(SessionResultDetails result) {
    final strings = _strings;
    final lines = <String>[
      strings.t('case_validation_title'),
      '${strings.t('validation_accuracy_label')}: ${_formatAccuracy(result.validationAccuracy)}',
    ];
    final summary = result.validationSummary?.trim();
    if (summary != null && summary.isNotEmpty) {
      lines.add('${strings.t('validation_summary_label')}: $summary');
    }
    final knowledgeUpdated = _formatSessionTimestamp(
      result.knowledgeLastUpdatedAt,
    );
    if (knowledgeUpdated.isNotEmpty) {
      lines.add('${strings.t('knowledge_updated_label')}: $knowledgeUpdated');
    }
    final coreVersion = result.coreVersion?.trim();
    if (coreVersion != null && coreVersion.isNotEmpty) {
      lines.add('${strings.t('model_version_label')}: $coreVersion');
    }
    return lines.join('\n');
  }

  void _syncCaseDocumentStatusThreadMessage({bool scrollToEnd = false}) {
    if (_selectedCase == null || _caseDocuments.isEmpty) {
      _removeThreadMessage(_caseDocumentsStatusMessageId);
      return;
    }
    _upsertThreadAssistantMessage(
      messageId: _caseDocumentsStatusMessageId,
      content: _buildCaseDocumentStatusMessage(),
      scrollToEnd: scrollToEnd,
    );
  }

  void _syncValidationThreadMessage({bool scrollToEnd = false}) {
    if (_responderMode != ResponderMode.aiUserSimulator) {
      _removeThreadMessage(_caseValidationMessageId);
      return;
    }
    final result = _latestSessionResult;
    if (result == null || !result.hasValidationData) {
      _removeThreadMessage(_caseValidationMessageId);
      return;
    }
    _upsertThreadAssistantMessage(
      messageId: _caseValidationMessageId,
      content: _buildCaseValidationThreadMessage(result),
      scrollToEnd: scrollToEnd,
    );
  }

  Future<void> _initializeSpeechRecognition() async {
    final enabled = await _speechRecognizer.initialize(
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
      <String, Object?>{
        'enabled': enabled,
        'speech_mode': _speechService.modeLabel,
        'speech_runtime_mode': _speechService.runtimeModeLabel,
        ..._voiceLogContext('speech_recognition_initialization'),
      },
    );
  }

  Future<void> _initializeAssistantSpeech() async {
    final enabled = await _speaker.initialize();
    if (!enabled) {
      await widget.logger.info('Assistant speech output unavailable');
      return;
    }
    await widget.logger.info(
      'Assistant speech output initialized in manual mode',
      <String, Object?>{
        'enabled': _speakerOutputEnabled,
        'speech_mode': _speechService.modeLabel,
        'speech_runtime_mode': _speechService.runtimeModeLabel,
        ..._voiceLogContext('assistant_speech_initialization'),
      },
    );
  }

  Map<String, Object?> _voiceLogContext(String processingPurpose) {
    return <String, Object?>{
      'trace_id': _apiClient.flowCorrelationId,
      'processing_purpose': processingPurpose,
      'voice_compliance': _speechService.config.complianceFlags.toLogContext(),
    };
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

  Future<void> _speakAssistantMessage(
    String content, {
    bool resumeSpeechInputOnCompletion = false,
  }) async {
    if (!_speakerOutputEnabled) {
      return;
    }
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
      return;
    }
    if (resumeSpeechInputOnCompletion) {
      if (_isSending) {
        _resumeSpeechInputAfterSend = true;
        return;
      }
      await _resumeSpeechListeningAfterAssistantSpeech(
        reason: 'assistant_message',
      );
    }
  }

  Future<bool> _ensureSpeechInputEnabledForVoiceMode() async {
    if (!_speakerOutputEnabled || !_speechEnabled) {
      return false;
    }
    if (!_speechInputEnabled && mounted) {
      setState(() {
        _speechInputEnabled = true;
      });
      await widget.logger.info(
        'Speech input enabled for assistant voice mode',
      );
    }
    return _speechInputEnabled;
  }

  Future<void> _resumeSpeechListeningAfterAssistantSpeech({
    required String reason,
  }) async {
    final speechInputReady = await _ensureSpeechInputEnabledForVoiceMode();
    if (!mounted ||
        !speechInputReady ||
        !_speakerOutputEnabled ||
        _isListening ||
        _isSending) {
      return;
    }
    await Future<void>.delayed(_speechService.config.resumeListeningDelay);
    final stillReady = await _ensureSpeechInputEnabledForVoiceMode();
    if (!mounted ||
        !stillReady ||
        !_speakerOutputEnabled ||
        _isListening ||
        _isSending) {
      return;
    }
    if (!_awaitingSpokenName && !_awaitingSpokenCaseTitle) {
      _inputController.clear();
    }
    await widget.logger.info(
      'Speech listening resumed after assistant speech',
      <String, Object?>{'reason': reason},
    );
    await _startSpeechListening(resetHandledText: true);
  }

  String _resolveAssistantVisibleReply({
    required String rawReply,
    required bool exportReady,
  }) {
    final generatedDocumentId = _acceptedGeneratedCaseDocumentId(rawReply);
    if (generatedDocumentId != null) {
      _latestGeneratedCaseDocumentId = generatedDocumentId;
      _hasExportReady = true;
    }
    final visibleReply = _sanitizeVisibleMessageContent(
      stripInternalGeneratedDocumentNotice(rawReply),
    );
    if (!exportReady &&
        (generatedDocumentId != null ||
            _looksLikeGeneratedDocumentDraft(visibleReply))) {
      _hasExportReady = true;
    }
    if (visibleReply.isEmpty) {
      return '';
    }
    final shouldSuppressDocumentBody =
        _containsDocumentPayloadMarkers(rawReply) ||
            (exportReady && _looksLikeGeneratedDocumentDraft(visibleReply));
    if (!shouldSuppressDocumentBody) {
      return visibleReply;
    }
    return _strings.t('document_pdf_offer');
  }

  String? _acceptedGeneratedCaseDocumentId(String content) {
    final generatedDocument = extractGeneratedCaseDocumentReference(content);
    if (generatedDocument == null ||
        generatedDocument.caseId != _selectedCase?.caseId ||
        (generatedDocument.userId != null &&
            generatedDocument.userId != _signedInUser.userId)) {
      return null;
    }
    return generatedDocument.docId;
  }

  Future<void> _setSpeakerOutputEnabled(bool enabled) async {
    if (!mounted) {
      return;
    }
    setState(() {
      _speakerOutputEnabled = enabled;
    });
    if (!enabled) {
      await _speaker.stop();
    }
    await widget.logger.info(
      'Assistant speech output toggled',
      <String, Object?>{'enabled': enabled},
    );
  }

  void _onSpeechResult(JurisdictaSpeechRecognitionResult result) {
    if (!mounted) {
      return;
    }
    final recognizedText = result.recognizedWords.trim();
    final speechStartedAt = _speechRecognitionStartedAt ?? DateTime.now();
    if (result.finalResult && recognizedText.isNotEmpty) {
      _lastFinalSpeechResult = recognizedText;
    }
    if (recognizedText.isNotEmpty &&
        !isSpokenSendCommand(recognizedText) &&
        !isSpokenClearDraftCommand(recognizedText) &&
        parseSpokenCaseCreationCommand(recognizedText) == null) {
      _lastDictatedSpeechDraft = recognizedText;
      _scheduleSpeechSendPrompt();
    }
    setState(() {
      _inputController.text = result.recognizedWords;
      _inputController.selection = TextSelection.fromPosition(
        TextPosition(offset: _inputController.text.length),
      );
    });
    final shouldProcessImmediately = result.finalResult &&
        _shouldProcessFinalSpeechResultImmediately(
          recognizedText,
        );
    final wasAwaitingVoiceConfirmation =
        _voiceSessionOrchestrator.awaitingConfirmation;
    final spokenConfirmation = wasAwaitingVoiceConfirmation
        ? parseSpokenConfirmation(recognizedText)
        : null;
    final transcriptResult = _voiceSessionOrchestrator.acceptTranscript(
      transcript: recognizedText,
      isFinal: result.finalResult,
      speechStartedAt: speechStartedAt,
      context: _buildRuleEngineContext(
        submitMessageWhenNoRuleMatches: shouldProcessImmediately,
      ),
      submitMessageWhenNoRuleMatches: shouldProcessImmediately,
    );
    if (transcriptResult.queuedAction != null) {
      unawaited(_processQueuedSpeechActionsImmediately());
    } else if (spokenConfirmation != null) {
      unawaited(_finishAnsweredVoiceConfirmation());
    }
  }

  bool _shouldProcessFinalSpeechResultImmediately(String recognizedText) {
    if (recognizedText.isEmpty) {
      return false;
    }
    return isSpokenSendCommand(recognizedText) ||
        _shouldRouteProfilePatchViaRule(recognizedText) ||
        isSpokenClearDraftCommand(recognizedText) ||
        hasTrailingSpokenSendCommand(recognizedText) ||
        parseSpokenCaseCreationCommand(recognizedText) != null;
  }

  Future<void> _processQueuedSpeechActionsImmediately() async {
    _cancelSpeechSendPrompt();
    if (_isListening) {
      await _stopSpeechListening(
        submitAfterStop: false,
        processStoppedInput: false,
      );
      if (!mounted) {
        return;
      }
    }
    await _drainVoiceActionQueue();
  }

  Future<void> _finishAnsweredVoiceConfirmation() async {
    _cancelSpeechSendPrompt();
    if (_isListening) {
      await _stopSpeechListening(
        submitAfterStop: false,
        processStoppedInput: false,
      );
      if (!mounted) {
        return;
      }
    }
    setState(_clearSpeechDraft);
  }

  void _onSpeechStatus(String status) {
    if (!mounted) {
      return;
    }
    final isListening = status == SpeechToText.listeningStatus;
    setState(() {
      _isListening = isListening;
    });
    if (isListening) {
      _voiceSessionOrchestrator.startListening(
        now: _speechRecognitionStartedAt,
      );
    } else {
      _voiceSessionOrchestrator.stopListening();
    }
    unawaited(
      widget.logger.info(
        'Speech status changed',
        <String, Object?>{'status': status},
      ),
    );
    if (!isListening) {
      _cancelSpeechSendPrompt();
      if (!_stoppingSpeechManually &&
          _speechInputEnabled &&
          _lastFinalSpeechResult == null) {
        _showSnackbar(_strings.t('speech_input_auto_stopped'));
      }
      final shouldProcess = _processSpeechOnStop;
      final shouldSubmit = _submitSpeechOnStop;
      _processSpeechOnStop = true;
      _submitSpeechOnStop = true;
      _speechStopCompleter?.complete();
      _speechStopCompleter = null;
      if (shouldProcess) {
        unawaited(
          _handleSpeechStopped(
            submitAfterStop: shouldSubmit,
          ),
        );
      }
    }
  }

  void _onSpeechError(JurisdictaSpeechRecognitionError error) {
    if (!mounted) {
      return;
    }
    setState(() {
      _isListening = false;
    });
    _voiceSessionOrchestrator.stopListening();
    _showSnackbar(_strings.t('speech_recognition_error', <String, String>{
      'error': error.errorMsg,
    }));
    unawaited(
      widget.logger.error(
        'Speech recognition error',
        Exception(error.errorMsg),
        StackTrace.current,
        <String, Object?>{
          'permanent': error.permanent,
          ..._voiceLogContext('speech_recognition_error'),
        },
      ),
    );
    _speechStopCompleter?.complete();
    _speechStopCompleter = null;
  }

  Future<void> _handleSpeechStopped({
    required bool submitAfterStop,
  }) async {
    if (!mounted) {
      return;
    }
    await Future<void>.delayed(const Duration(milliseconds: 150));
    if (!mounted) {
      return;
    }
    final spokenText = _resolvedSpeechTextOnStop();
    if (spokenText.isEmpty) {
      return;
    }
    await _handleCompletedSpeechInput(
      spokenText,
      submitAfterRecognition: submitAfterStop,
    );
  }

  String _resolvedSpeechTextOnStop() {
    final current = _inputController.text.trim();
    if (current.isNotEmpty) {
      return current;
    }
    final finalResult = (_lastFinalSpeechResult ?? '').trim();
    if (finalResult.isNotEmpty) {
      return finalResult;
    }
    return (_lastDictatedSpeechDraft ?? '').trim();
  }

  Future<void> _stopSpeechListening({
    required bool submitAfterStop,
    bool processStoppedInput = true,
  }) async {
    _cancelSpeechSendPrompt();
    _submitSpeechOnStop = submitAfterStop;
    _processSpeechOnStop = processStoppedInput;
    if (!_isListening) {
      if (processStoppedInput) {
        await _handleSpeechStopped(submitAfterStop: submitAfterStop);
      }
      return;
    }
    final completer = Completer<void>();
    _speechStopCompleter = completer;
    _stoppingSpeechManually = true;
    await _speechRecognizer.stop();
    if (!completer.isCompleted) {
      await completer.future.timeout(
        const Duration(seconds: 10),
        onTimeout: () {},
      );
    }
    _stoppingSpeechManually = false;
  }

  Future<void> _requestNewCaseFromCommand({
    String? title,
  }) async {
    if (_cases.length >= 5) {
      _showSnackbar(_strings.t('maximum_cases'));
      return;
    }

    final normalizedTitle = title?.trim();
    if (_selectedCase == null) {
      if (normalizedTitle == null || normalizedTitle.isEmpty) {
        await _promptForSpokenCaseTitle();
        return;
      }
      await _createCaseWithTitle(
        normalizedTitle,
        successMessage:
            _strings.t('case_voice_created_continue', <String, String>{
          'name': normalizedTitle,
        }),
      );
      return;
    }

    final currentCase = _selectedCase!;
    final prompt = normalizedTitle != null && normalizedTitle.isNotEmpty
        ? _strings.t('case_archive_confirmation_named', <String, String>{
            'current': currentCase.title,
            'name': normalizedTitle,
          })
        : _strings.t('case_archive_confirmation', <String, String>{
            'name': currentCase.title,
          });

    setState(() {
      _awaitingCaseArchiveConfirmation = true;
      _pendingNewCaseTitle = normalizedTitle;
      _inputController.clear();
    });

    _appendAssistantMessage(prompt, speak: false);
    await _speaker.stop();
    await _speakAssistantMessage(prompt, resumeSpeechInputOnCompletion: true);
  }

  Future<void> _handleCaseArchiveConfirmation(
    SpokenConfirmationChoice? confirmation,
  ) async {
    if (confirmation == null) {
      final retryPrompt = _strings.t('case_archive_confirmation_retry');
      _appendAssistantMessage(retryPrompt, speak: false);
      await _speaker.stop();
      await _speakAssistantMessage(
        retryPrompt,
        resumeSpeechInputOnCompletion: true,
      );
      return;
    }

    final pendingTitle = (_pendingNewCaseTitle ?? '').trim();
    setState(() {
      _awaitingCaseArchiveConfirmation = false;
      _pendingNewCaseTitle = null;
      _inputController.clear();
    });

    if (confirmation == SpokenConfirmationChoice.no) {
      _appendAssistantMessage(_strings.t('case_archive_cancelled'));
      return;
    }

    if (pendingTitle.isEmpty) {
      await _promptForSpokenCaseTitle();
      return;
    }

    await _createCaseWithTitle(
      pendingTitle,
      successMessage:
          _strings.t('case_voice_created_continue', <String, String>{
        'name': pendingTitle,
      }),
    );
  }

  Future<void> _storeSpokenName(SpokenProfileName? parsed) async {
    if (_isSavingSpokenName) {
      return;
    }
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
      final previousUser = _signedInUser;
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
      _appendProfileNameChangedMessage(
          previousUser: previousUser, updated: updated);
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

  Future<bool> _tryHandleUserCommand(
    String rawText, {
    required bool appendUserMessage,
  }) async {
    final container = ProviderScope.containerOf(context, listen: false);
    final result = await container.read(userCommandExecutorProvider).execute(
          rawText,
          currentUser: _signedInUser,
          locales: appLocaleOptions,
          authStore: widget.authStore,
        );
    if (!result.handled) {
      return false;
    }

    if (appendUserMessage) {
      _appendUserMessageLocally(rawText);
      _inputController.clear();
      _lastDictatedSpeechDraft = null;
    }

    if (result.updatedLocale != null) {
      final locale = result.updatedLocale!;
      await _handleLocaleChanged(locale);
      if (!mounted) {
        return true;
      }
      final localeLabel = _strings.localeLabel(locale);
      final message = _strings
          .t('language_changed', <String, String>{'language': localeLabel});
      _showSnackbar(message);
      _appendAssistantMessage(message);
    }

    if (result.updatedUser != null) {
      final updated = result.updatedUser!;
      final previousUser = _signedInUser;
      setState(() {
        _signedInUser = updated;
        _awaitingSpokenName = false;
        _updateWelcomeMessageForLocale();
      });
      widget.onProfileUpdated(updated);
      final successMessage = _strings.t('profile_updated_success');
      _showSnackbar(successMessage);
      _appendAssistantMessage(successMessage);
      _appendProfileNameChangedMessage(
        previousUser: previousUser,
        updated: updated,
      );
    }

    return true;
  }

  void _appendProfileNameChangedMessage({
    required LocalAuthUser previousUser,
    required LocalAuthUser updated,
  }) {
    final previousName = resolveStoredProfileName(
      firstName: previousUser.firstName,
      lastName: previousUser.lastName,
    );
    final updatedName = resolveStoredProfileName(
      firstName: updated.firstName,
      lastName: updated.lastName,
    );
    if (updatedName == null ||
        updatedName.isEmpty ||
        previousName == updatedName) {
      return;
    }
    _appendAssistantMessage(
      _strings.t('profile_name_changed', <String, String>{
        'name': updatedName,
      }),
    );
  }

  String _profilePatchFieldLabel(ProfilePatchField field) {
    final key = switch (field) {
      ProfilePatchField.firstName => 'profile_voice_patch_confirm_first_name',
      ProfilePatchField.lastName => 'profile_voice_patch_confirm_last_name',
      ProfilePatchField.address => 'profile_voice_patch_confirm_address',
    };
    return _strings.t(key);
  }

  Future<void> _requestProfilePatchConfirmation(
    SpokenProfilePatch? patch,
  ) async {
    _lastDictatedSpeechDraft = null;
    _inputController.clear();
    if (patch == null) {
      final message = _strings.t('profile_voice_patch_invalid');
      _showSnackbar(message);
      _appendAssistantMessage(message);
      return;
    }

    final message = _strings.t(
      'profile_voice_patch_recap',
      <String, String>{
        'field': _profilePatchFieldLabel(patch.field),
        'value': patch.value,
      },
    );
    setState(() {
      _awaitingProfileField = false;
      _awaitingProfilePatchConfirmation = true;
      _pendingProfilePatch = patch;
    });
    _appendAssistantMessage(message, speak: false);
    await widget.logger.info(
      'Voice profile patch pending confirmation',
      <String, Object?>{
        'user_id': _signedInUser.userId,
        'field': patch.apiFieldName,
        'value_length': patch.value.length,
      },
    );
    await _speaker.stop();
    await _speakAssistantMessage(
      message,
      resumeSpeechInputOnCompletion: _speakerOutputEnabled,
    );
  }

  Future<void> _handleProfilePatchConfirmation(
    SpokenConfirmationChoice? confirmation,
    SpokenProfilePatch? patch,
  ) async {
    if (confirmation == null) {
      final pending = patch ?? _pendingProfilePatch;
      await _requestProfilePatchConfirmation(pending);
      return;
    }
    if (confirmation == SpokenConfirmationChoice.no) {
      setState(() {
        _awaitingProfilePatchConfirmation = false;
        _pendingProfilePatch = null;
        _inputController.clear();
      });
      final message = _strings.t('profile_voice_patch_cancelled');
      _showSnackbar(message);
      _appendAssistantMessage(message);
      return;
    }

    final confirmedPatch = patch ?? _pendingProfilePatch;
    if (confirmedPatch == null) {
      final message = _strings.t('profile_voice_patch_invalid');
      _showSnackbar(message);
      _appendAssistantMessage(message);
      return;
    }

    setState(() {
      _isSavingSpokenName = true;
    });
    try {
      final previousUser = _signedInUser;
      final updated = await _profileService.patchProfileFromVoice(
        currentUser: _signedInUser,
        patch: confirmedPatch,
        requestedBy: _signedInUser.userId,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _signedInUser = updated;
        _awaitingProfileField = false;
        _awaitingProfilePatchConfirmation = false;
        _pendingProfilePatch = null;
        _inputController.clear();
        _updateWelcomeMessageForLocale();
      });
      widget.onProfileUpdated(updated);
      final successMessage = _strings.t('profile_updated_success');
      _showSnackbar(successMessage);
      _appendAssistantMessage(successMessage);
      _appendProfileNameChangedMessage(
        previousUser: previousUser,
        updated: updated,
      );
      await widget.logger.info(
        'Voice profile patch committed',
        <String, Object?>{
          'user_id': updated.userId,
          'field': confirmedPatch.apiFieldName,
          'source': 'voice',
        },
      );
    } catch (error, stackTrace) {
      _showSnackbar(_strings.t('profile_update_failed', <String, String>{
        'error': '$error',
      }));
      await widget.logger.error(
        'Voice profile patch failed',
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

  RuleEngineContext _buildRuleEngineContext({
    required bool submitMessageWhenNoRuleMatches,
  }) {
    return RuleEngineContext(
      awaitingProfileName: _awaitingSpokenName,
      awaitingProfileField: _awaitingProfileField,
      awaitingProfilePatchConfirmation: _awaitingProfilePatchConfirmation,
      awaitingCaseArchiveConfirmation: _awaitingCaseArchiveConfirmation,
      awaitingCaseTitle: _awaitingSpokenCaseTitle,
      submitMessageWhenNoRuleMatches: submitMessageWhenNoRuleMatches,
      pendingProfilePatch: _pendingProfilePatch,
      currentDraft: _inputController.text,
      lastDictatedDraft: _lastDictatedSpeechDraft,
      correlationId: _apiClient.flowCorrelationId,
      caseId: _selectedCase?.caseId,
      userId: _signedInUser.userId,
      languageCode: _selectedLocale.languageCode,
      redactSensitiveEntitiesBeforeSend:
          _speechService.config.redactSensitiveEntitiesBeforeSend,
    );
  }

  Future<void> _applyRuleEngineAction(
    RuleEngineAction action, {
    required String originalInput,
  }) async {
    switch (action) {
      case IgnoreRuleAction():
        return;
      case ConfirmProfilePatchRuleAction(:final confirmation, :final patch):
        _lastHandledSpeechText = originalInput;
        await _handleProfilePatchConfirmation(confirmation, patch);
        return;
      case ConfirmCaseArchiveRuleAction(:final confirmation):
        _lastHandledSpeechText = originalInput;
        await _handleCaseArchiveConfirmation(confirmation);
        return;
      case StoreProfileNameRuleAction(:final profileName):
        _lastHandledSpeechText = originalInput;
        await _storeSpokenName(profileName);
        return;
      case RequestProfilePatchRuleAction(:final patch):
        _lastHandledSpeechText = originalInput;
        if (_isListening) {
          await _stopSpeechListening(
            submitAfterStop: false,
            processStoppedInput: false,
          );
          if (!mounted) {
            return;
          }
        }
        await _requestProfilePatchConfirmation(patch);
        return;
      case SendCurrentDraftRuleAction(:final message):
        _lastHandledSpeechText = originalInput;
        _cancelSpeechSendPrompt();
        if (_isListening) {
          await _stopSpeechListening(
            submitAfterStop: false,
            processStoppedInput: false,
          );
          if (!mounted) {
            return;
          }
        }
        setState(() {
          _inputController.text = message;
          _inputController.selection = TextSelection.fromPosition(
            TextPosition(offset: message.length),
          );
        });
        await widget.logger.info(
          'Speech send command recognized',
          <String, Object?>{'message_length': message.length},
        );
        await _submitMessageText(message);
        return;
      case ClearCurrentDraftRuleAction():
        _lastHandledSpeechText = originalInput;
        if (_isListening) {
          await _stopSpeechListening(
            submitAfterStop: false,
            processStoppedInput: false,
          );
          if (!mounted) {
            return;
          }
        }
        setState(_clearSpeechDraft);
        _showSnackbar(_strings.t('speech_draft_cancelled'));
        await widget.logger.info('Speech draft cleared by voice command');
        if (_speechInputEnabled && _speakerOutputEnabled) {
          await _resumeSpeechListeningAfterAssistantSpeech(
            reason: 'draft_cleared',
          );
        }
        return;
      case SubmitMessageRuleAction(:final message):
        _lastHandledSpeechText = originalInput;
        _cancelSpeechSendPrompt();
        if (_awaitingSpokenCaseTitle) {
          await _createCaseFromVoice(message);
          return;
        }
        await widget.logger.info(
          'Submitting speech-recognized message after speech stop',
          <String, Object?>{'message_length': message.length},
        );
        await _submitMessageText(message);
        return;
      case CreateCaseRuleAction(:final title):
        _lastHandledSpeechText = originalInput;
        _inputController.clear();
        _lastDictatedSpeechDraft = null;
        await _requestNewCaseFromCommand(title: title);
        return;
      case ToolInvocationRuleAction(:final request):
        _lastHandledSpeechText = originalInput;
        await widget.logger.info(
          'Speech tool intent mapped',
          request.toJson(),
        );
        await _submitMessageText(originalInput);
        return;
    }
  }

  Future<void> _drainVoiceActionQueue() async {
    while (mounted) {
      final queued = _voiceSessionOrchestrator.dequeueAction();
      if (queued == null) {
        return;
      }
      await _applyRuleEngineAction(
        queued.action,
        originalInput: queued.originalTranscript,
      );
    }
  }

  Future<void> _handleCompletedSpeechInput(
    String spokenText, {
    bool submitAfterRecognition = false,
  }) async {
    final normalizedText = spokenText.trim();
    if (normalizedText.isEmpty || _lastHandledSpeechText == normalizedText) {
      return;
    }

    if (_shouldRouteProfilePatchViaRule(normalizedText)) {
      final action = _ruleEngine.evaluate(
        input: normalizedText,
        context: _buildRuleEngineContext(
          submitMessageWhenNoRuleMatches: false,
        ),
      );
      _voiceSessionOrchestrator.enqueueActionForTranscript(
        action: action,
        transcript: normalizedText,
        speechStartedAt: _speechRecognitionStartedAt ?? DateTime.now(),
      );
      await _drainVoiceActionQueue();
      return;
    }

    final handledCommand = await _tryHandleUserCommand(
      normalizedText,
      appendUserMessage: true,
    );
    if (handledCommand) {
      _lastHandledSpeechText = normalizedText;
      return;
    }

    final action = _ruleEngine.evaluate(
      input: normalizedText,
      context: _buildRuleEngineContext(
        submitMessageWhenNoRuleMatches: submitAfterRecognition,
      ),
    );
    _voiceSessionOrchestrator.enqueueActionForTranscript(
      action: action,
      transcript: normalizedText,
      speechStartedAt: _speechRecognitionStartedAt ?? DateTime.now(),
    );
    await _drainVoiceActionQueue();
  }

  bool _shouldRouteProfilePatchViaRule(String normalizedText) {
    return _awaitingProfileField ||
        _awaitingProfilePatchConfirmation ||
        parseSpokenProfilePatchCommand(normalizedText) != null;
  }

  Future<void> _toggleSpeechInput() async {
    if (!_speakerOutputEnabled) {
      _setInputComposerExpanded(true);
      _inputFocusNode.requestFocus();
    } else {
      _setInputComposerExpanded(false, unfocus: true);
    }
    _lastHandledSpeechText = null;
    await _speaker.stop();
    if (!_speechEnabled) {
      _showSnackbar(_strings.t('speech_unavailable'));
      return;
    }
    if (!_speechInputEnabled) {
      await _toggleSpeechInputEnabled();
      if (!_speechInputEnabled || !mounted) {
        return;
      }
    }
    if (_isListening) {
      await _stopSpeechListening(submitAfterStop: true);
      return;
    }
    if (_awaitingSpokenName) {
      _inputController.clear();
    } else if (_awaitingSpokenCaseTitle) {
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
    await _startSpeechListening(resetHandledText: true);
  }

  Future<void> _downloadRequestedDocuments() async {
    final sessionId = _apiClient.sessionId;
    if (sessionId != null && sessionId.isNotEmpty) {
      try {
        final exportOptions = await _apiClient.listDocumentExportOptions();
        if (exportOptions.isNotEmpty) {
          final selected = exportOptions.length == 1
              ? _DocumentDownloadOption.sessionExport(exportOptions.first)
              : await _showDocumentDownloadPicker(
                  exportOptions
                      .map(_DocumentDownloadOption.sessionExport)
                      .toList(growable: false),
                );
          if (selected?.export != null) {
            final savedFile =
                await _downloadDocumentExportPdf(selected!.export!);
            if (savedFile != null && mounted) {
              await _openSavedFile(context, _strings, savedFile.savedPath);
            }
          }
          return;
        }
      } catch (error, stackTrace) {
        await widget.logger.error(
          'Failed to list document export options',
          error,
          stackTrace,
        );
      }
    }

    final generatedDocumentId = _latestGeneratedCaseDocumentId;
    if ((_apiClient.sessionId == null || _apiClient.sessionId!.isEmpty) &&
        generatedDocumentId != null &&
        generatedDocumentId.trim().isNotEmpty) {
      final savedFile = await _downloadGeneratedCaseDocumentPdf(
        generatedDocumentId,
      );
      if (savedFile != null && mounted) {
        await _openSavedFile(context, _strings, savedFile.savedPath);
      }
      return;
    }
    if (_caseDocuments.length > 1) {
      final selected = await _showDocumentDownloadPicker(
        _caseDocuments
            .map(_DocumentDownloadOption.caseDocument)
            .toList(growable: false),
      );
      if (selected?.caseDocument != null) {
        final caseDocument = selected!.caseDocument!;
        if (caseDocument.kind == 'technical_payload') {
          final savedFile = await _downloadGeneratedCaseDocumentPdf(
            caseDocument.docId,
          );
          if (savedFile != null && mounted) {
            await _openSavedFile(context, _strings, savedFile.savedPath);
          }
        } else {
          await _downloadCaseDocument(caseDocument);
        }
      }
      return;
    }

    final savedFile = await _downloadPdf('document');
    if (!mounted || savedFile == null) {
      return;
    }
    await _openSavedFile(context, _strings, savedFile.savedPath);
  }

  Future<_SavedLocalFile?> _downloadDocumentExportPdf(
    DocumentExportOption option,
  ) async {
    if (_isDownloading) {
      return null;
    }
    setState(() {
      _isDownloading = true;
    });
    try {
      await widget.logger.info(
        'Document PDF export download requested',
        <String, Object?>{'index': option.index, 'filename': option.filename},
      );
      final payload = await _apiClient.downloadDocumentExportPdf(
        index: option.index,
        responderMode: _responderMode,
        locale: _selectedLocale,
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
        return _SavedLocalFile(
          fileName: payload.filename,
          savedPath: savedPath,
          contentType: payload.contentType,
        );
      }
      _showSnackbar(_strings.t('pdf_download_started', <String, String>{
        'filename': payload.filename,
      }));
    } on SessionExpiredException {
      _showSnackbar(
        _sessionExpiredMessageForLanguage(_selectedLocale.languageCode),
      );
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Document PDF export download failed',
        error,
        stackTrace,
        <String, Object?>{'index': option.index, 'filename': option.filename},
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
    return null;
  }

  Future<_SavedLocalFile?> _downloadGeneratedCaseDocumentPdf(
      String docId) async {
    final selected = _selectedCase;
    if (_isDownloading || selected == null || docId.trim().isEmpty) {
      return null;
    }
    setState(() {
      _isDownloading = true;
    });
    try {
      await widget.logger.info(
        'Generated case document PDF download requested',
        <String, Object?>{'case_id': selected.caseId, 'doc_id': docId},
      );
      final payload = await _apiClient.downloadGeneratedCaseDocumentPdf(
        caseId: selected.caseId,
        userId: _signedInUser.userId,
        docId: docId,
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
        return _SavedLocalFile(
          fileName: payload.filename,
          savedPath: savedPath,
          contentType: payload.contentType,
        );
      }
      _showSnackbar(_strings.t('pdf_download_started', <String, String>{
        'filename': payload.filename,
      }));
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Generated case document PDF download failed',
        error,
        stackTrace,
        <String, Object?>{'case_id': selected.caseId, 'doc_id': docId},
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
    return null;
  }

  Future<bool> _ensureCaseSelectedForOutgoingMessage(String message) async {
    if (_selectedCase != null) {
      return true;
    }
    final generatedTitle = generateCaseTitleFromDiscussion(
      message,
      languageCode: _selectedLocale.languageCode,
    );
    final created = await _createCaseWithTitle(
      generatedTitle,
      successMessage: _strings.t('case_auto_created', <String, String>{
        'name': generatedTitle,
      }),
    );
    return created != null;
  }

  Future<void> _toggleSpeechInputEnabled() async {
    if (!_speechEnabled) {
      _showSnackbar(_strings.t('speech_unavailable'));
      return;
    }

    final nextValue = !_speechInputEnabled;
    if (!nextValue && _isListening) {
      await _stopSpeechListening(
        submitAfterStop: false,
        processStoppedInput: false,
      );
    }
    if (!nextValue) {
      _lastHandledSpeechText = null;
    }

    if (!mounted) {
      return;
    }

    setState(() {
      _speechInputEnabled = nextValue;
      if (nextValue) {
        _speakerOutputEnabled = true;
      }
      if (!nextValue) {
        _awaitingSpokenName = false;
        _awaitingCaseArchiveConfirmation = false;
        _awaitingSpokenCaseTitle = false;
        _pendingNewCaseTitle = null;
        _lastDictatedSpeechDraft = null;
      }
    });

    if (nextValue) {
      await _speaker.stop();
      await _speakAssistantMessage(
        speechInputReadyMessage(
          _selectedLocale.languageCode,
          firstName: _signedInUser.firstName,
        ),
        resumeSpeechInputOnCompletion: true,
      );
    }

    await widget.logger.info(
      'Speech input toggle changed',
      <String, Object?>{
        'enabled': nextValue,
        'speaker_output_enabled': _speakerOutputEnabled,
        ..._voiceLogContext('speech_input_toggle'),
      },
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
    _updateCheckTimer?.cancel();
    _cancelSpeechSendPrompt();
    _voiceSessionOrchestrator.dispose();
    unawaited(_speaker.stop());
    _submitSpeechOnStop = false;
    _processSpeechOnStop = false;
    _speechRecognizer.stop();
    _inputController.dispose();
    _inputFocusNode.removeListener(_handleInputFocusChanged);
    _inputFocusNode.dispose();
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
    if (_selectedCase == null) {
      _showSnackbar(_strings.t('select_case'));
      return;
    }
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
    if (!mounted || path == null || path.isEmpty) {
      return;
    }
    await _uploadPlatformFiles(<PlatformFile>[
      PlatformFile(
          name: path.split(Platform.pathSeparator).last,
          path: path,
          size: await File(path).length()),
    ]);
  }

  Future<void> _pickDocuments() async {
    if (_selectedCase == null) {
      _showSnackbar(_strings.t('select_case'));
      return;
    }
    final result = await FilePicker.platform
        .pickFiles(allowMultiple: true, withData: true);
    if (result == null || result.files.isEmpty) {
      return;
    }
    await _uploadPlatformFiles(result.files);
  }

  Future<void> _uploadPlatformFiles(List<PlatformFile> files) async {
    final selected = _selectedCase;
    if (selected == null || files.isEmpty) {
      return;
    }
    final statusMessageId = _appendDocumentUploadStatusMessage(
      _strings.t('documents_uploading'),
    );
    try {
      final uploaded = await _apiClient.uploadCaseDocuments(
        caseId: selected.caseId,
        userId: _signedInUser.userId,
        files: files,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _caseDocuments = <CaseDocumentItem>[
          ...uploaded,
          ..._caseDocuments
        ].fold<List<CaseDocumentItem>>(<CaseDocumentItem>[], (items, document) {
          if (!items.any((existing) => existing.docId == document.docId)) {
            items.add(document);
          }
          return items;
        });
      });
      _syncCaseDocumentStatusThreadMessage(scrollToEnd: true);
      if (uploaded.isEmpty) {
        await _updateDocumentUploadStatusMessage(
          statusMessageId,
          content: _strings.t('documents_upload_error'),
          speak: true,
        );
        return;
      }
      unawaited(
        _queueUploadedDocumentAnalysis(
          batch: _PendingDocumentUploadBatch(
            caseId: selected.caseId,
            uploadedDocIds: uploaded.map((document) => document.docId).toSet(),
            statusMessageId: statusMessageId,
          ),
        ),
      );
    } catch (error) {
      await _updateDocumentUploadStatusMessage(
        statusMessageId,
        content: _strings.t('documents_upload_error'),
        speak: true,
      );
      _showSnackbar(_strings.t('documents_upload_error'));
      await widget.logger.error(
        'Failed to upload case documents',
        error,
        StackTrace.current,
        <String, Object?>{
          'case_id': selected.caseId,
          'file_count': files.length,
        },
      );
    }
  }

  Future<void> _queueUploadedDocumentAnalysis({
    required _PendingDocumentUploadBatch batch,
  }) async {
    if (batch.uploadedDocIds.isEmpty) {
      await _updateDocumentUploadStatusMessage(
        batch.statusMessageId,
        content: _strings.t('documents_upload_error'),
        speak: true,
      );
      return;
    }
    _queuedDocumentUploadBatches.add(batch);
    if (_documentAutoAnalysisInProgress) {
      return;
    }
    _documentAutoAnalysisInProgress = true;
    try {
      while (_queuedDocumentUploadBatches.isNotEmpty) {
        final currentBatch = _queuedDocumentUploadBatches.removeAt(0);
        if (!mounted || _selectedCase?.caseId != currentBatch.caseId) {
          _queuedDocumentUploadBatches.clear();
          return;
        }
        final result = await _waitForUploadedDocumentsToReachTerminalState(
          caseId: currentBatch.caseId,
          uploadedDocIds: currentBatch.uploadedDocIds,
        );
        if (!mounted || _selectedCase?.caseId != currentBatch.caseId) {
          return;
        }
        final uploadSucceeded = result.completed && !result.hasFailures;
        await _updateDocumentUploadStatusMessage(
          currentBatch.statusMessageId,
          content: _strings.t(
            uploadSucceeded ? 'documents_uploaded' : 'documents_upload_error',
          ),
          speak: true,
        );
        if (!uploadSucceeded) {
          continue;
        }
        await _waitForSendChannelToBeIdle();
        if (!mounted || _selectedCase?.caseId != currentBatch.caseId) {
          return;
        }
        final prompt = _documentAutoAnalysisPrompt(
          languageCode: _selectedLocale.languageCode,
          countryCode: _selectedLocale.countryCode,
        );
        await widget.logger.info(
          'Automatic document analysis triggered',
          <String, Object?>{
            'case_id': currentBatch.caseId,
            'document_count': currentBatch.uploadedDocIds.length,
          },
        );
        await _submitMessageText(
          prompt,
          appendUserMessage: false,
          includeAttachedDocumentPath: false,
          speakAssistantReply: false,
          interceptDocumentIntent: false,
        );
      }
    } finally {
      _documentAutoAnalysisInProgress = false;
    }
  }

  Future<_DocumentUploadWaitResult>
      _waitForUploadedDocumentsToReachTerminalState({
    required String caseId,
    required Set<String> uploadedDocIds,
  }) async {
    const maxAttempts = 30;
    for (var attempt = 0; attempt < maxAttempts; attempt++) {
      if (!mounted || _selectedCase?.caseId != caseId) {
        return const _DocumentUploadWaitResult(
          completed: false,
          hasFailures: true,
        );
      }
      try {
        final documents = await _apiClient.loadCaseDocumentsSnapshot(
          caseId: caseId,
          userId: _signedInUser.userId,
        );
        if (!mounted || _selectedCase?.caseId != caseId) {
          return const _DocumentUploadWaitResult(
            completed: false,
            hasFailures: true,
          );
        }
        setState(() {
          _caseDocuments = documents;
        });
        _syncCaseDocumentStatusThreadMessage(scrollToEnd: true);
        final tracked = documents
            .where((document) => uploadedDocIds.contains(document.docId))
            .toList(growable: false);
        final allTerminal = tracked.length == uploadedDocIds.length &&
            tracked.every((document) {
              final status = document.processingStatus.toLowerCase();
              return status == 'processed' || status == 'failed';
            });
        if (allTerminal) {
          final hasFailures = tracked.any(
            (document) => document.processingStatus.toLowerCase() == 'failed',
          );
          return _DocumentUploadWaitResult(
            completed: true,
            hasFailures: hasFailures,
          );
        }
      } catch (error, stackTrace) {
        await widget.logger.error(
          'Failed to poll uploaded document processing state',
          error,
          stackTrace,
          <String, Object?>{
            'case_id': caseId,
            'tracked_document_count': uploadedDocIds.length,
            'attempt': attempt + 1,
          },
        );
      }
      await Future<void>.delayed(const Duration(seconds: 3));
    }
    return const _DocumentUploadWaitResult(
      completed: false,
      hasFailures: true,
    );
  }

  Future<void> _waitForSendChannelToBeIdle() async {
    while (mounted && _isSending) {
      await Future<void>.delayed(const Duration(milliseconds: 250));
    }
  }

  Future<void> _refreshSessionResultDetails() async {
    try {
      final details = await _apiClient.loadSessionResultDetails();
      if (!mounted) {
        return;
      }
      setState(() {
        _latestSessionResult = details;
        _hasExportReady = (details?.documentReady ?? false) ||
            _latestGeneratedCaseDocumentId != null;
      });
      _syncValidationThreadMessage(scrollToEnd: true);
    } catch (error, stackTrace) {
      await widget.logger.error(
        'Failed to refresh session result metadata',
        error,
        stackTrace,
      );
    }
  }

  Future<void> _sendMessage() async {
    if (_isListening) {
      await _stopSpeechListening(submitAfterStop: true);
      _setInputComposerExpanded(false, unfocus: true);
      return;
    }
    final text = _inputController.text.trim();
    if (text.isEmpty || _isSending) {
      return;
    }

    _lastHandledSpeechText = null;
    _setInputComposerExpanded(false, unfocus: true);
    if (_shouldRouteProfilePatchViaRule(text)) {
      final action = _ruleEngine.evaluate(
        input: text,
        context: _buildRuleEngineContext(
          submitMessageWhenNoRuleMatches: true,
        ),
      );
      _voiceSessionOrchestrator.enqueueActionForTranscript(
        action: action,
        transcript: text,
        speechStartedAt: DateTime.now(),
      );
      await _drainVoiceActionQueue();
      return;
    }

    final handledCommand = await _tryHandleUserCommand(
      text,
      appendUserMessage: true,
    );
    if (handledCommand) {
      return;
    }

    final action = _ruleEngine.evaluate(
      input: text,
      context: _buildRuleEngineContext(
        submitMessageWhenNoRuleMatches: true,
      ),
    );
    _voiceSessionOrchestrator.enqueueActionForTranscript(
      action: action,
      transcript: text,
      speechStartedAt: DateTime.now(),
    );
    await _drainVoiceActionQueue();
  }

  Future<void> _submitMessageText(
    String text, {
    bool appendUserMessage = true,
    bool includeAttachedDocumentPath = true,
    bool speakAssistantReply = true,
    bool interceptDocumentIntent = true,
  }) async {
    if (interceptDocumentIntent) {
      final handled = await _handleDocumentIntentBeforeSend(
        text,
        appendUserMessage: appendUserMessage,
      );
      if (handled) {
        return;
      }
    }
    final activeDocumentPath =
        includeAttachedDocumentPath ? _documentPath : null;
    final caseReady = await _ensureCaseSelectedForOutgoingMessage(text);
    if (!caseReady || _selectedCase == null) {
      return;
    }
    await widget.logger.info(
      'User message submission',
      <String, Object?>{
        'message_length': text.length,
        'has_document_path': activeDocumentPath != null,
        'responder_mode': _responderMode.name,
        'append_user_message': appendUserMessage,
      },
    );

    setState(() {
      _isSending = true;
      _hasExportReady = false;
      _latestGeneratedCaseDocumentId = null;
      if (appendUserMessage && _selectedCase != null) {
        _caseHistoryOffset += 1;
      }
      if (appendUserMessage) {
        _messages.add(
          ChatMessage(
            role: 'user',
            content: text,
            documentPath: activeDocumentPath,
            createdAt: DateTime.now(),
          ),
        );
      }
    });

    if (appendUserMessage) {
      _inputController.clear();
      _lastDictatedSpeechDraft = null;
    }
    if (appendUserMessage) {
      _scrollToLatest();
    }
    final frontendThinkingMessageId = _appendFrontendThinkingMessage();

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
          documentPath: activeDocumentPath,
        )) {
          if (event.event == 'message' && event.data is Map) {
            final payload = Map<String, dynamic>.from(event.data as Map);
            final role = (payload['role'] as String? ?? 'assistant')
                .toLowerCase()
                .trim();
            final content = payload['content'] as String? ?? '';
            final visibleContent = role == 'assistant'
                ? _resolveAssistantVisibleReply(
                    rawReply: content,
                    exportReady: false,
                  )
                : _sanitizeVisibleMessageContent(content);
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
            if (role == 'assistant' && speakAssistantReply) {
              unawaited(
                _speakAssistantMessage(
                  visibleContent,
                  resumeSpeechInputOnCompletion: _speakerOutputEnabled,
                ),
              );
            }
          }
          if (event.event == 'result' && event.data is Map) {
            final result = SessionResultDetails.fromJson(
              Map<String, dynamic>.from(event.data as Map),
            );
            if (mounted) {
              setState(() {
                _latestSessionResult = result;
                _hasExportReady = result.documentReady ||
                    _latestGeneratedCaseDocumentId != null;
              });
              _syncValidationThreadMessage(scrollToEnd: false);
            }
          }
          if (event.event == 'done') {
            await _refreshSessionResultDetails();
          }
          if (event.event == 'error') {
            throw Exception('Discussion stream reported error: ${event.data}');
          }
        }
      } else {
        final streamInstruction = activeDocumentPath == null
            ? text
            : '$text\n\n[Attached local document path: $activeDocumentPath]';
        var skippedEchoedUserMessage = false;
        await for (final event in _apiClient.startReadUserTurnStream(
          instruction: streamInstruction,
          locale: _selectedLocale,
          questionTimeoutSeconds: _questionTimeoutSeconds,
          maxDiscussionMinutes: _maxDiscussionMinutes,
          communicationMinutes: _communicationMinutes,
          documentPath: activeDocumentPath,
        )) {
          if (event.event == 'processing' && event.data is Map) {
            final payload = Map<String, dynamic>.from(event.data as Map);
            final backendMessage = (payload['message'] as String? ?? '').trim();
            if (backendMessage.isNotEmpty) {
              _appendBackendProcessingMessage(backendMessage);
            } else {
              _appendBackendProcessingMessage(
                _strings.t('backend_processing_fallback_message'),
              );
            }
            continue;
          }
          if (event.event == 'message' && event.data is Map) {
            final payload = Map<String, dynamic>.from(event.data as Map);
            final role = (payload['role'] as String? ?? 'assistant')
                .toLowerCase()
                .trim();
            final content = payload['content'] as String? ?? '';
            final visibleContent = role == 'assistant'
                ? _resolveAssistantVisibleReply(
                    rawReply: content,
                    exportReady: false,
                  )
                : _sanitizeVisibleMessageContent(content);
            final agentName = payload['agent_name'] as String?;
            if (visibleContent.isEmpty) {
              continue;
            }
            if (!mounted) {
              continue;
            }
            if (!skippedEchoedUserMessage &&
                role == 'user' &&
                visibleContent.trim() == text.trim()) {
              skippedEchoedUserMessage = true;
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
            if (role == 'assistant' && speakAssistantReply) {
              unawaited(
                _speakAssistantMessage(
                  visibleContent,
                  resumeSpeechInputOnCompletion: _speakerOutputEnabled,
                ),
              );
            }
          }
          if (event.event == 'result' && event.data is Map) {
            final result = SessionResultDetails.fromJson(
              Map<String, dynamic>.from(event.data as Map),
            );
            if (mounted) {
              setState(() {
                _latestSessionResult = result;
                _hasExportReady = result.documentReady ||
                    _latestGeneratedCaseDocumentId != null;
              });
              _syncValidationThreadMessage(scrollToEnd: false);
            }
          }
          if (event.event == 'done') {
            await _refreshSessionResultDetails();
          }
          if (event.event == 'error') {
            throw Exception('ReadUser stream reported error: ${event.data}');
          }
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
      _removeThreadMessage(frontendThinkingMessageId);
      if (mounted) {
        setState(() {
          _isSending = false;
        });
      }
      if (_resumeSpeechInputAfterSend && mounted) {
        _resumeSpeechInputAfterSend = false;
        await _resumeSpeechListeningAfterAssistantSpeech(
          reason: 'message_submission_finished',
        );
      }
    }
  }

  Future<bool> _handleDocumentIntentBeforeSend(
    String text, {
    required bool appendUserMessage,
  }) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty || _isInternalDocumentAutoAnalysisPrompt(trimmed)) {
      return false;
    }
    final statusRequest = _isDocumentStatusRequest(trimmed);
    final operationRequest = _isDocumentOperationRequest(trimmed);
    if (!statusRequest && !operationRequest) {
      return false;
    }
    if (_selectedCase == null) {
      _showSnackbar(_strings.t('create_or_select_case'));
      return true;
    }
    try {
      final documents = await _apiClient.loadCaseDocumentsSnapshot(
        caseId: _selectedCase!.caseId,
        userId: _signedInUser.userId,
      );
      if (mounted) {
        setState(() {
          _caseDocuments = documents;
        });
        _syncCaseDocumentStatusThreadMessage(scrollToEnd: false);
      }
    } catch (_) {}
    if (statusRequest) {
      if (appendUserMessage) {
        _appendUserMessageLocally(trimmed);
      }
      _appendAssistantMessage(_buildCaseDocumentStatusMessage(), speak: false);
      return true;
    }
    final pendingDocuments = _caseDocuments
        .where((document) =>
            document.processingStatus.toLowerCase() != 'processed')
        .toList(growable: false);
    if (pendingDocuments.isEmpty) {
      return false;
    }
    if (appendUserMessage) {
      _appendUserMessageLocally(trimmed);
    }
    final pendingNames = pendingDocuments
        .map((document) =>
            '${document.originalFilename} (${_localizedDocumentStatusLabel(document.processingStatus)})')
        .join(', ');
    _appendAssistantMessage(
      _strings.t('document_status_pending_message', <String, String>{
        'documents': pendingNames,
      }),
      speak: false,
    );
    return true;
  }

  bool _isDocumentStatusRequest(String text) {
    final normalized = ' ${text.toLowerCase().trim()} ';
    const phrases = <String>[
      ' document status ',
      ' status of documents ',
      ' status documents ',
      ' uploaded documents status ',
      ' stav dokumentov ',
      ' status dokumentov ',
      ' dokument status ',
      ' dokumenty status ',
      ' dokumentstatus ',
      ' status der dokumente ',
      ' status von dokumenten ',
    ];
    return phrases.any(normalized.contains);
  }

  bool _isDocumentOperationRequest(String text) {
    final normalized = text.toLowerCase().trim();
    final documentWords = <String>[
      'document',
      'documents',
      'uploaded',
      'upload',
      'pdf',
      'contract',
      'dokument',
      'dokumenty',
      'pdf',
      'zmluva',
      'zmluvy',
      'vertrag',
      'dokumente',
    ];
    final actionWords = <String>[
      'summary',
      'summarize',
      'analyse',
      'analyze',
      'analysis',
      'review',
      'check',
      'compare',
      'zhrn',
      'zhrnut',
      'analyz',
      'skontrol',
      'porovnaj',
      'zusammen',
      'analys',
      'prüf',
      'pruef',
      'vergleich',
    ];
    final mentionsDocument = documentWords.any(normalized.contains);
    final mentionsAction = actionWords.any(normalized.contains);
    return mentionsDocument && mentionsAction;
  }

  String _buildCaseDocumentStatusMessage() {
    if (_caseDocuments.isEmpty) {
      return _strings.t('document_status_report_empty');
    }
    final lines = <String>[_strings.t('document_status_report_intro')];
    for (final document in _caseDocuments) {
      lines.add(
        '- ${document.originalFilename}: ${_localizedDocumentStatusLabel(document.processingStatus)}',
      );
    }
    return lines.join('\n');
  }

  String _localizedDocumentStatusLabel(String status) {
    switch (status.toLowerCase()) {
      case 'uploaded':
        return _strings.t('document_status_uploaded');
      case 'processing':
        return _strings.t('document_status_processing');
      case 'processed':
        return _strings.t('document_status_processed');
      case 'failed':
        return _strings.t('document_status_failed');
      default:
        return _strings.t('document_status_unknown');
    }
  }

  String _documentStatusSubtitle(CaseDocumentItem document) {
    final status = _localizedDocumentStatusLabel(document.processingStatus);
    if (document.processingStatus.toLowerCase() == 'failed' &&
        document.processingError != null &&
        document.processingError!.trim().isNotEmpty) {
      return '$status • ${document.processingError!.trim()}';
    }
    if (document.processingStatus.toLowerCase() == 'processed') {
      return '$status • ${_strings.t('document_status_ready')}';
    }
    return status;
  }

  Future<_SavedLocalFile?> _downloadPdf(String kind) async {
    if (_isDownloading) {
      return null;
    }
    if (!_hasExportReady) {
      _showSnackbar(_strings.t('pdf_not_ready'));
      return null;
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
        return _SavedLocalFile(
          fileName: payload.filename,
          savedPath: savedPath,
          contentType: payload.contentType,
        );
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
    return null;
  }

  Future<void> _openAccountSettings() async {
    final previousUser = _signedInUser;
    final updated = await Navigator.of(context).push<LocalAuthUser>(
      MaterialPageRoute<LocalAuthUser>(
        builder: (_) => AccountSettingsPage(
          user: _signedInUser,
          authStore: widget.authStore,
          selectedLocale: _selectedLocale,
          locales: appLocaleOptions,
          speaker: _speaker,
          speakerOutputEnabled: _speakerOutputEnabled,
          onSpeakerOutputChanged: _setSpeakerOutputEnabled,
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
    _appendProfileNameChangedMessage(
      previousUser: previousUser,
      updated: updated,
    );
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
      _latestGeneratedCaseDocumentId = null;
    });
    ProviderScope.containerOf(context, listen: false)
        .read(appLocaleProvider.notifier)
        .setLocale(locale);
    if (_isListening) {
      await _speechRecognizer.stop();
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
    unawaited(_refreshSystemLawDate());
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
      final preferredCaseId =
          _selectedCase?.caseId ?? await _readPersistedSelectedCaseId();
      final selected = _resolvePreferredCase(
        cases: cases,
        preferredCaseId: preferredCaseId,
      );
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

  CaseSummary? _resolvePreferredCase({
    required List<CaseSummary> cases,
    required String? preferredCaseId,
  }) {
    if (cases.isEmpty) {
      return null;
    }
    if (preferredCaseId == null || preferredCaseId.trim().isEmpty) {
      return cases.first;
    }
    for (final item in cases) {
      if (item.caseId == preferredCaseId) {
        return item;
      }
    }
    return cases.first;
  }

  Future<void> _persistSelectedCaseId(String? caseId) async {
    final prefs = await SharedPreferences.getInstance();
    final key = _selectedCaseStorageKey();
    if (caseId == null || caseId.trim().isEmpty) {
      await prefs.remove(key);
      return;
    }
    await prefs.setString(key, caseId.trim());
  }

  Future<String?> _readPersistedSelectedCaseId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_selectedCaseStorageKey());
  }

  String _selectedCaseStorageKey() {
    final baseUri = Uri.parse(widget.apiBaseUrl);
    final buffer = StringBuffer()
      ..write(_selectedCaseKeyPrefix)
      ..write('_')
      ..write(baseUri.scheme.toLowerCase())
      ..write('_')
      ..write(baseUri.host.toLowerCase())
      ..write('_')
      ..write(_signedInUser.userId);
    if (baseUri.hasPort) {
      buffer
        ..write('_')
        ..write(baseUri.port);
    }
    final normalizedPath = baseUri.path.trim();
    if (normalizedPath.isNotEmpty && normalizedPath != '/') {
      buffer
        ..write('_')
        ..write(normalizedPath);
    }
    return buffer
        .toString()
        .replaceAll(RegExp(r'[^a-z0-9]+'), '_')
        .replaceAll(RegExp(r'_+'), '_')
        .replaceFirst(RegExp(r'^_+'), '')
        .replaceFirst(RegExp(r'_+$'), '');
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
          textAlignVertical: TextAlignVertical.top,
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
    await _createCaseWithTitle(title.trim());
  }

  Future<void> _startSpeechListening({bool resetHandledText = false}) async {
    if (resetHandledText) {
      _lastHandledSpeechText = null;
    }
    _lastFinalSpeechResult = null;
    _submitSpeechOnStop = true;
    _processSpeechOnStop = true;
    _speechRecognitionStartedAt = DateTime.now();
    _voiceSessionOrchestrator.startListening(
      now: _speechRecognitionStartedAt,
    );
    await _speechRecognizer.listen(
      onResult: _onSpeechResult,
      listenFor: _speechMaxListenDuration,
      pauseFor: _speechSilenceTimeout,
      localeId: _localeIdForSpeech(_selectedLocale),
      listenMode: ListenMode.dictation,
    );
    await widget.logger.info(
      'Speech listening started',
      <String, Object?>{
        'locale': _localeIdForSpeech(_selectedLocale),
        ..._voiceLogContext('speech_to_text'),
      },
    );
  }

  Future<void> _promptForSpokenCaseTitle() async {
    if (_cases.length >= 5) {
      _showSnackbar(_strings.t('maximum_cases'));
      return;
    }
    if (_isListening) {
      await _stopSpeechListening(
        submitAfterStop: false,
        processStoppedInput: false,
      );
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _awaitingSpokenCaseTitle = true;
      _inputController.clear();
    });
    final prompt = _strings.t('case_voice_name_prompt');
    _appendAssistantMessage(prompt, speak: false);
    await _speaker.stop();
    await _speakAssistantMessage(prompt);
    if (!mounted || !_speechEnabled || !_speechInputEnabled) {
      return;
    }
    await _startSpeechListening(resetHandledText: true);
  }

  Future<void> _createCaseFromVoice(
    String spokenTitle, {
    String? originatingRequest,
  }) async {
    final title = spokenTitle.trim();
    if (title.isEmpty) {
      final retryPrompt = _strings.t('case_voice_name_retry');
      _appendAssistantMessage(retryPrompt);
      return;
    }
    await _createCaseWithTitle(
      title,
      originatingRequest: originatingRequest,
      successMessage:
          _strings.t('case_voice_created_continue', <String, String>{
        'name': title,
      }),
    );
  }

  Future<CaseSummary?> _createCaseWithTitle(
    String title, {
    String? successMessage,
    String? originatingRequest,
  }) async {
    final normalizedTitle = title.trim();
    if (normalizedTitle.isEmpty) {
      return null;
    }
    if (_cases.length >= 5) {
      _showSnackbar(_strings.t('maximum_cases'));
      return null;
    }
    try {
      final created = await _apiClient.createCase(
        userId: _signedInUser.userId,
        title: normalizedTitle,
      );
      if (!mounted) {
        return null;
      }
      setState(() {
        _cases = <CaseSummary>[created, ..._cases];
        _awaitingCaseArchiveConfirmation = false;
        _awaitingSpokenCaseTitle = false;
        _pendingNewCaseTitle = null;
        _inputController.clear();
      });
      await _selectCase(created);
      if (originatingRequest != null && originatingRequest.trim().isNotEmpty) {
        _appendUserMessageLocally(originatingRequest);
      }
      if (successMessage != null && successMessage.trim().isNotEmpty) {
        _appendAssistantMessage(successMessage);
      } else {
        _showSnackbar(_strings.t('case_created'));
      }
      return created;
    } catch (error) {
      if (!mounted) {
        return null;
      }
      setState(() {
        _awaitingCaseArchiveConfirmation = false;
        _awaitingSpokenCaseTitle = false;
        _pendingNewCaseTitle = null;
      });
      _showSnackbar('$error');
      return null;
    }
  }

  Future<void> _renameSelectedCase() async {
    final selected = _selectedCase;
    if (selected == null) return;
    try {
      final documents = await _apiClient.loadCaseDocumentsSnapshot(
        caseId: selected.caseId,
        userId: _signedInUser.userId,
      );
      if (mounted) {
        setState(() {
          _caseDocuments = documents;
        });
      }
    } catch (_) {}
    if (!mounted) {
      return;
    }
    final controller = TextEditingController(text: selected.title);
    final strings = _strings;
    final dialogResult = await showDialog<CaseEditDialogResult>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(strings.t('rename_case')),
        content: SizedBox(
          width: 420,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextField(controller: controller),
                const SizedBox(height: 16),
                Text(
                  strings.t('case_documents'),
                  style: Theme.of(context).textTheme.titleSmall,
                ),
                const SizedBox(height: 8),
                if (_caseDocuments.isEmpty)
                  Text(strings.t('no_case_documents'))
                else
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxHeight: 220),
                    child: ListView.separated(
                      shrinkWrap: true,
                      itemCount: _caseDocuments.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (context, index) {
                        final document = _caseDocuments[index];
                        final status = document.processingStatus.toLowerCase();
                        final leadingIcon = switch (status) {
                          'processed' => Icons.check_circle_outline,
                          'failed' => Icons.error_outline,
                          'processing' => Icons.sync,
                          _ => Icons.schedule,
                        };
                        return ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: Icon(leadingIcon),
                          title: Text(document.originalFilename),
                          subtitle: Text(_documentStatusSubtitle(document)),
                          trailing: IconButton(
                            icon: const Icon(Icons.share_outlined),
                            tooltip: strings.t(
                              'share_case_document',
                              <String, String>{
                                'filename': document.originalFilename,
                              },
                            ),
                            onPressed: () => _shareCaseDocument(document),
                          ),
                          onTap: () => Navigator.pop(
                            context,
                            CaseEditDialogResult(documentToOpen: document),
                          ),
                        );
                      },
                    ),
                  ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(strings.t('cancel')),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(
              context,
              CaseEditDialogResult(renamedTitle: controller.text.trim()),
            ),
            child: Text(strings.t('save')),
          ),
        ],
      ),
    );

    final documentToOpen = dialogResult?.documentToOpen;
    if (documentToOpen != null) {
      await _downloadCaseDocument(documentToOpen);
      return;
    }

    final title = dialogResult?.renamedTitle;
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

  Future<_DocumentDownloadOption?> _showDocumentDownloadPicker(
    List<_DocumentDownloadOption> documents,
  ) {
    return showModalBottomSheet<_DocumentDownloadOption>(
      context: context,
      builder: (context) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _strings.t('available_documents_title'),
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      _strings.t('available_documents_subtitle'),
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              Flexible(
                child: ListView.separated(
                  shrinkWrap: true,
                  itemCount: documents.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    final document = documents[index];
                    return ListTile(
                      leading: const Icon(Icons.picture_as_pdf_outlined),
                      title: Text(document.title),
                      subtitle: Text(document.subtitle),
                      onTap: () => Navigator.of(context).pop(document),
                    );
                  },
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildComposerInputField({
    required AppStrings strings,
    required bool expanded,
  }) {
    return TextField(
      controller: _inputController,
      focusNode: _inputFocusNode,
      minLines: expanded ? 5 : 1,
      maxLines: expanded ? 5 : 1,
      expands: false,
      keyboardType: TextInputType.multiline,
      textInputAction:
          expanded ? TextInputAction.newline : TextInputAction.send,
      onSubmitted: expanded ? null : (_) => _sendMessage(),
      onTap: () => _setInputComposerExpanded(true),
      onTapOutside: (_) => _setInputComposerExpanded(false, unfocus: true),
      textAlignVertical: TextAlignVertical.top,
      decoration: InputDecoration(
        hintText: _responderMode == ResponderMode.aiUserSimulator
            ? strings.t('case_input_discussion')
            : strings.t('case_input_question'),
        filled: true,
        fillColor: Colors.white,
        alignLabelWithHint: expanded,
        border: const OutlineInputBorder(),
      ),
    );
  }

  String _localizedAgentName(String? rawAgentName, AppStrings strings) {
    final normalized = (rawAgentName ?? '').trim().toLowerCase();
    if (normalized.isEmpty) {
      return strings.t('assistant');
    }
    if (normalized.contains('lawyer')) {
      return strings.t('assistant');
    }
    return rawAgentName!.trim();
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
    if (_isOfflineError(error)) {
      if (mounted) {
        setState(() {
          _lastErrorCorrelationId = null;
        });
      } else {
        _lastErrorCorrelationId = null;
      }
      _showSnackbar(_strings.t('no_internet_connection'));
      return;
    }
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

  Future<void> _openLawCitation(LawCitationDetails citation) async {
    final rawUrl = citation.openUrl.trim().isNotEmpty
        ? citation.openUrl.trim()
        : citation.officialSourceUrl.trim();
    if (rawUrl.isEmpty) {
      _showSnackbar(_strings.t('law_citation_open_failed'));
      return;
    }
    final uri = Uri.tryParse(rawUrl);
    final resolvedUri = uri == null
        ? null
        : (uri.hasScheme ? uri : _apiClient.baseUri.resolveUri(uri));
    if (resolvedUri == null) {
      _showSnackbar(_strings.t('law_citation_open_failed'));
      return;
    }
    final opened = await launchUrl(
      resolvedUri,
      mode: LaunchMode.platformDefault,
    );
    if (!opened) {
      _showSnackbar(_strings.t('law_citation_open_failed'));
    }
  }

  Widget _buildLawCitationsPanel({
    required AppStrings strings,
    required SessionResultDetails result,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.94),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            strings.t('law_citations_title'),
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 8),
          for (final citation in result.lawCitations)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: OutlinedButton(
                onPressed: () => unawaited(_openLawCitation(citation)),
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.all(12),
                  alignment: Alignment.centerLeft,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      citation.label,
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    if (citation.effectiveFrom.trim().isNotEmpty)
                      Text(
                        '${strings.t('law_citation_effective_from')}: ${citation.effectiveFrom}',
                      ),
                    if (citation.versionToken.trim().isNotEmpty)
                      Text(
                        '${strings.t('law_citation_version')}: ${citation.versionToken}',
                      ),
                    if (citation.summary.trim().isNotEmpty)
                      Text(citation.summary),
                    const SizedBox(height: 4),
                    Text(strings.t('law_citation_open')),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final strings = _strings;
    final lawCitations =
        _latestSessionResult?.lawCitations ?? const <LawCitationDetails>[];
    return Scaffold(
      body: Stack(
        children: [
          const Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: <Color>[
                    Color(0xFF041B59),
                    Color(0xFF1388E9),
                    Color(0xFF041B59),
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
                if (_showLocalResponderSwitch)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
                    child: Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.94),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Row(
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
                                  _latestGeneratedCaseDocumentId = null;
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
                        final speaker = isUser
                            ? strings.t('you')
                            : _localizedAgentName(
                                message.agentName,
                                strings,
                              );
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
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 2, 12, 12),
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      Tooltip(
                        message: _speechInputEnabled
                            ? strings.t('speech_input_enabled')
                            : strings.t('speech_input_disabled'),
                        child: IconButton.filledTonal(
                          onPressed: _speechEnabled
                              ? () => unawaited(_toggleSpeechInputEnabled())
                              : null,
                          icon: Icon(
                            _speechInputEnabled ? Icons.mic : Icons.mic_off,
                          ),
                        ),
                      ),
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
                if (lawCitations.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                    child: _buildLawCitationsPanel(
                      strings: strings,
                      result: _latestSessionResult!,
                    ),
                  ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 2, 12, 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (_isInputComposerExpanded) ...[
                        Row(
                          children: [
                            IconButton(
                              onPressed: _captureDocument,
                              icon: const Icon(Icons.camera_alt_outlined),
                              tooltip: strings.t('capture_document'),
                            ),
                            IconButton(
                              onPressed: _pickDocuments,
                              icon: const Icon(Icons.upload_file),
                              tooltip: strings.t('upload_documents'),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        AnimatedContainer(
                          duration: const Duration(milliseconds: 180),
                          curve: Curves.easeOut,
                          height: (MediaQuery.sizeOf(context).height * 0.5) -
                              (MediaQuery.viewInsetsOf(context).bottom * 0.35),
                          child: _buildComposerInputField(
                            strings: strings,
                            expanded: true,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.end,
                          children: [
                            IconButton(
                              onPressed:
                                  _speechEnabled ? _toggleSpeechInput : null,
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
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : const Icon(Icons.send),
                              tooltip: _responderMode ==
                                      ResponderMode.aiUserSimulator
                                  ? strings.t('start_ai_discussion')
                                  : strings.t('send_to_api'),
                            ),
                          ],
                        ),
                      ] else
                        Row(
                          children: [
                            IconButton(
                              onPressed: _captureDocument,
                              icon: const Icon(Icons.camera_alt_outlined),
                              tooltip: strings.t('capture_document'),
                            ),
                            IconButton(
                              onPressed: _pickDocuments,
                              icon: const Icon(Icons.upload_file),
                              tooltip: strings.t('upload_documents'),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: _buildComposerInputField(
                                strings: strings,
                                expanded: false,
                              ),
                            ),
                            const SizedBox(width: 8),
                            IconButton(
                              onPressed:
                                  _speechEnabled ? _toggleSpeechInput : null,
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
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : const Icon(Icons.send),
                              tooltip: _responderMode ==
                                      ResponderMode.aiUserSimulator
                                  ? strings.t('start_ai_discussion')
                                  : strings.t('send_to_api'),
                            ),
                          ],
                        ),
                      const SizedBox(height: 6),
                      if (_voiceSessionStatusLabel() != null)
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 12),
                          child: Text(
                            _voiceSessionStatusLabel()!,
                            style: Theme.of(context)
                                .textTheme
                                .labelSmall
                                ?.copyWith(
                                  color: Theme.of(context).colorScheme.primary,
                                ),
                          ),
                        ),
                      if (_voiceSessionStatusLabel() != null)
                        const SizedBox(height: 6),
                      _buildUpgradeProgressCard(Theme.of(context), strings),
                      const SizedBox(height: 6),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                        child: Row(
                          children: [
                            Text(
                              _appVersionLabel,
                              style: Theme.of(context)
                                  .textTheme
                                  .bodySmall
                                  ?.copyWith(color: const Color(0xFF4A628A)),
                            ),
                            const Spacer(),
                            Text(
                              '${strings.t('law_date_label')}: ${_formatFooterLawDate(_effectiveSystemLawDate())}',
                              textAlign: TextAlign.right,
                              style: Theme.of(context)
                                  .textTheme
                                  .bodySmall
                                  ?.copyWith(color: const Color(0xFF4A628A)),
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
