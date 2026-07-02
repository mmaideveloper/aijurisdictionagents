# setup.sk DNS With Cloudflare Tunnel For JurisDigta Subdomains

This runbook explains how to publish JurisDigta service hostnames from a local Ubuntu 26.04 server while keeping the DNS zone in setup.sk and using Cloudflare Tunnel for ingress.

Target hostnames:

- `web.jurisdigta.eu`
- `agent.jurisdigta.eu`
- `api.jurisdigta.eu`
- `mcp.jurisdigta.eu`
- `admin.jurisdigta.eu`

DNS provider: `www.setup.sk` remains authoritative for `jurisdigta.eu`.

## Recommended Approach

Use **Cloudflare Tunnel with partial DNS/CNAME setup**.

This keeps `jurisdigta.eu` records managed in setup.sk while Cloudflare Tunnel carries traffic from Cloudflare to the local Ubuntu server over outbound `cloudflared` connections. This avoids static IP requirements, router port forwarding, and most CGNAT limitations.

The pattern is:

1. Create a Cloudflare Tunnel in Cloudflare Zero Trust.
2. Install and run `cloudflared` on the Ubuntu server.
3. Configure Cloudflare public hostnames for `web`, `agent`, `api`, `mcp`, and `admin`, each mapped to a local service.
4. In setup.sk, create one `CNAME` per subdomain pointing to the Cloudflare-provided partial-setup target.

For partial DNS setup, Cloudflare documents the CNAME target as `<hostname>.cdn.cloudflare.net`, for example `api.jurisdigta.eu.cdn.cloudflare.net`. Cloudflare named tunnel DNS records may also be represented as `<UUID>.cfargotunnel.com`; use the exact target shown by Cloudflare for the hostname/tunnel flow you configure.

## Why This Fits A Local Server Without Static IP

- No static public IP is required.
- No router port forwarding is required for public TCP `80` or `443`.
- It can work when the ISP uses CGNAT.
- setup.sk can remain the DNS provider.
- The Ubuntu server can keep direct inbound HTTP/HTTPS closed at the router.
- `admin.jurisdigta.eu` and `mcp.jurisdigta.eu` can be protected with Cloudflare Access before reaching local services.

## Architecture

```text
Internet user
  |
  | HTTPS https://api.jurisdigta.eu
  v
setup.sk DNS zone
  |
  | CNAME api.jurisdigta.eu -> api.jurisdigta.eu.cdn.cloudflare.net
  v
Cloudflare edge + Cloudflare Tunnel
  |
  | outbound tunnel maintained by cloudflared
  v
Ubuntu 26.04 server cloudflared
  |
  | local HTTP routing
  v
Ubuntu 26.04 server nginx / local services
  |
  +--> web.jurisdigta.eu   -> local web frontend port or static files
  +--> agent.jurisdigta.eu -> local web frontend port, protected by JurisDigta account login
  +--> api.jurisdigta.eu   -> http://127.0.0.1:8080
  +--> mcp.jurisdigta.eu   -> local MCP service port
  +--> admin.jurisdigta.eu -> local admin service port protected by Cloudflare Access/VPN/IP allow-list
```

## Prerequisites

- Access to the setup.sk DNS zone for `jurisdigta.eu`.
- Access to Cloudflare Zero Trust and permission to create a tunnel/public hostnames.
- Ubuntu server reachable locally.
- Local services already listening on loopback or LAN addresses, for example API on `127.0.0.1:8080`.
- A documented decision for how `admin.jurisdigta.eu` and `mcp.jurisdigta.eu` will be authenticated before public exposure.

## Step 1: Create The Tunnel In Cloudflare

1. Open Cloudflare Zero Trust.
2. Create a named tunnel, for example `jurisdigta-local`.
3. Choose the connector installation instructions for Linux / Debian package on Ubuntu.
4. Copy the generated tunnel token or connector command.
5. Treat the tunnel token as a secret; store it only on the server or in a local password manager.

## Step 2: Install And Run `cloudflared` On Ubuntu

Follow the package command shown by Cloudflare for Ubuntu/Debian. The final service should be managed by systemd so the tunnel starts after reboot.

Validation commands on the server:

```bash
systemctl status cloudflared --no-pager
journalctl -u cloudflared -n 100 --no-pager
```

The tunnel should show as healthy in Cloudflare Zero Trust before DNS cutover.

## Step 3: Configure Cloudflare Public Hostnames

Create these public hostnames in the Cloudflare Tunnel configuration:

| Public hostname | Local service | Required protection |
| --- | --- | --- |
| `web.jurisdigta.eu` | `http://127.0.0.1:<web-port>` or local nginx static site | Public web frontend controls |
| `agent.jurisdigta.eu` | `http://127.0.0.1:<web-port>` after web deployment | Authenticated assistant route `/app/assistant`; current production uses JurisDigta account login against the API users table |
| `api.jurisdigta.eu` | `http://127.0.0.1:8080` | API authentication, rate limits, safe CORS |
| `mcp.jurisdigta.eu` | `http://127.0.0.1:8070` | Authentication, rate limits, audit logging |
| `admin.jurisdigta.eu` | `http://127.0.0.1:<admin-port>` | Cloudflare Access, VPN/IP allow-list, strong MFA |

Do not expose unauthenticated MCP or admin routes. Put `admin.jurisdigta.eu` behind Cloudflare Access before sharing the hostname outside the operator team.

## Step 4: Create setup.sk CNAME Records

In setup.sk DNS management for `jurisdigta.eu`, create one `CNAME` per public hostname. Use the exact CNAME target Cloudflare provides for each hostname.

For Cloudflare partial DNS setup, the target commonly follows this form:

```text
<full-hostname>.cdn.cloudflare.net
```

Example setup.sk records:

| setup.sk host | Type | Target | TTL |
| --- | --- | --- | --- |
| `web` | `CNAME` | `web.jurisdigta.eu.cdn.cloudflare.net.` | `300` |
| `agent` | `CNAME` | `agent.jurisdigta.eu.cdn.cloudflare.net.` | `300` |
| `api` | `CNAME` | `api.jurisdigta.eu.cdn.cloudflare.net.` | `300` |
| `mcp` | `CNAME` | `mcp.jurisdigta.eu.cdn.cloudflare.net.` | `300` |
| `admin` | `CNAME` | `admin.jurisdigta.eu.cdn.cloudflare.net.` | `300` |

If the Cloudflare dashboard gives a different target such as `<UUID>.cfargotunnel.com`, use the dashboard-provided value. Do not create `A` records pointing to the home IP for the tunnel path.

## Step 5: Keep The Router Locked Down

For the Cloudflare Tunnel path, do **not** forward public TCP `80` or `443` to the Ubuntu server. The connector makes outbound connections to Cloudflare. Keep direct inbound services closed unless a separate security review approves them.

On Ubuntu, local firewall rules can allow services only from loopback or the LAN as needed. Public ingress should arrive through `cloudflared`, not through direct router NAT.

## Step 6: Validate Externally

After DNS propagation and a healthy tunnel, validate from outside the LAN:

```bash
dig +short web.jurisdigta.eu
dig +short agent.jurisdigta.eu
dig +short api.jurisdigta.eu
dig +short mcp.jurisdigta.eu
dig +short admin.jurisdigta.eu
curl -I https://web.jurisdigta.eu
curl -fsS https://agent.jurisdigta.eu/health
curl -I https://agent.jurisdigta.eu/app/assistant
curl -fsS https://api.jurisdigta.eu/health
curl -I https://mcp.jurisdigta.eu
curl -I https://admin.jurisdigta.eu
```

If the tunnel stops, DNS records can remain in setup.sk, but visitors will receive a Cloudflare tunnel error until `cloudflared` is healthy again.

## Step-By-Step Cloudflare Tunnel Setup

This section is the operator checklist for the preferred setup.sk + Cloudflare Tunnel path. Replace placeholder ports and tokens before running commands.

### 1. Confirm local services first

On the Ubuntu server, confirm the services work locally before exposing them through Cloudflare:

```bash
curl -fsS http://127.0.0.1:8080/health
# Replace these ports with the actual local web, MCP, and admin ports.
curl -I http://127.0.0.1:<web-port>
curl -I http://127.0.0.1:8070/.well-known/oauth-protected-resource/mcp
curl -I http://127.0.0.1:<admin-port>
```

Do not continue to public DNS until the local health checks succeed.

### 2. Create a Cloudflare Tunnel in the dashboard

1. Sign in to Cloudflare.
2. Open **Zero Trust**.
3. Go to **Networks** > **Tunnels**.
4. Select **Create a tunnel**.
5. Choose **Cloudflared**.
6. Name the tunnel `jurisdigta-local`.
7. Select the Debian/Ubuntu connector instructions.
8. Copy the generated install/run command containing the tunnel token.

The generated token is a secret. Do not paste it into Git, tickets, screenshots, or shared logs.

### 3. Install `cloudflared` on Ubuntu

Cloudflare's dashboard may give a one-line install command. If you need to install the package manually on Ubuntu/Debian, use Cloudflare's apt repository:

```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update
sudo apt-get install -y cloudflared
cloudflared --version
```

### 4. Install the tunnel as a systemd service

Use the exact token command shown in Cloudflare. It normally has this shape:

```bash
sudo cloudflared service install <CLOUDFLARE_TUNNEL_TOKEN>
sudo systemctl enable --now cloudflared
systemctl status cloudflared --no-pager
journalctl -u cloudflared -n 100 --no-pager
```

If `systemctl status cloudflared` is not active/running, fix the tunnel before creating public DNS records.

### 5. Add public hostnames in Cloudflare

In the tunnel details page, add these public hostname routes:

| Cloudflare hostname | Service type and URL | Notes |
| --- | --- | --- |
| `web.jurisdigta.eu` | `HTTP` -> `127.0.0.1:<web-port>` | Use the actual local web/frontend port or local nginx port. |
| `agent.jurisdigta.eu` | `HTTP` -> `127.0.0.1:<web-port>` | Same frontend container as `web`; require JurisDigta account login for the assistant workspace. |
| `api.jurisdigta.eu` | `HTTP` -> `127.0.0.1:8080` | API service. Validate `/health`. |
| `mcp.jurisdigta.eu` | `HTTP` -> `127.0.0.1:8070` | Require auth, rate limits, and audit logging. |
| `admin.jurisdigta.eu` | `HTTP` -> `127.0.0.1:<admin-port>` | Put behind Cloudflare Access/MFA before sharing. |

If Cloudflare asks for HTTPS origin URLs instead of HTTP, only use HTTPS origin mode after local origin certificates are configured and validated. For the first local setup, HTTP to `127.0.0.1` through the tunnel is simpler.

### 6. Create setup.sk CNAME records

For each Cloudflare public hostname, copy the Cloudflare-provided DNS target into setup.sk. For partial DNS setup this target commonly looks like `<full-hostname>.cdn.cloudflare.net`; named tunnels may show `<UUID>.cfargotunnel.com`. Use the exact value shown in Cloudflare.

Example setup.sk records:

| setup.sk host | Type | Target |
| --- | --- | --- |
| `web` | `CNAME` | `web.jurisdigta.eu.cdn.cloudflare.net.` |
| `agent` | `CNAME` | `agent.jurisdigta.eu.cdn.cloudflare.net.` |
| `api` | `CNAME` | `api.jurisdigta.eu.cdn.cloudflare.net.` |
| `mcp` | `CNAME` | `mcp.jurisdigta.eu.cdn.cloudflare.net.` |
| `admin` | `CNAME` | `admin.jurisdigta.eu.cdn.cloudflare.net.` |

Do not add `A` records pointing these names to the home public IP when using Cloudflare Tunnel.

### 7. Lock down router and firewall exposure

For Cloudflare Tunnel, public inbound router forwards are not needed:

- Do not forward public TCP `80` to the Ubuntu server.
- Do not forward public TCP `443` to the Ubuntu server.
- Do not expose PostgreSQL, Redis, Docker, MCP, admin, or internal API ports directly.
- Allow local services only on loopback/LAN unless there is a documented exception.

The tunnel connector reaches Cloudflare using outbound connections, so CGNAT and changing public IPs should not break hostname routing.

### 8. Validate DNS and HTTPS from outside the LAN

Run these checks from a mobile network or another external connection after DNS propagation:

```bash
dig +short web.jurisdigta.eu
dig +short agent.jurisdigta.eu
dig +short api.jurisdigta.eu
dig +short mcp.jurisdigta.eu
dig +short admin.jurisdigta.eu
curl -I https://web.jurisdigta.eu
curl -fsS https://agent.jurisdigta.eu/health
curl -I https://agent.jurisdigta.eu/app/assistant
curl -fsS https://api.jurisdigta.eu/health
curl -I https://mcp.jurisdigta.eu
curl -I https://admin.jurisdigta.eu
```

If a hostname returns a Cloudflare tunnel error, check:

1. Cloudflare Zero Trust tunnel health.
2. `systemctl status cloudflared --no-pager`.
3. `journalctl -u cloudflared -n 100 --no-pager`.
4. The public hostname's local service URL and port.
5. The setup.sk `CNAME` value and DNS propagation.

If HTTPS fails before an HTTP status is returned, inspect the certificate issuer
shown to the client. Antivirus or enterprise proxy TLS inspection can re-sign
the Cloudflare certificate with a local issuer such as `Avast Web/Mail Shield
Root`; strict clients may then fail with OpenSSL, Node.js, or Schannel
certificate errors even though the tunnel route is healthy. Exclude JurisDigta
hostnames from HTTPS scanning or configure the client runtime to use the
operating-system trust store where appropriate. Do not treat `--ssl-no-revoke`,
`-k`, or disabled certificate verification as a production MCP/Claude fix.

### 9. Add Cloudflare Access before exposing admin

Before using `admin.jurisdigta.eu` for anything real:

1. Create a Cloudflare Access application for `admin.jurisdigta.eu`.
2. Require MFA for allowed operators.
3. Restrict access to named users/groups.
4. Keep local admin authentication enabled as a second layer.
5. Confirm denied users cannot reach the admin origin.

Apply the same approach to `mcp.jurisdigta.eu` unless every MCP route is already strongly authenticated and rate-limited.

## Security And Compliance Notes

- Treat the Cloudflare tunnel token as a secret and never commit it.
- Expose public traffic only through Cloudflare Tunnel; keep direct router ingress closed.
- Protect `admin.jurisdigta.eu` with Cloudflare Access, VPN, IP allow-list, strong MFA, and human-approved access before production use.
- Do not publish secret-bearing MCP endpoints without authentication, rate limits, and audit logging.
- Apply GDPR data minimization to Cloudflare, application, and origin logs; avoid logging legal case contents, uploaded document text, access tokens, API keys, or user credentials.
- Keep privacy-safe audit logs for legal-risk workflows and preserve human-oversight paths before AI-assisted legal outputs are generated.
- Review Cloudflare data processing, log retention, access controls, and incident-response responsibilities before relying on the tunnel for production legal workflows.

## Rollback

1. Remove or disable setup.sk `CNAME` records for `web`, `api`, `mcp`, and `admin`.
2. Disable Cloudflare Tunnel public hostnames.
3. Stop and disable the tunnel service on Ubuntu:

```bash
sudo systemctl disable --now cloudflared
```

4. Revoke the Cloudflare tunnel token if it was exposed or is no longer needed.
5. Keep direct router port forwards disabled unless a separate rollback target requires them and has been reviewed.

## Direct DDNS Fallback

Use direct DDNS only if Cloudflare Tunnel is not desired. It requires a routable public IP and usually requires router port forwarding for TCP `80` and `443`.

A setup.sk-compatible fallback uses a dynamic DNS hostname as the stable target and points each JurisDigta service hostname to it with `CNAME` records. This is less preferred because it exposes the home public IP, often fails with CGNAT, and moves more security responsibility to the origin network.
