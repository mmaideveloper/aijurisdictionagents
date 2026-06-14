# MCP server

The API exposes a Streamable HTTP-style MCP JSON-RPC endpoint at `POST /MCP`.
It is intended for AI assistants that can connect to remote MCP servers over HTTP.
For ChatGPT, Claude, and VS Code OAuth-capable clients, start from the OAuth metadata endpoints instead of manually copying a token.

## OAuth Discovery

- Protected resource metadata: `GET /.well-known/oauth-protected-resource/MCP`
- Authorization server metadata: `GET /.well-known/oauth-authorization-server`
- Authorization endpoint: `GET /oauth/authorize`
- Token endpoint: `POST /oauth/token`

The OAuth flow uses authorization code with PKCE S256. The browser authorization page validates the user password, sends an email OTP, and only creates a short-lived authorization code after OTP verification. The token endpoint exchanges that code for the same revocable JWT bearer token accepted by `POST /MCP`.

## Authentication

- MCP API keys are per user.
- Default key lifetime is 1 day.
- Keys are signed JWT bearer tokens and are only shown once at creation.
- JWT claims are minimized to `sub`, `email`, `exp`, and `jti`.
- The full token is still stored hashed in the database so it can be revoked.
- Protected MCP tools accept either `Authorization: Bearer <mcp_api_key>` or `x-mcp-api-key: <mcp_api_key>`.

Users can generate a key in either way:

- Browser login page: `GET /MCP/login`, then submit username/email and password. The API emails an OTP code to the user. Submitting the OTP at `POST /MCP/login/verify` generates and stores the MCP API key.
- Browser sign-up page: `GET /MCP/sign-up`, then submit email, phone number, password, first name, last name, address, ID card number, and data-processing consent. The API emails an OTP code. Submitting the OTP at `POST /MCP/sign-up/verify` creates the user; the user can then log in to generate an MCP API key.
- API endpoint: `POST /v1/users/{user_id}/mcp-api-key` with optional `{ "expires_in_days": 1 }`.

Keys can be revoked with:

- `DELETE /v1/users/{user_id}/mcp-api-key`

Manual JWT generation remains useful for local VS Code setups that pass an `Authorization` header directly. Standards-based remote clients should prefer OAuth discovery.

## Public Tools

These tools do not require an MCP API key:

- `getVersion`: returns API, system/core, mobile app, and web app versions.
- `getStatistics`: returns processed laws count, last processed law, last processed day, and collector details.

## Protected Tools

These tools require an MCP API key:

- `searchLaws`: searches imported laws by title, identifier, and lawyer-facing title.
- `getLawText`: returns latest imported text for a law document id.

## Minimal JSON-RPC Example

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "searchLaws",
    "arguments": {
      "query": "civil",
      "country_code": "SK",
      "limit": 10
    }
  }
}
```

For protected tools, send the MCP API key as a Bearer token or `x-mcp-api-key` header.

## Logging And Debugging

MCP server logs use the `aijuristiction-api.mcp` logger and the API-wide `API_LOG_LEVEL` or `LOG_LEVEL` setting.
Each JSON-RPC request logs request and correlation IDs from `x-request-id` and `x-correlation-id`, batch/message counts, method names, HTTP status, and request duration.
Tool calls log stable event names such as `mcp_tool_started`, `mcp_tool_completed`, `mcp_tool_auth_failed`, and `mcp_laws_db_session_failed`.

Debugging fields are intentionally minimized:

- Logged: tool name, argument keys, country code, limit, query length, result count, content length, database backend, user id after successful authentication, and a short SHA-256 hash for document ids.
- Not logged: MCP API keys, OAuth/JWT tokens, passwords, OTP codes, email addresses, raw search queries, raw law document ids, returned law text, law content, or full database connection strings.

For production troubleshooting, filter application logs by `mcp_` event names and correlate them with the `x-request-id` or `x-correlation-id` response headers.

Security/GDPR/EU AI Act notes: the current MCP surface exposes public-law data and per-user access credentials. JWT tokens are signed, hashed in storage, expire by default after 1 day, and can be revoked. Public tools avoid user-specific data. Protected legal-data tools remain read-only and should be logged with request correlation IDs by the API middleware for traceability. Pending MCP sign-up data is stored server-side with a short expiry and is not echoed into hidden browser fields. Set `MCP_API_JWT_SECRET` to a long random value in deployed environments.
