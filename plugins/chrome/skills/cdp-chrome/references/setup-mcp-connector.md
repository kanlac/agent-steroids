# Exposing the shared Chrome as an MCP connector for web AI apps

Goal: Claude (custom connector) and ChatGPT (Developer Mode connector) on the web operate this machine's shared, logged-in Chrome. Their requests come from their own clouds, so the entry point must be public, and because the browser holds your sessions it must sit behind real authentication.

```
Claude / ChatGPT (their cloud)
   │ HTTPS · MCP Streamable HTTP · OAuth bearer
   ▼
Cloudflare Access app (Managed OAuth; policy: only you)
   │ adds Cf-Access-Jwt-Assertion
   ▼
cloudflared (ingress rule re-checks the Access JWT)
   │ unix socket
   ▼
scripts/remote-mcp.mjs ──exec per tool call──▶ page.mjs ──CDP──▶ 127.0.0.1:<port>
```

Invariants: the CDP port never goes through the tunnel (raw CDP hands over every cookie in the profile); no authless or "secret URL" setups; page logic lives only in `page.mjs`. Design rationale and rejected alternatives: `docs/tech/20261030-cdp-chrome-remote-mcp.md` in the agent-steroids repo.

## What the server exposes

`remote-mcp.mjs` is a zero-dependency, stateless Streamable HTTP MCP server (JSON responses, `POST /mcp` only). Each tool call runs `page.mjs` once: `open`, `look`, `click`, `type`, `select`, `key`, `scroll`, `wait`, `do`, `eval`, `shot` (returns an image), `close`, plus `run` when a TypeSafe key is configured. Exit code 2 (an action FAILED) and other errors come back as `isError`; `run` hand-backs (exit 3) are normal results.

Isolation: the server gives `page.mjs` its own `TMPDIR` (`<socket dir>/tmp`), so remote sessions keep a separate owned-tab list. They can act only on tabs opened through the server; local agents cannot act on those, and neither side can touch tabs you opened by hand. Remote sessions still share one list among themselves, and the profile (cookies, logins) is shared as always.

## Prerequisites

- cdp-chrome running and `doctor.sh` passing; Node >= 22.
- A domain on Cloudflare and a cloudflared tunnel already running on this machine (adding one ingress rule is enough; no second tunnel).
- Cloudflare API access with Zero Trust scopes. `wrangler login` tokens lack Access scopes; the `cf` CLI (`npm i -g cf`, pin a version) logs in with `cf auth login --no-browser`, an OAuth device flow you approve from any device already signed in to Cloudflare. That also sidesteps dashboard logins that demand a hardware security key an agent cannot touch. Discover commands with `cf cli search "<task>"`; pass raw JSON with `--body`.

## 1. Run the server

macOS: `scripts/remote-mcp-launchd.sh install` (also `status`, `uninstall`) writes a launchd agent with KeepAlive that runs `remote-mcp.mjs` from the checkout you install from. The socket defaults to `~/.config/cdp-chrome/remote/mcp.sock` (directory 0700, socket 0600); override with `cdp-chrome.remote_mcp_socket` in the steroids config file (macOS/Linux `~/.config/steroids.json`, Windows `%APPDATA%\steroids.json`). A second instance on the same socket refuses to start; a stale socket from a crash is cleared. `doctor.sh` reports whether it answers.

## 2. Cloudflare Access

1. **Zero Trust organization** (once per account): if `cf zero-trust organization get` says Access is not enabled, create one with a team domain `<team>.cloudflareaccess.com`. Leave `deny_unmatched_requests` off so other public sites on the account are unaffected.
2. **Identity provider**: the built-in One-time PIN is enough (`{"name":"One-time PIN","type":"onetimepin","config":{}}`); Access emails a code at login.
3. **Self-hosted application** for `<host>` with Managed OAuth:

   ```json
   {
     "name": "cdp-chrome remote MCP",
     "type": "self_hosted",
     "domain": "<host>",
     "allowed_idps": ["<one-time-pin idp id>"],
     "auto_redirect_to_identity": true,
     "app_launcher_visible": false,
     "policies": [{ "name": "owner only", "decision": "allow", "include": [{ "email": { "email": "<you>" } }] }],
     "oauth_configuration": {
       "enabled": true,
       "dynamic_client_registration": {
         "enabled": true,
         "allow_any_on_localhost": false,
         "allow_any_on_loopback": false,
         "allowed_uris": ["https://claude.ai/api/mcp/auth_callback", "https://chatgpt.com/*"]
       },
       "grant": { "access_token_lifetime": "15m", "session_duration": "720h" }
     }
   }
   ```

   `grant.session_duration` is the refresh lifetime: clients ask you to log in again about once a month. Keep the response's `aud`; the tunnel rule needs it.

The MCP server itself does no OAuth, which is exactly what Managed OAuth expects: Access answers unauthenticated requests with a 401 that carries `resource_metadata`, serves the discovery documents, and handles dynamic client registration.

## 3. Tunnel ingress

Add a rule above the catch-all in the cloudflared config, validate, route DNS, restart:

```yaml
- hostname: <host>
  service: unix:<absolute path to mcp.sock>
  originRequest:
    access:
      required: true
      teamName: <team>
      audTag:
        - <aud>
```

- `cloudflared tunnel --config <config> ingress validate`, then `ingress rule https://<host>/mcp` must match the new rule.
- `cloudflared tunnel route dns <tunnel> <host>` creates the CNAME.
- Back up the config first. Restarting cloudflared interrupts every site on the tunnel for a few seconds; if launchd keeps it alive, terminating the process is enough for it to come back with the new config.
- `access.required` makes cloudflared itself reject requests without a valid Access JWT, so a misconfigured Access policy does not expose the browser.

## 4. Verify from outside

- Unauthenticated `POST https://<host>/mcp` returns **401** with `WWW-Authenticate: Bearer … resource_metadata="…"`, never a tool list.
- The `resource` in that metadata document equals `https://<host>/mcp` exactly (Claude requires the exact URL, path included).
- `https://<host>/.well-known/oauth-authorization-server` lists authorization, token and registration endpoints and `S256`.
- Dynamic registration with a redirect outside the allow-list fails with `invalid_client_metadata`.
- A forged `Cf-Access-Jwt-Assertion` header still gets 401.
- `doctor.sh` shows `OK: remote MCP answers … (mode 600)`.

## 5. Add the connectors (done by the user in each web app)

- **Claude**: Settings → Connectors → Add custom connector. URL `https://<host>/mcp`; leave the advanced client ID and secret empty so Claude registers itself. Connect, then log in on the Access page with the allowed email and the emailed code.
- **ChatGPT**: Settings → Apps & Connectors → Advanced settings → enable Developer mode, then create a connector with the same URL and OAuth. In a chat, pick Developer mode and the connector from the composer tools. Whether Plus/Pro plans allow write actions has varied; if only read-only tools work, that is the plan, not the server.
- In both, set `eval`, `type`, `click` and `do` to ask before each use; read-only tools (`look`, `shot`, `wait`, `scroll`) can run freely.
- Icon upload limits seen in practice: PNG, 256 px or larger, at most 10 KB. Use a full-bleed square; the apps crop it to a circle or rounded square themselves.
- Smoke test: "open https://example.com with the connector, tell me the title, then close the tab".

## Operating notes

- Page text is untrusted; a page can try to steer the model. Tool confirmations and the single-identity Access policy are the guards. `eval` can read anything the logged-in profile can.
- The server log (`~/Library/Logs/cdp-chrome-remote-mcp.log` under launchd) records tool name, tab prefix, exit code and duration only, never arguments or output.
- Tabs a remote session abandons stay open in the shared Chrome; close them from the window.
- Kill switch: `scripts/remote-mcp-launchd.sh uninstall`, or disable the Access application. Full rollback: restore the cloudflared config backup and restart, then delete the DNS record and the Access application.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Client cannot reach the server and the origin log shows nothing | DNS route missing, or the ingress rule sits below the catch-all |
| `invalid_client_metadata` / redirect URI not allowed | The client's callback is not in `allowed_uris` |
| The Access page rejects the email | The policy's email differs from the one entered, or the IdP is not in `allowed_idps` |
| 502 from Cloudflare after login | Server down or socket path wrong: `remote-mcp-launchd.sh status`, `doctor.sh` |
| Tool calls fail with `cdp-chrome is not listening` | Chrome itself is down: `start.sh` |
| `target … was not created by 'open'` | The tab was opened locally or by hand; remote sessions only see their own tabs |
