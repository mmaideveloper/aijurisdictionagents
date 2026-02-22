from fastapi.testclient import TestClient

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
        'version': '0.1.1',
        'simulator_version': '0.1.1',
    }


def test_simulator_page_and_assets() -> None:
    page = client.get('/chat-simulator')
    assert page.status_code == 200
    assert '/static/simulator.js' in page.text
    assert 'Start Stream' in page.text
    assert 'Upload documents' in page.text

    js = client.get('/static/simulator.js')
    css = client.get('/static/simulator.css')

    assert js.status_code == 200
    assert css.status_code == 200
