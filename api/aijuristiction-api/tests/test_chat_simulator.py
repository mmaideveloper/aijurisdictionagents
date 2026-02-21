from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_chat_simulator_page_is_served() -> None:
    response = client.get("/chat-simulator")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Chat Simulator" in response.text
    assert "/chat-simulator-assets/simulator.css" in response.text
    assert "/chat-simulator-assets/simulator.js" in response.text


def test_chat_simulator_static_assets_are_served() -> None:
    css_response = client.get("/chat-simulator-assets/simulator.css")
    js_response = client.get("/chat-simulator-assets/simulator.js")

    assert css_response.status_code == 200
    assert "text/css" in css_response.headers["content-type"]
    assert "button.secondary" in css_response.text

    assert js_response.status_code == 200
    assert "javascript" in js_response.headers["content-type"]
    assert "Message content cannot be empty." in js_response.text
