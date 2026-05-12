from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.law_citations import read_law_document_text, read_law_source
from app.security import require_api_key

router = APIRouter(prefix="/v1/laws", tags=["laws"], dependencies=[Depends(require_api_key)])


@router.get("/source")
def download_law_source(
    country_code: str = Query(..., min_length=2, max_length=2),
    collection_code: str = Query("ZZ", min_length=1, max_length=8),
    law_year: int = Query(..., ge=1900),
    law_number: int = Query(..., ge=1),
    version_token: str = Query(..., min_length=1),
    artifact_kind: str = Query("html", pattern="^(html|pdf)$"),
) -> Response:
    payload = read_law_source(
        country_code=country_code.strip().upper(),
        collection_code=collection_code.strip().upper(),
        law_year=law_year,
        law_number=law_number,
        version_token=version_token.strip(),
        artifact_kind=artifact_kind.strip().lower(),
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Law source artifact not found.")
    content, media_type, filename = payload
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )


@router.get("/document-text")
def get_law_document_text(
    document_id: str = Query(..., min_length=1),
) -> dict[str, str]:
    content = read_law_document_text(document_id=document_id.strip())
    if content is None:
        raise HTTPException(status_code=404, detail="Law document text not found.")
    return {"document_id": document_id.strip(), "content_text": content}
