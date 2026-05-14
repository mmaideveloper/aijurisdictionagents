from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from aijurisdictionagents.api_db import ApiDatabaseStore

router = APIRouter(prefix="/MCP", tags=["mcp"])


def get_user_store() -> ApiDatabaseStore:
    store = ApiDatabaseStore.from_env()
    store.initialize()
    return store


def require_mcp_api_key(
    x_mcp_api_key: str | None = Header(default=None),
    store: ApiDatabaseStore = Depends(get_user_store),
) -> str:
    if not x_mcp_api_key:
        raise HTTPException(status_code=401, detail="Missing x-mcp-api-key header")
    user = store.find_user_by_mcp_api_key(api_key=x_mcp_api_key)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired MCP API key")
    return str(user.user_id)


@router.get("")
def mcp_endpoint(user_id: str = Depends(require_mcp_api_key)) -> dict[str, str]:
    return {"status": "ok", "user_id": user_id}
