# MCP server

- Endpoint: `GET /MCP`
- Auth header: `x-mcp-api-key`
- User profile now exposes `mcp_api_key_expires_at`.
- Manage key via:
  - `POST /v1/users/{user_id}/mcp-api-key` with `{ "expires_in_days": 30 }`
  - `DELETE /v1/users/{user_id}/mcp-api-key`

Security/GDPR notes: API key is stored hashed, only returned at creation, and can be revoked by delete endpoint.
