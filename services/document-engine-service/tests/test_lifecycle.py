from document_engine.db import Base, SessionLocal, engine
from document_engine.repository import create_request, get_request
from document_engine.statuses import DocumentStatus
from document_engine.worker import run_once


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_worker_finishes_new_request() -> None:
    with SessionLocal() as session:
        request = create_request(
            session,
            document_type="confirmation",
            requested_by="tester@example.com",
            correlation_id="test-correlation",
            payload={
                "title": "Potvrdenie",
                "issuer": "JurisDigta",
                "recipient": "Client",
                "facts": "Test fact",
            },
        )

    assert run_once() == 1

    with SessionLocal() as session:
        stored = get_request(session, request.id)
        assert stored is not None
        assert stored.status == DocumentStatus.FINISHED.value
        assert stored.error_message is None
        assert stored.result is not None
        assert stored.result["format"] == "markdown"


def test_worker_marks_invalid_request_as_error() -> None:
    with SessionLocal() as session:
        request = create_request(
            session,
            document_type="power_of_attorney",
            requested_by=None,
            correlation_id="test-error-correlation",
            payload={"principal": "A"},
        )

    assert run_once() == 1

    with SessionLocal() as session:
        stored = get_request(session, request.id)
        assert stored is not None
        assert stored.status == DocumentStatus.ERROR.value
        assert stored.error_message is not None
        assert "Missing required fields" in stored.error_message
