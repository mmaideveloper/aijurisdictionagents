from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://mcp.jurisdigta.eu"
CLAUDE_REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"
EXPECTED_TOOLS = {"getVersion", "getStatistics", "searchLaws", "getLawText"}
MCP_PROTOCOL_VERSION = "2025-11-25"
TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise AssertionError(f"Expected JSON response, got {self.body[:300]!r}") from exc
        if not isinstance(payload, dict):
            raise AssertionError(f"Expected JSON object response, got {type(payload).__name__}")
        return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the public MCP endpoint behaves like a Claude-compatible "
            "remote MCP connector after production deploy."
        )
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Public MCP base URL")
    parser.add_argument("--retries", type=int, default=6, help="Attempts per check")
    parser.add_argument("--retry-delay", type=float, default=5.0, help="Delay between failed attempts")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    results: list[str] = []

    run_check("health", args, lambda: check_health(base_url), results)
    run_check("oauth protected resource metadata", args, lambda: check_protected_resource(base_url), results)
    run_check("oauth authorization server metadata", args, lambda: check_authorization_server(base_url), results)
    run_check("Claude dynamic client registration", args, lambda: check_claude_registration(base_url), results)
    run_check("client credentials remains closed", args, lambda: check_client_credentials_rejected(base_url), results)
    run_check("MCP initialize", args, lambda: check_initialize(base_url), results)
    run_check("MCP tools/list", args, lambda: check_tools_list(base_url), results)
    run_check("public MCP tool call", args, lambda: check_public_tool_call(base_url), results)
    run_check("protected tool auth challenge", args, lambda: check_auth_challenge(base_url), results)
    run_check("browser auth pages", args, lambda: check_auth_pages(base_url), results)

    print("Claude MCP smoke checks passed:")
    for item in results:
        print(f"- {item}")
    return 0


def run_check(name: str, args: argparse.Namespace, check: Any, results: list[str]) -> None:
    last_error: Exception | None = None
    for attempt in range(1, args.retries + 1):
        try:
            detail = check()
            results.append(f"{name}: {detail}")
            return
        except Exception as exc:  # pragma: no cover - diagnostic path for deploy logs
            last_error = exc
            if attempt < args.retries:
                time.sleep(args.retry_delay)
    raise SystemExit(f"{name} failed after {args.retries} attempts: {last_error}")


def check_health(base_url: str) -> str:
    payload = request_json("GET", f"{base_url}/health")
    assert_equal(payload.get("status"), "ok", "health.status")
    assert_equal(payload.get("service"), "jurisdigta-mcp-server", "health.service")
    return "public /health is ok"


def check_protected_resource(base_url: str) -> str:
    payload = request_json("GET", f"{base_url}/.well-known/oauth-protected-resource/mcp")
    assert_equal(payload.get("resource_name"), "JurisDigta MCP", "resource_name")
    assert_equal(payload.get("authorization_servers"), [base_url], "authorization_servers")
    assert_equal(payload.get("scopes_supported"), ["mcp:laws"], "scopes_supported")
    resource = str(payload.get("resource") or "")
    if resource != f"{base_url}/mcp":
        raise AssertionError(f"Unexpected protected resource URL: {resource!r}")
    return "OAuth protected resource metadata is advertised"


def check_authorization_server(base_url: str) -> str:
    for path in ("/.well-known/oauth-authorization-server", "/.well-known/oauth-authorization-server/mcp"):
        payload = request_json("GET", f"{base_url}{path}")
        assert_equal(payload.get("issuer"), base_url, f"{path}.issuer")
        assert_equal(payload.get("authorization_endpoint"), f"{base_url}/oauth/authorize", "authorization_endpoint")
        assert_equal(payload.get("token_endpoint"), f"{base_url}/oauth/token", "token_endpoint")
        assert_equal(payload.get("registration_endpoint"), f"{base_url}/oauth/register", "registration_endpoint")
        scopes = set(payload.get("scopes_supported") or [])
        if not {"mcp:laws", "offline_access"}.issubset(scopes):
            raise AssertionError(f"Authorization scopes do not include Claude-compatible scopes: {sorted(scopes)}")
        methods = set(payload.get("token_endpoint_auth_methods_supported") or [])
        if "none" not in methods:
            raise AssertionError(f"Authorization server must support public OAuth clients, got {sorted(methods)}")
    return "OAuth authorization metadata is advertised for root and /mcp"


def check_claude_registration(base_url: str) -> str:
    payload = request_json(
        "POST",
        f"{base_url}/oauth/register",
        {
            "client_name": "Claude Connector Smoke Test",
            "redirect_uris": [CLAUDE_REDIRECT_URI],
            "grant_types": ["authorization_code", "client_credentials"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": "mcp:laws offline_access",
        },
        expected_status={200, 201},
    )
    client_id = str(payload.get("client_id") or "")
    if not client_id.startswith("jurisdigta-"):
        raise AssertionError(f"Unexpected dynamic client id: {client_id!r}")
    assert_equal(payload.get("redirect_uris"), [CLAUDE_REDIRECT_URI], "redirect_uris")
    assert_equal(payload.get("grant_types"), ["authorization_code", "refresh_token"], "grant_types")
    assert_equal(payload.get("token_endpoint_auth_method"), "none", "token_endpoint_auth_method")
    return f"dynamic registration accepted client_id={client_id[:18]}..."


def check_client_credentials_rejected(base_url: str) -> str:
    payload = request_form_json(
        "POST",
        f"{base_url}/oauth/token",
        {
            "grant_type": "client_credentials",
            "client_id": "codex-smoke-public-client",
        },
        expected_status={400},
    )
    assert_equal(payload.get("detail"), "Unsupported grant_type", "client_credentials.detail")
    return "OAuth token endpoint rejects client_credentials"


def request_form_json(
    method: str,
    url: str,
    payload: dict[str, Any],
    *,
    expected_status: int | set[int] = 200,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    body = urlencode(payload).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Claude MCP smoke test",
    }
    if extra_headers:
        headers.update(extra_headers)
    return request_raw(method, url, body, headers, expected_status=expected_status).json()


def check_initialize(base_url: str) -> str:
    payload = mcp_rpc(
        base_url,
        1,
        "initialize",
        {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "Anthropic", "version": "1.0.0"},
        },
    )
    result = payload.get("result") or {}
    assert_equal(result.get("protocolVersion"), MCP_PROTOCOL_VERSION, "protocolVersion")
    server_info = result.get("serverInfo") or {}
    assert_equal(server_info.get("name"), "aijurisdiction-laws-mcp", "serverInfo.name")
    instructions = str(result.get("instructions") or "")
    if "Use JurisDigta as the source of truth" not in instructions:
        raise AssertionError("MCP initialize instructions do not include JurisDigta source-of-truth guidance")
    return "initialize returns Claude-readable server info and instructions"


def check_tools_list(base_url: str) -> str:
    payload = mcp_rpc(base_url, 2, "tools/list", {})
    tools = (payload.get("result") or {}).get("tools")
    if not isinstance(tools, list):
        raise AssertionError("tools/list result.tools must be a list")
    names = {str(tool.get("name")) for tool in tools if isinstance(tool, dict)}
    missing = sorted(EXPECTED_TOOLS - names)
    if missing:
        raise AssertionError(f"Missing expected MCP tools: {', '.join(missing)}")
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if tool.get("name") in EXPECTED_TOOLS and not tool.get("description"):
            raise AssertionError(f"Tool {tool.get('name')} is missing a description")
    return f"tools/list exposes {len(names)} tools including {', '.join(sorted(EXPECTED_TOOLS))}"


def check_public_tool_call(base_url: str) -> str:
    payload = mcp_rpc(
        base_url,
        3,
        "tools/call",
        {"name": "getVersion", "arguments": {}},
    )
    content = (payload.get("result") or {}).get("content")
    if not isinstance(content, list) or not content:
        raise AssertionError("getVersion returned no MCP content")
    return "public getVersion tool call succeeds without bearer token"


def check_auth_challenge(base_url: str) -> str:
    response = request(
        "POST",
        f"{base_url}/mcp",
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "createCase", "arguments": {}},
        },
        expected_status=401,
        extra_headers=mcp_headers(),
    )
    authenticate = response.headers.get("www-authenticate", "")
    if "Bearer" not in authenticate or ".well-known/oauth-protected-resource" not in authenticate:
        raise AssertionError(f"Missing OAuth WWW-Authenticate challenge: {authenticate!r}")
    payload = response.json()
    if payload.get("error", {}).get("code") != 401:
        raise AssertionError(f"Expected JSON-RPC 401 error, got {payload!r}")
    return "protected tools return OAuth challenge for unauthenticated Claude client"


def check_auth_pages(base_url: str) -> str:
    for path, marker in (("/mcp/login", "form"), ("/mcp/sign-up", "form")):
        response = request("GET", f"{base_url}{path}")
        text = response.body.decode("utf-8", errors="replace").lower()
        if marker not in text:
            raise AssertionError(f"{path} does not look like an HTML auth page")
    return "login and sign-up pages are reachable"


def mcp_rpc(base_url: str, request_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
    payload = request_json(
        "POST",
        f"{base_url}/mcp",
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
        extra_headers=mcp_headers(),
    )
    if "error" in payload:
        raise AssertionError(f"MCP method {method} returned error: {payload['error']!r}")
    return payload


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    expected_status: int | set[int] = 200,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    return request(method, url, payload, expected_status=expected_status, extra_headers=extra_headers).json()


def request(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    expected_status: int | set[int] = 200,
    extra_headers: dict[str, str] | None = None,
) -> HttpResponse:
    body = None
    headers = {
        "Accept": "application/json, text/html;q=0.9",
        "User-Agent": "Claude MCP smoke test",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if extra_headers:
        headers.update(extra_headers)
    return request_raw(method, url, body, headers, expected_status=expected_status)


def request_raw(
    method: str,
    url: str,
    body: bytes | None,
    headers: dict[str, str],
    *,
    expected_status: int | set[int] = 200,
) -> HttpResponse:
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            status = int(response.status)
            data = response.read()
            response_headers = {key.lower(): value for key, value in response.headers.items()}
    except HTTPError as exc:
        status = int(exc.code)
        data = exc.read()
        response_headers = {key.lower(): value for key, value in exc.headers.items()}
    except URLError as exc:
        detail = f"HTTP request failed for {method} {url}: {exc}"
        tls_detail = tls_certificate_diagnostic(url, exc)
        if tls_detail:
            detail = f"{detail}\n{tls_detail}"
        raise AssertionError(detail) from exc

    expected_statuses = expected_status if isinstance(expected_status, set) else {expected_status}
    if status not in expected_statuses:
        preview = data.decode("utf-8", errors="replace")[:500]
        expected_label = " or ".join(str(item) for item in sorted(expected_statuses))
        raise AssertionError(f"Expected {expected_label} for {method} {url}, got {status}: {preview}")
    return HttpResponse(status=status, headers=response_headers, body=data)


def mcp_headers() -> dict[str, str]:
    return {
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        "User-Agent": "python-httpx/0.28.1 Claude MCP smoke test",
    }


def tls_certificate_diagnostic(url: str, error: URLError) -> str:
    reason = getattr(error, "reason", error)
    if not isinstance(reason, ssl.SSLError):
        return ""

    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return ""

    port = parsed.port or 443
    try:
        cert = fetch_peer_certificate(parsed.hostname, port)
    except OSError as exc:  # pragma: no cover - diagnostic path
        return f"TLS certificate diagnostic unavailable for {parsed.hostname}:{port}: {exc}"

    subject = name_to_text(cert.get("subject", ()))
    issuer = name_to_text(cert.get("issuer", ()))
    san = cert.get("subjectAltName", ())
    san_text = (
        ", ".join(f"{name}:{value}" for name, value in san)
        if isinstance(san, tuple)
        else str(san)
    )
    mitigation = (
        "Strict TLS verification failed before the MCP/OAuth flow reached the server. "
        "If the issuer is an antivirus, proxy, or enterprise TLS inspection root "
        "(for example Avast Web/Mail Shield), fix that local/client trust path or "
        "exclude mcp.jurisdigta.eu from HTTPS scanning. Do not use --ssl-no-revoke, "
        "-k, or disabled verification as a production connector workaround."
    )
    return (
        "TLS certificate diagnostic:\n"
        f"- peer subject: {subject or 'unknown'}\n"
        f"- peer issuer: {issuer or 'unknown'}\n"
        f"- peer SAN: {san_text or 'unknown'}\n"
        f"- guidance: {mitigation}"
    )


def fetch_peer_certificate(hostname: str, port: int) -> dict[str, Any]:
    context = ssl._create_unverified_context()
    with socket.create_connection((hostname, port), timeout=TIMEOUT_SECONDS) as raw_socket:
        with context.wrap_socket(raw_socket, server_hostname=hostname) as tls_socket:
            der_cert = tls_socket.getpeercert(binary_form=True)
    if not der_cert:
        return {}

    pem_cert = ssl.DER_cert_to_PEM_cert(der_cert)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".pem", delete=False, encoding="ascii"
    ) as cert_file:
        cert_path = Path(cert_file.name)
        cert_file.write(pem_cert)
    try:
        return ssl._ssl._test_decode_cert(str(cert_path))  # type: ignore[attr-defined]
    finally:
        cert_path.unlink(missing_ok=True)


def name_to_text(name: object) -> str:
    if not isinstance(name, tuple):
        return ""
    parts: list[str] = []
    for group in name:
        if not isinstance(group, tuple):
            continue
        for attribute in group:
            if (
                isinstance(attribute, tuple)
                and len(attribute) == 2
                and isinstance(attribute[0], str)
            ):
                parts.append(f"{attribute[0]}={attribute[1]}")
    return ", ".join(parts)


def assert_equal(actual: Any, expected: Any, name: str) -> None:
    if actual != expected:
        raise AssertionError(f"Unexpected {name}: expected {expected!r}, got {actual!r}")


if __name__ == "__main__":
    sys.exit(main())
