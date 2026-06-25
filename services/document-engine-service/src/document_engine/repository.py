from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from document_engine.models import DocumentRequest
from document_engine.statuses import DocumentStatus


def create_request(
    session: Session,
    *,
    document_type: str,
    payload: dict,
    requested_by: str | None,
    correlation_id: str | None,
) -> DocumentRequest:
    request = DocumentRequest(
        document_type=document_type,
        payload=payload,
        requested_by=requested_by,
    )
    if correlation_id:
        request.correlation_id = correlation_id
    session.add(request)
    session.commit()
    session.refresh(request)
    return request


def get_request(session: Session, request_id: str) -> DocumentRequest | None:
    return session.get(DocumentRequest, request_id)


def claim_next_requests(session: Session, *, batch_size: int) -> list[DocumentRequest]:
    candidates = session.scalars(
        select(DocumentRequest)
        .where(DocumentRequest.status == DocumentStatus.NEW.value)
        .order_by(DocumentRequest.created_at)
        .limit(batch_size)
    ).all()

    claimed: list[DocumentRequest] = []
    now = datetime.now(timezone.utc)
    for candidate in candidates:
        result = session.execute(
            update(DocumentRequest)
            .where(
                DocumentRequest.id == candidate.id,
                DocumentRequest.status == DocumentStatus.NEW.value,
            )
            .values(
                status=DocumentStatus.IN_PROGRESS.value,
                started_at=now,
                updated_at=now,
                error_message=None,
            )
        )
        if result.rowcount == 1:
            session.commit()
            refreshed = session.get(DocumentRequest, candidate.id)
            if refreshed is not None:
                claimed.append(refreshed)
        else:
            session.rollback()
    return claimed


def mark_finished(session: Session, request_id: str, result: dict) -> None:
    now = datetime.now(timezone.utc)
    session.execute(
        update(DocumentRequest)
        .where(DocumentRequest.id == request_id)
        .values(
            status=DocumentStatus.FINISHED.value,
            result=result,
            finished_at=now,
            updated_at=now,
            error_message=None,
        )
    )
    session.commit()


def mark_error(session: Session, request_id: str, error_message: str) -> None:
    now = datetime.now(timezone.utc)
    session.execute(
        update(DocumentRequest)
        .where(DocumentRequest.id == request_id)
        .values(
            status=DocumentStatus.ERROR.value,
            error_message=error_message,
            finished_at=now,
            updated_at=now,
        )
    )
    session.commit()
