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
        'version': '0.1.18',
        'simulator_version': '0.1.18',
    }


def test_simulator_page_and_assets() -> None:
    page = client.get('/chat-simulator')
    assert page.status_code == 200
    assert '/static/simulator.js?v=0.1.18' in page.text
    assert '/static/simulator.css?v=0.1.18' in page.text
    assert 'Start Stream' in page.text
    assert 'Upload documents' in page.text
    assert 'Persisted Case Debug' in page.text
    assert 'Upload To Case' in page.text
    assert 'Workflow Warning' in page.text
    assert 'http://127.0.0.1:8081' in page.text
    assert 'replyStatus' in page.text
    assert 'novalidate' in page.text
    assert 'id="preparedCase"' in page.text
    assert 'id="preparedCasesData"' in page.text
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
    assert 'localizedThinkingMessage' in js.text
    assert 'processing:thinking:' in js.text
    assert '_thinkingPlaceholder' in js.text
    assert 'applyPreparedCaseDocuments' in js.text
    assert 'new DataTransfer()' in js.text
    assert 'preparedCasesDataEl' in js.text
    assert 'Create Case first before Create Session.' in js.text
    assert 'refreshPersistedCaseControls' in js.text
    assert '/internal/delete-user-cases' in js.text


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
