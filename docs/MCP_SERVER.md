# MCP server

JurisDigta runs MCP as a dedicated service, separate from the public API app.
The local default is `http://127.0.0.1:8070`, and production routing should map
`https://mcp.jurisdigta.eu` to the MCP service, not to `api.jurisdigta.eu`.

The MCP service exposes a Streamable HTTP-style MCP JSON-RPC endpoint at `POST /mcp`.
It is intended for AI assistants that can connect to remote MCP servers over HTTP.
For ChatGPT, Claude, and VS Code OAuth-capable clients, start from the OAuth metadata endpoints instead of manually copying a token.
The API `/version`, MCP `/version`, and MCP `getVersion` tool expose `mcp_server_version`.
For the current deployable package this value is aligned with the API package revision.
During JSON-RPC `initialize`, the server echoes the requested MCP protocol
version when it is one of the supported protocol versions (`2025-03-26`,
`2025-06-18`, or `2025-11-25`). If the client omits the version or sends an
unknown future value, the server falls back to the latest supported version.
`POST /MCP` remains accepted as a Claude compatibility endpoint and for older
client records, and `POST /MC` is also accepted for connector records that were
accidentally saved with the truncated Claude URL `/MC`. OAuth metadata keeps
`https://mcp.jurisdigta.eu/mcp` for lowercase clients. The uppercase
`/.well-known/oauth-protected-resource/MCP` path intentionally returns `404`
because Claude web may store custom connector URLs with uppercase `/MCP` and
will force OAuth when that path is advertised as protected.
Because Claude web can complete OAuth and then reject the issued credentials
without making an authenticated MCP call, `/MCP` also acts as a public-law
compatibility endpoint for Claude web: it allows `getVersion`, `getStatistics`,
`searchLaws`, `getLawText`, and `searchCourtDecisions` without a bearer token.
The canonical lowercase `/mcp` endpoint still requires OAuth or an MCP API key
for protected tools.

`GET /` on the MCP service is a public human-facing setup page. In production,
`https://mcp.jurisdigta.eu/` should show:

- Registration and login steps for creating an MCP account and short-lived MCP API key.
- Remote MCP setup guidance for ChatGPT custom connectors, Claude, Perplexity-compatible clients, VS Code, and other MCP clients.
- OAuth discovery URLs and the MCP endpoints `https://mcp.jurisdigta.eu/mcp`
  and Claude-compatible `https://mcp.jurisdigta.eu/MCP`.
- Privacy and compliance notes explaining that protected tools require per-user authentication and privacy-safe logging.

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
- Authorization server metadata: `GET /.well-known/oauth-authorization-server`
- Claude/path-derived authorization server metadata: `GET /.well-known/oauth-authorization-server/mcp`
- Dynamic client registration endpoint: `POST /oauth/register`
- Authorization endpoint: `GET /oauth/authorize`
- Token endpoint: `POST /oauth/token`

The OAuth flow uses authorization code with PKCE S256, plus refresh tokens for
remote clients that request `offline_access`. Remote clients can use OAuth
Client ID Metadata Documents, dynamic client registration at `/oauth/register`,
or a preconfigured public OAuth Client ID. New dynamic registrations may return
either `200 OK` or `201 Created` with the issued public client metadata.
ChatGPT and other lowercase clients should pass the protected resource value
`https://mcp.jurisdigta.eu/mcp` on the authorization, token, and refresh
requests. Claude web custom connectors should store the server URL as
`https://mcp.jurisdigta.eu/MCP`; that uppercase path is public for bounded
public-law tools and is not advertised as an OAuth protected resource.
Protected-resource metadata includes a human-readable `resource_name`, and
authorization-server metadata advertises only the lowercase protected MCP
resource, `client_id_metadata_document_supported=true`, and
`authorization_response_iss_parameter_supported=true`. The authorization
callback returns `iss=https://mcp.jurisdigta.eu` with the authorization code so
strict OAuth clients can bind the response to the issuer.
The browser authorization page validates the user password, sends an email OTP,
and only creates a short-lived authorization code after OTP verification. The
token endpoint exchanges that code for the same revocable JWT bearer token
accepted by `POST /mcp` and a separate audience-bound refresh token. Token
responses include `Cache-Control: no-store` and `Pragma: no-cache`. Clients may
request `offline_access` to receive a refresh token, but the token response
`scope` reports only the access-token scope, `mcp:laws`; the refresh token
itself carries `offline_access`.

Production settings:

- `MCP_PUBLIC_BASE_URL=https://mcp.jurisdigta.eu`
- `MCP_OAUTH_ALLOWED_REDIRECT_HOSTS=chatgpt.com,chat.openai.com,claude.ai,vscode.dev,www.perplexity.ai,localhost,127.0.0.1,::1`
  for hosted HTTPS callbacks. Loopback `http://localhost/...` and
  `http://127.0.0.1/...` and `http://[::1]/...` redirects are accepted for
  local OAuth clients such as Claude Desktop proxies.
- `MCP_API_JWT_SECRET=<long-random-secret>`
- `MCP_OTP_REUSE_WINDOW_HOURS=24`
- `MCP_OAUTH_AUTHORIZATION_RESPONSE_ISS=true` by default; keep it enabled for Claude web custom connectors so the authorization callback includes `iss`.

Do not hide OAuth discovery from Claude web custom connector probes. Claude web
uses `python-httpx` while validating custom connectors and must receive the
protected-resource metadata, authorization-server metadata, and dynamic client
registration response before it can start the browser authorization flow.

## Authentication

- MCP API keys are per user.
- Default key lifetime is 1 day.
- Keys are signed JWT bearer tokens and are only shown once at creation.
- JWT claims are minimized to `sub`, `aud`, `scope`, `exp`, `jti`, and
  `token_use` for refresh tokens.
- The latest full token is stored hashed in the database as the per-user MCP
  access marker. Clearing it revokes MCP access for the user; valid signed
  OAuth/browser tokens for that user remain usable until their own JWT expiry
  unless access is revoked.
- Protected MCP tools accept either `Authorization: Bearer <mcp_api_key>` or `x-mcp-api-key: <mcp_api_key>`.
- OAuth tokens are audience-bound to the MCP resource URL and include `scope=mcp:laws`.
- OAuth refresh tokens are audience-bound, use `scope=offline_access`, are not
  accepted as MCP bearer tokens, and can be exchanged at `/oauth/token` with
  `grant_type=refresh_token`.

Users can generate a key in either way:

- Browser login page: `GET /mcp/login`, then submit username/email and password. The MCP service emails an OTP code through the shared email queue. Submitting the OTP at `POST /mcp/login/verify` generates and stores the MCP API key.
- Browser sign-up page: `GET /mcp/sign-up`, then submit email, phone number, password, first name, last name, address, ID card number, and data-processing consent. The MCP service emails an OTP code. Submitting the OTP at `POST /mcp/sign-up/verify` creates the user; the user can then log in to generate an MCP API key.
- API endpoint: `POST /v1/users/{user_id}/mcp-api-key` with optional `{ "expires_in_days": 1 }`.

The browser login, sign-up, OTP, OAuth authorization, and key-created pages share the JurisDigta MCP auth shell in `api/aijuristiction-api/app/mcp_api.py`. Keep the form field names and POST targets stable when changing UX, because external MCP and OAuth clients rely on those routes. Do not add remote tracking images or echo submitted password, ID-card, or profile values back into the OTP pages.

After a successful MCP OTP verification, the server records a per-user MCP verification marker and skips repeat OTP prompts for subsequent MCP login or OAuth authorization attempts during `MCP_OTP_REUSE_WINDOW_HOURS` hours. The default is 24 hours; set it to `0` to require OTP every time. The user password is still required before a reused verification can authorize a client or create an MCP API key.

Keys can be revoked with:

- `DELETE /v1/users/{user_id}/mcp-api-key`

Manual JWT generation remains useful for local VS Code setups that pass an `Authorization` header directly. Standards-based remote clients should prefer OAuth discovery. Newly issued tokens use the lowercase `/mcp` audience; existing `/MCP` audience tokens remain accepted as a compatibility path until they expire or are revoked.

## Assistant Setup

Use `https://mcp.jurisdigta.eu/mcp` as the remote MCP server URL in clients that support custom HTTP MCP servers.

- ChatGPT custom connectors: create a remote MCP connector and enter the MCP server URL. Prefer OAuth discovery when the connector supports it. Users may self-register during the browser authorization flow, but ChatGPT only receives the OAuth access token and tool results, not a raw API key.
- Claude web custom connectors: use `https://mcp.jurisdigta.eu/MCP`. This uppercase path is intentionally a public-law compatibility endpoint without OAuth protected-resource discovery because Claude web may complete OAuth and then reject the issued credentials before making any authenticated MCP request. Claude Desktop, Claude Code, and local OAuth proxies can use loopback callbacks such as `http://localhost/...`, `http://127.0.0.1/...`, or `http://[::1]/...`.
- VS Code: add an HTTP MCP server in MCP settings. If OAuth is unavailable in the client, include `Authorization: Bearer <mcp_api_key>` after generating a key from `/mcp/login`.
- Perplexity and other clients: use the MCP server URL where custom remote MCP servers are supported. Hosted OAuth callbacks include `https://vscode.dev/redirect`, `https://claude.ai/api/mcp/auth_callback`, and `https://www.perplexity.ai/rest/connections/oauth_callback` when their hosts are listed in `MCP_OAUTH_ALLOWED_REDIRECT_HOSTS`. If a product only exposes its own MCP server and does not support registering external MCP servers, use another MCP-compatible host.

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

If Claude, `mcp-remote`, `curl`, or `scripts/prod_mcp_claude_smoke.py` reports
a TLS/certificate failure before OAuth discovery is reached, inspect the
certificate issuer first. Some antivirus and corporate proxy products re-sign
HTTPS traffic with a local root certificate, for example `Avast Web/Mail Shield
Root`. That client-side TLS interception can cause strict OpenSSL clients to
fail with errors such as `certificate verify failed`,
`UNABLE_TO_VERIFY_LEAF_SIGNATURE`, or Windows Schannel revocation errors even
when the public Cloudflare tunnel and MCP app are healthy.

For production connector validation, do not use `--ssl-no-revoke`, `-k`, or
disabled certificate verification as the fix. Exclude `mcp.jurisdigta.eu` from
HTTPS scanning, disable TLS interception for Claude/MCP traffic, or configure
the client runtime to trust the operating-system store when that is acceptable
for the local workstation. Then re-run:

```powershell
python scripts/prod_mcp_claude_smoke.py --retries 1 --retry-delay 1
curl.exe -Iv https://mcp.jurisdigta.eu/health
```

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

These tools do not require an MCP API key:

- `getVersion`: returns API, system/core, mobile app, web app versions, court-decision collector version, and court-decision collector status with latest imported decision metadata.
- `getStatistics`: returns processed laws count, last processed law, last processed day, laws collector details, court-decision collector version, and court-decision statistics such as total decisions, published decisions, total versions, last imported decision/source GUID, last import time, court, court type, ECLI, file number, issue date, and collector cursor status.

## Protected Tools

These tools require an MCP API key:

- `searchLaws`: searches imported laws by title, identifier, and lawyer-facing title.
- `getLawText`: returns bounded latest imported text for a law document id. For large codes, pass `section_number` or `section_start`/`section_end` to retrieve only the relevant sections; use `offset` and `max_chars` when pagination is needed.
- `searchCourtDecisions`: searches the dedicated court-decision vector store and returns pseudonymized public snippets with court/date/ECLI/file-number metadata. MCP court-decision search is bounded by a server-side PostgreSQL connect timeout and statement timeout so slow database calls return a structured `status=degraded`, `retryable=true` payload with request/correlation identifiers instead of hanging until the MCP client times out. Logs record query length, limit, duration, error kind, request ID, and correlation ID, but not the raw query, credentials, tokens, snippets, or court-decision text.
- `getCourtDecision`: returns one imported court decision. `outputMode=public` is the default and returns pseudonymized text. `outputMode=internal_raw` is blocked unless `COURT_DECISIONS_ALLOW_INTERNAL_RAW_MCP=true` is enabled for a controlled internal runtime; it must not be used for normal external model prompts or UI display.

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

For Civil Code style questions, call `searchLaws` with the exact identifier first, for example `{"query": "40/1964", "law_number": 40, "law_year": 1964}`. Then call `getLawText` with the returned `document_id` and a focused range, for example `{"document_id": "...", "section_start": 685, "section_end": 716}`. Avoid asking for the full law text unless the law is small or pagination is explicitly required.

For protected tools, send the MCP API key as a Bearer token or `x-mcp-api-key` header. Protected unauthenticated tool calls return `401` with a `WWW-Authenticate` header pointing clients at the protected-resource metadata endpoint.

## Logging And Debugging

MCP server logs use the `jurisdigta-mcp-server.http` and `aijuristiction-api.mcp` loggers with the shared `API_LOG_LEVEL` or `LOG_LEVEL` setting.
Each JSON-RPC request logs request and correlation IDs from `x-request-id` and `x-correlation-id`, batch/message counts, method names, HTTP status, and request duration.
Tool calls log stable event names such as `mcp_tool_started`, `mcp_tool_completed`, `mcp_tool_auth_failed`, and `mcp_laws_db_session_failed`.
OAuth connector diagnostics log stable event names such as
`mcp_oauth_protected_resource_metadata_served`,
`mcp_oauth_authorization_server_metadata_served`,
`mcp_oauth_authorize_started`, `mcp_oauth_authorize_succeeded`,
`mcp_oauth_authorize_failed`, `mcp_oauth_token_started`,
`mcp_oauth_token_succeeded`, and `mcp_oauth_token_failed`.
These records include the request path, redirect host/path, client id hash,
whether a `resource` parameter was supplied, the resolved resource, stored
authorization-code resource, token audience, scopes, and user-agent family so
Claude-style connector failures can be correlated without exposing credentials.
For Claude web, `resource_supplied=false` with
`token_audience=https://mcp.jurisdigta.eu/MCP` is expected when Claude omits the
OAuth `resource` parameter.
MCP endpoint entry logs use `mcp_endpoint_called` and include the actual request
path, which helps distinguish canonical `/mcp` traffic from legacy `/MCP` or
`/MC` compatibility traffic.
The HTTP middleware also emits `mcp_wire_request` and `mcp_wire_response`
records for MCP-service traffic. These records include method, path, redacted
query string, selected headers, content type, body bytes, and a body preview.
The preview is complete up to `MCP_WIRE_LOG_MAX_BYTES` bytes, which defaults to
`20000`; set a larger value temporarily when a connector sends larger payloads.
Set `MCP_WIRE_LOGGING_ENABLED=false` to disable these wire-level records.

Debugging fields are intentionally minimized:

- Logged: tool name, argument keys, country code, limit, query length, result count, content length, database backend, user id after successful authentication, OAuth endpoint path/resource/audience context, redirect host/path, user-agent family, and short SHA-256 hashes for document ids and OAuth client ids.
- Redacted from wire logs: authorization and cookie headers, MCP API keys,
  OAuth/JWT access and refresh tokens, OAuth authorization codes, PKCE
  verifiers, passwords, OTP verification codes, client secrets, pending ids,
  and identity-card fields.
- Not logged in tool events: MCP API keys, OAuth/JWT tokens, passwords, OTP codes, email addresses, raw search queries, raw law document ids, returned law text, law content, or full database connection strings.

For production troubleshooting, filter application logs by `mcp_` event names and correlate them with the `x-request-id` or `x-correlation-id` response headers.

Security/GDPR/EU AI Act notes: the current MCP surface exposes public-law data and per-user access credentials. JWT tokens are signed, audience-bound, hashed in storage, expire by default after 1 day, and can be revoked. Public tools avoid user-specific data. Protected legal-data tools remain read-only and are logged with request correlation IDs by the MCP middleware for traceability. Pending MCP sign-up data is stored server-side with a short expiry and is not echoed into hidden browser fields. OAuth and MCP tool responses do not return raw API keys to ChatGPT or Claude. Dynamic client registration only issues a public OAuth client identifier for PKCE flows; it does not issue user tokens, secrets, or data access without the existing user login and email OTP authorization. OTP reuse stores only user id, purpose, verification time, and expiry; it does not store OTP codes, passwords, OAuth tokens, email addresses, prompts, or law text. Set `MCP_API_JWT_SECRET` to a long random value in deployed environments, set `MCP_PUBLIC_BASE_URL=https://mcp.jurisdigta.eu`, keep OAuth redirect hosts restricted, protect `mcp.jurisdigta.eu` separately from the public API, and keep assistant/tool audit logs privacy-safe.
