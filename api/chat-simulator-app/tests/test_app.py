from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main
from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_version() -> None:
    response = client.get('/version')
    assert response.status_code == 200
    assert response.json() == {
        'service': 'chat-simulator-app',
        'version': '0.1.27',
        'simulator_version': '0.1.27',
    }


def test_simulator_page_and_assets() -> None:
    page = client.get('/chat-simulator')
    assert page.status_code == 200
    assert '/static/simulator.js?v=0.1.27' in page.text
    assert '/static/simulator.css?v=0.1.27' in page.text
    assert '/email-tests' in page.text
    assert 'Email Validation Tests' in page.text
    assert '/speech-to-text' in page.text
    assert 'Speech to Text' in page.text
    assert 'Start Stream' in page.text
    assert 'Upload documents' in page.text
    assert 'Persisted Case Debug' in page.text
    assert 'Upload To Case' in page.text
    assert 'Refresh Existing Cases' in page.text
    assert 'Workflow Warning' in page.text
    assert 'http://127.0.0.1:8080' in page.text
    assert 'replyStatus' in page.text
    assert 'processingStatus' in page.text
    assert 'id="existingCase"' in page.text
    assert 'id="caseHistory"' in page.text
    assert 'id="caseDocumentsList"' in page.text
    assert 'id="documentViewer"' in page.text
    assert 'novalidate' in page.text
    assert 'id="preparedCase"' in page.text
    assert 'id="preparedCasesData"' in page.text
    assert 'id="userFirstName"' in page.text
    assert 'id="userLastName"' in page.text
    assert 'id="userAddress"' in page.text
    assert 'Document Templates' in page.text
    assert 'id="refreshDocumentTemplates"' in page.text
    assert 'id="documentTemplatesList"' in page.text
    assert 'sample_case_prenajom' in page.text
    assert 'sample_case_prenajom_contract' in page.text
    assert 'sample_case_vlastnik_fimy' in page.text
    assert 'ESolutions SK s.r.o.' in page.text
    assert 'Zmluva strana navrh' in page.text
    assert page.headers['cache-control'] == 'no-store, no-cache, must-revalidate, max-age=0'
    assert 'value="60"' in page.text
    assert 'value="30"' in page.text
    assert '<option value="ReadUser" selected>' in page.text
    persisted_controls = (
        'Ensure User</button>'
        in page.text
        and 'Inspect Stored Docs</button>' in page.text
        and 'Create Session</button>' in page.text
        and 'Clear Session</button>' in page.text
        and 'Delete All Cases</button>' in page.text
    )
    assert persisted_controls
    assert page.text.index('Inspect Stored Docs</button>') < page.text.index('Create Session</button>')

    js = client.get('/static/simulator.js')
    css = client.get('/static/simulator.css')

    assert js.status_code == 200
    assert css.status_code == 200
    assert 'normalizeApiBaseUrl' in js.text
    assert 'refreshReplyControls' in js.text
    assert 'Switch Reply mode to ReadUser before using Send answer.' in js.text
    assert 'streamStartedForSession' in js.text
    assert 'The simulator will start the stream automatically.' in js.text
    assert 'manual_reply_stream: sending ReadUser turn through /stream' in js.text
    assert 'Failed to stream reply, status=' in js.text
    assert 'appendInitialInstructionMessage' in js.text
    assert 'loadPreparedCases' in js.text
    assert 'deleteAllCases' in js.text
    assert 'Use Delete All Cases or remove one existing case first.' in js.text
    assert 'formatStreamEvent' in js.text
    assert 'tool:${data.tool_name}' in js.text
    assert 'MESSAGE_PREVIEW_LIMIT = 256' in js.text
    assert 'viac...' in js.text
    assert 'appendProcessingMessage' in js.text
    assert 'document_package_ready' in js.text
    assert 'document_status' in js.text
    assert 'localizedThinkingMessage' in js.text
    assert 'processing:thinking:' in js.text
    assert '_thinkingPlaceholder' in js.text
    assert 'Backend is processing your request...' in js.text
    assert 'handleStreamLifecycleEvent' in js.text
    assert 'Assistant is waiting for your answer.' in js.text
    assert 'Stream completed. You can ask a follow-up question or document status.' in js.text
    assert 'applyPreparedCaseDocuments' in js.text
    assert 'new DataTransfer()' in js.text
    assert 'preparedCasesDataEl' in js.text
    assert 'Create Case first before Create Session.' in js.text
    assert 'refreshExistingCases' in js.text
    assert 'selectExistingCase' in js.text
    assert 'viewCaseDocument' in js.text
    assert 'downloadCaseDocument' in js.text
    assert 'Existing case loaded. Click Create Session to continue this conversation on the selected case.' in js.text
    assert 'Type an answer and click Send answer. The simulator will start the stream automatically.' in js.text
    assert 'refreshPersistedCaseControls' in js.text
    assert '/internal/delete-user-cases' in js.text
    assert 'continue the session or ask for document status' in js.text
    assert 'refreshDocumentTemplates' in js.text
    assert 'generateTemplatePdf' in js.text
    assert 'first_name: userFirstNameInput.value.trim()' in js.text
    assert 'last_name: userLastNameInput.value.trim()' in js.text
    assert 'address: userAddressInput.value.trim()' in js.text
    assert '/v1/document-templates' in js.text
    assert '/preview/pdf' in js.text
    assert 'Generate PDF' in js.text
    assert 'template_pdf_generated' in js.text
    assert 'document-template-card' in css.text
    assert 'page-action' in css.text


def test_email_tests_page_and_assets() -> None:
    page = client.get('/email-tests')
    assert page.status_code == 200
    assert '/static/email-tests.js?v=0.1.27' in page.text
    assert 'Email Validation Tests' in page.text
    assert 'id="emailTransport"' in page.text
    assert '<option value="log" selected>log</option>' in page.text
    assert '<option value="smtp">smtp</option>' in page.text
    assert 'Open email logs' in page.text
    assert 'Open generated emails' in page.text
    assert 'Test: registration email' in page.text
    assert 'Test: mobile OTP email' in page.text
    assert 'Test: payment email' in page.text
    assert 'info@jurisdigta.eu' in page.text
    assert '+421944400166' in page.text
    assert page.headers['cache-control'] == 'no-store, no-cache, must-revalidate, max-age=0'

    js = client.get('/static/email-tests.js')
    assert js.status_code == 200
    assert '/internal/email-tests/send' in js.text
    assert 'emailPayload' in js.text
    assert 'smtp_password' in js.text
    assert 'Open latest email' in js.text


def test_email_test_log_transport_writes_log_and_email(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(main, '_EMAIL_TEST_RUNS_DIR', tmp_path)

    response = client.post(
        '/internal/email-tests/send',
        json={
            'transport': 'log',
            'template': 'registration',
            'recipient': 'recipient@example.com',
            'sender': 'no-reply@jurisdigta.eu',
            'first_name': 'Test',
            'last_name': 'User',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'logged'
    assert payload['links']['logs'] == '/internal/email-tests/logs'
    assert payload['links']['emails'] == '/internal/email-tests/emails'
    assert payload['links']['email'].endswith('.eml')

    logs = client.get('/internal/email-tests/logs')
    assert logs.status_code == 200
    assert 'recipient@example.com' in logs.text
    assert 'Your registration code' in logs.text

    emails = client.get('/internal/email-tests/emails')
    assert emails.status_code == 200
    assert payload['links']['email'].split('/')[-1] in emails.text

    message = client.get(payload['links']['email'])
    assert message.status_code == 200
    assert 'Your JurisDigta registration code is: 123456' in message.text
    assert 'The code expires in 30 minutes.' in message.text


def test_internal_delete_user_cases_route(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        '_delete_remote_user_cases',
        lambda payload: {
            'user_id': payload.user_id or 'user-1',
            'deleted_count': 2,
            'deleted_case_ids': ['case-a', 'case-b'],
            'failed_deletes': [],
        },
    )

    response = client.post(
        '/internal/delete-user-cases',
        json={
            'api_base_url': 'http://127.0.0.1:8080',
            'api_key': 'aijuris',
            'user_id': 'user-1',
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        'user_id': 'user-1',
        'deleted_count': 2,
        'deleted_case_ids': ['case-a', 'case-b'],
        'failed_deletes': [],
    }


def test_read_testcase_supports_case_descripton_typo_and_embeds_documents() -> None:
    testcase = main._read_testcase(
        Path(__file__).resolve().parents[1] / 'testcases' / 'sample_case_prenajom_contract.txt'
    )

    assert testcase['title'] == 'Prenajom bytu zmluva'
    assert 'Ako vypovedat zmvluvu?' in testcase['instruction']
    assert 'Co v pripade ze prestanu platit najomne?' in testcase['instruction']
    assert isinstance(testcase['documents'], list)
    assert len(testcase['documents']) == 1
    document = testcase['documents'][0]
    assert document['fileName'] == 'Zmluva strana navrh'
    assert document['sourcePath'] == 'najomna-zmluva-byt-sample.pdf'
    assert document['mimeType'] == 'application/pdf'
    assert len(document['contentBase64']) > 100


def test_speech_to_text_page() -> None:
    page = client.get('/speech-to-text')
    assert page.status_code == 200
    assert 'Speech to Text Tester' in page.text
    assert 'id="startListening"' in page.text
    assert 'id="sttTranscript"' in page.text
    assert 'SpeechRecognition' in page.text
