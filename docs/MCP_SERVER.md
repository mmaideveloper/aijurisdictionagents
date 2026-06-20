# MCP server

JurisDigta runs MCP as a dedicated service, separate from the public API app.
The local default is `http://127.0.0.1:8070`, and production routing should map
`https://mcp.jurisdigta.eu` to the MCP service, not to `api.jurisdigta.eu`.

The MCP service exposes a Streamable HTTP-style MCP JSON-RPC endpoint at `POST /mcp`.
It is intended for AI assistants that can connect to remote MCP servers over HTTP.
For ChatGPT, Claude, and VS Code OAuth-capable clients, start from the OAuth metadata endpoints instead of manually copying a token.
The API `/version`, MCP `/version`, and MCP `getVersion` tool expose `mcp_server_version`.
For the current deployable package this value is aligned with the API package revision.
`POST /MC` is also accepted as a compatibility alias for connector records that
were accidentally saved with the truncated Claude URL `/MC`; OAuth metadata and
token audiences remain canonical as `https://mcp.jurisdigta.eu/mcp`. `POST /MCP`
is accepted as a legacy compatibility alias for older connector records and
browser account pages.

`GET /` on the MCP service is a public human-facing setup page. In production,
`https://mcp.jurisdigta.eu/` should show:

- Registration and login steps for creating an MCP account and short-lived MCP API key.
- Remote MCP setup guidance for ChatGPT custom connectors, Claude, Perplexity-compatible clients, VS Code, and other MCP clients.
- OAuth discovery URLs and the canonical MCP endpoint `https://mcp.jurisdigta.eu/mcp`.
- Privacy and compliance notes explaining that public-law tools avoid user-specific data and use privacy-safe logging.

Start locally with Docker Compose:

```powershell
cd api/aijuristiction-api
docker compose up --build mcp
```

Or directly from the API package:

```powershell
cd api/aijuristiction-api
uvicorn app.mcp_main:app --reload --port 8070
```

Then open the setup page:

```powershell
curl http://127.0.0.1:8070/
```

## OAuth Discovery

- Protected resource metadata: `GET /.well-known/oauth-protected-resource/mcp`
- Legacy protected resource metadata alias: `GET /.well-known/oauth-protected-resource/MCP`
- Authorization server metadata: `GET /.well-known/oauth-authorization-server`
- Claude/path-derived authorization server metadata: `GET /.well-known/oauth-authorization-server/mcp`
- Legacy Claude/path-derived authorization server metadata alias: `GET /.well-known/oauth-authorization-server/MCP`
- Dynamic client registration endpoint: `POST /oauth/register`
- Authorization endpoint: `GET /oauth/authorize`
- Token endpoint: `POST /oauth/token`

The OAuth flow uses authorization code with PKCE S256, plus refresh tokens for
remote clients that request `offline_access`. Remote clients can either use
dynamic client registration at `/oauth/register` or provide a preconfigured
public OAuth Client ID. ChatGPT and Claude should pass the protected resource
value `https://mcp.jurisdigta.eu/mcp` on the authorization, token, and refresh
requests. Protected-resource metadata includes a human-readable
`resource_name`, and authorization-server metadata advertises the protected MCP
resource. By default, `authorization_response_iss_parameter_supported=false`
and the authorization callback does not include the optional `iss` query
parameter; Claude web accepts the code and token exchange more reliably without
that optional callback issuer. Set `MCP_OAUTH_AUTHORIZATION_RESPONSE_ISS=true`
only for strict OAuth clients that require `iss=https://mcp.jurisdigta.eu` in
the authorization callback.
The browser authorization page validates the user password, sends an email OTP,
and only creates a short-lived authorization code after OTP verification. The
token endpoint exchanges that code for a short audience-bound JWT bearer token
accepted by `POST /mcp` and a separate audience-bound JWT refresh token. Token responses
include `Cache-Control: no-store` and `Pragma: no-cache`.

Claude web custom connectors receive the read-only MCP surface without requiring
an authenticated tool call, but Claude still probes OAuth registration during
connector setup. By default, OAuth metadata and dynamic registration remain
available. Set `MCP_CLAUDE_WEB_PUBLIC_DISCOVERY=true` only for incident testing
when Claude should be forced to validate the public tools directly through
`POST /mcp` without advertised OAuth metadata or dynamic client registration.

Production settings:

- `MCP_PUBLIC_BASE_URL=https://mcp.jurisdigta.eu`
- `MCP_OAUTH_ALLOWED_REDIRECT_HOSTS=chatgpt.com,chat.openai.com,claude.ai`
- `MCP_API_JWT_SECRET=<long-random-secret>`
- `MCP_OAUTH_AUTHORIZATION_RESPONSE_ISS=false` unless a strict OAuth client requires it
- `MCP_OTP_REUSE_WINDOW_HOURS=24`

## Authentication

- MCP API keys are per user.
- Default key lifetime is 1 day.
- Browser/manual keys and OAuth access tokens are signed JWT bearer tokens.
  Browser/manual keys are only shown once at creation.
- JWT claims for manual access keys, OAuth access tokens, and OAuth refresh tokens are minimized to
  `sub`, `aud`, `iss`, `scope`, `iat`, `exp`, `jti`, and `token_use`.
- The latest full token is stored hashed in the database as the per-user MCP
  access marker. Clearing it revokes MCP access for the user; valid signed
  OAuth/browser tokens for that user remain usable until their own JWT expiry
  unless access is revoked.
- MCP tools accept either unauthenticated read-only access or optional `Authorization: Bearer <mcp_api_key>` / `x-mcp-api-key: <mcp_api_key>` headers from clients that already use OAuth or manual API keys.
- `initialize` advertises MCP protocol version `2025-11-25`, matching the
  current Claude custom connector probe.
- OAuth token responses include `scope=mcp:laws offline_access` when a refresh
  token is returned. OAuth access tokens are JWTs and server-side revocable.
- OAuth refresh tokens are audience-bound, use `scope=offline_access`, are not
  accepted as MCP bearer tokens, and can be exchanged at `/oauth/token` with
  `grant_type=refresh_token`.

Users can generate a key in either way:

- Browser login page: `GET /MCP/login`, then submit username/email and password. The MCP service emails an OTP code through the shared email queue. Submitting the OTP at `POST /MCP/login/verify` generates and stores the MCP API key.
- Browser sign-up page: `GET /MCP/sign-up`, then submit email, phone number, password, first name, last name, address, ID card number, and data-processing consent. The MCP service emails an OTP code. Submitting the OTP at `POST /MCP/sign-up/verify` creates the user; the user can then log in to generate an MCP API key.
- API endpoint: `POST /v1/users/{user_id}/mcp-api-key` with optional `{ "expires_in_days": 1 }`.

The browser login, sign-up, OTP, OAuth authorization, and key-created pages share the JurisDigta MCP auth shell in `api/aijuristiction-api/app/mcp_api.py`. Keep the form field names and POST targets stable when changing UX, because external MCP and OAuth clients rely on those routes. Do not add remote tracking images or echo submitted password, ID-card, or profile values back into the OTP pages.

After a successful MCP OTP verification, the server records a per-user MCP verification marker and skips repeat OTP prompts for subsequent MCP login or OAuth authorization attempts during `MCP_OTP_REUSE_WINDOW_HOURS` hours. The default is 24 hours; set it to `0` to require OTP every time. The user password is still required before a reused verification can authorize a client or create an MCP API key.

Keys can be revoked with:

- `DELETE /v1/users/{user_id}/mcp-api-key`

Manual JWT generation remains useful for local VS Code setups that pass an `Authorization` header directly. Standards-based remote clients should prefer OAuth discovery. Existing uppercase `/MCP` audience tokens are accepted during the compatibility window, but new tokens use lowercase `/mcp`.

## Assistant Setup

Use `https://mcp.jurisdigta.eu/mcp` as the remote MCP server URL in clients that support custom HTTP MCP servers.

- ChatGPT custom connectors: create a remote MCP connector and enter the MCP server URL. Prefer OAuth discovery when the connector supports it. Users may self-register during the browser authorization flow, but ChatGPT only receives the OAuth access token and tool results, not a raw API key.
- Claude: add a custom connector or remote MCP server and enter the MCP server URL. OAuth-capable Claude clients can discover authorization metadata from `https://mcp.jurisdigta.eu` and register dynamically. If Claude reports that automatic client registration is not supported, open Advanced settings, set OAuth Client ID to a stable public value such as `claude`, leave OAuth Client Secret empty, and retry after confirming `claude.ai` is allowed in `MCP_OAUTH_ALLOWED_REDIRECT_HOSTS`.
- VS Code: add an HTTP MCP server in MCP settings. If OAuth is unavailable in the client, include `Authorization: Bearer <mcp_api_key>` after generating a key from `/MCP/login`.
- Perplexity and other clients: use the MCP server URL where custom remote MCP servers are supported. If a product only exposes its own MCP server and does not support registering external MCP servers, use another MCP-compatible host.

### Claude Desktop via `mcp-remote`

Claude Desktop can use a remote HTTPS MCP server through a local stdio proxy.
On Windows Store installs, edit:

```text
%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json
```

On classic desktop installs, check:

```text
%APPDATA%\Claude\claude_desktop_config.json
```

Add or merge this `mcpServers` entry while keeping existing preferences:

```json
{
  "mcpServers": {
    "jurisdigta": {
      "type": "stdio",
      "command": "C:\\Program Files\\nodejs\\npx.cmd",
      "args": [
        "-y",
        "mcp-remote",
        "https://mcp.jurisdigta.eu/mcp"
      ],
      "env": {
        "NODE_OPTIONS": "--use-system-ca"
      }
    }
  }
}
```

Restart Claude Desktop after saving the file. The first connection starts
`mcp-remote`, opens the JurisDigta OAuth flow, and then stores the MCP session
locally for Claude Desktop.

If the Claude log shows `UNABLE_TO_VERIFY_LEAF_SIGNATURE` while running `npx`,
keep `NODE_OPTIONS=--use-system-ca`; it tells Node.js to trust the Windows
system certificate store. If Claude logs `Claude Code requires a Pro or Max
subscription`, the MCP server may be configured correctly but the active Claude
account lacks the required Claude Desktop/Code entitlement.

Discovery endpoints:

- `https://mcp.jurisdigta.eu/.well-known/oauth-protected-resource/mcp`
- `https://mcp.jurisdigta.eu/.well-known/oauth-authorization-server`
- `https://mcp.jurisdigta.eu/.well-known/oauth-authorization-server/mcp`
- `https://mcp.jurisdigta.eu/oauth/register`

Client documentation:

- OpenAI remote MCP documentation: <https://developers.openai.com/api/docs/mcp>
- Claude MCP connector documentation: <https://platform.claude.com/docs/en/agents-and-tools/mcp-connector>
- VS Code MCP server documentation: <https://code.visualstudio.com/docs/agent-customization/mcp-servers>

## Public Tools

These read-only public-law tools do not require an MCP API key:

- `getVersion`: returns API, system/core, mobile app, and web app versions.
- `getStatistics`: returns processed laws count, last processed law, last processed day, and collector details.
- `searchLaws`: searches imported laws by title, identifier, and lawyer-facing title.
- `getLawText`: returns latest imported text for a law document id.

## Protected Tools

There are currently no user-specific or write-capable MCP tools. Keep new user-specific,
write-capable, or private-data tools out of `_PUBLIC_TOOLS` and require an MCP API key
before adding them to the published tool list.

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

OAuth and manually generated MCP API keys remain supported for clients that send them,
but the current published MCP tools are public read-only law lookup tools. Protected
future tool calls should return `401` with a `WWW-Authenticate` header pointing clients
at the protected-resource metadata endpoint.

## Logging And Debugging

MCP server logs use the `jurisdigta-mcp-server.http` and `aijuristiction-api.mcp` loggers with the shared `API_LOG_LEVEL` or `LOG_LEVEL` setting.
Each JSON-RPC request logs request and correlation IDs from `x-request-id` and `x-correlation-id`, batch/message counts, method names, HTTP status, and request duration.
Tool calls log stable event names such as `mcp_tool_started`, `mcp_tool_completed`, `mcp_tool_auth_failed`, and `mcp_laws_db_session_failed`.
The HTTP middleware also emits `mcp_wire_request` and `mcp_wire_response`
records for MCP-service traffic. These records include method, path, redacted
query string, selected headers, content type, body bytes, and a body preview.
The preview is complete up to `MCP_WIRE_LOG_MAX_BYTES` bytes, which defaults to
`20000`; set a larger value temporarily when a connector sends larger payloads.
Set `MCP_WIRE_LOGGING_ENABLED=false` to disable these wire-level records.

Debugging fields are intentionally minimized:

- Logged: tool name, argument keys, country code, limit, query length, result count, content length, database backend, user id after successful authentication, and a short SHA-256 hash for document ids.
- Redacted from wire logs: authorization and cookie headers, MCP API keys,
  OAuth/JWT access and refresh tokens, OAuth authorization codes, PKCE
  verifiers, passwords, OTP verification codes, client secrets, pending ids,
  email addresses, and identity-card fields. OAuth `token_type` remains visible
  so connector debugging can confirm Bearer-token semantics without exposing
  credentials.
- Not logged in tool events: MCP API keys, OAuth/JWT tokens, passwords, OTP codes, email addresses, raw search queries, raw law document ids, returned law text, law content, or full database connection strings.

For production troubleshooting, filter application logs by `mcp_` event names and correlate them with the `x-request-id` or `x-correlation-id` response headers.

Security/GDPR/EU AI Act notes: the current MCP surface exposes public-law data and optional per-user access credentials. Manual and OAuth JWT tokens are signed and audience-bound. They are hashed in storage, expire by default after 1 day, and can be revoked. Public tools avoid user-specific data and remain read-only, with request correlation IDs logged by the MCP middleware for traceability. Pending MCP sign-up data is stored server-side with a short expiry and is not echoed into hidden browser fields. OAuth and MCP tool responses do not return raw API keys to ChatGPT or Claude. Dynamic client registration only issues a public OAuth client identifier for PKCE flows; it does not issue user tokens or secrets without the existing user login and email OTP authorization. OTP reuse stores only user id, purpose, verification time, and expiry; it does not store OTP codes, passwords, OAuth tokens, email addresses, prompts, or law text. Set `MCP_API_JWT_SECRET` to a long random value in deployed environments, set `MCP_PUBLIC_BASE_URL=https://mcp.jurisdigta.eu`, keep OAuth redirect hosts restricted, protect `mcp.jurisdigta.eu` separately from the public API, and keep assistant/tool audit logs privacy-safe.
