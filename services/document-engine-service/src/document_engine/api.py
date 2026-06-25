from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

from document_engine.db import get_session, init_db
from document_engine.repository import create_request, get_request
from document_engine.schemas import (
    CreateDocumentRequest,
    DocumentRequestResponse,
    HealthResponse,
)


app = FastAPI(title="Document Engine Service", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post(
    "/document-requests",
    response_model=DocumentRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_document_request(
    body: CreateDocumentRequest,
    session: Session = Depends(get_session),
) -> DocumentRequestResponse:
    request = create_request(
        session,
        document_type=body.document_type,
        payload=body.payload,
        requested_by=body.requested_by,
        correlation_id=body.correlation_id,
    )
    return DocumentRequestResponse.model_validate(request)


@app.get("/document-requests/{request_id}", response_model=DocumentRequestResponse)
def get_document_request(
    request_id: str,
    session: Session = Depends(get_session),
) -> DocumentRequestResponse:
    request = get_request(session, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Document request not found")
    return DocumentRequestResponse.model_validate(request)
