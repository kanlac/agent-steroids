# Remote MCP entry (Claude / ChatGPT web connectors)

`scripts/remote-mcp.mjs` lets hosted clients (Claude custom connectors, ChatGPT Developer Mode) operate the shared Chrome. It speaks MCP Streamable HTTP (stateless, JSON responses) on a unix socket and execs `page.mjs` once per tool call, so tools and behaviour match the local CLI: `open`, `look`, `click`, `type`, `select`, `key`, `scroll`, `wait`, `do`, `eval`, `shot` (returns an image), `close`, and `run` when a TypeSafe key is configured.

It has **no authentication of its own**. The Chrome behind it holds your logged-in sessions, so it must only be reachable through an authenticating proxy. The setup below uses Cloudflare Access (OAuth for the clients) in front of a Cloudflare Tunnel. Never route the CDP port itself through the tunnel.

## Isolation

The server gives `page.mjs` its own `TMPDIR` (`<socket dir>/tmp`), so remote sessions keep a separate owned-tab list: they can act only on tabs opened through the server, and local agents cannot act on those. The browser profile (cookies, logins) is shared as usual.

## Setup

1. **Run the server.** macOS: `scripts/remote-mcp-launchd.sh install` (also `status`, `uninstall`) creates a launchd agent that keeps it alive. The socket defaults to `~/.config/cdp-chrome/remote/mcp.sock` (directory 0700, socket 0600); override with `cdp-chrome.remote_mcp_socket` in the steroids config file. `doctor.sh` checks that it answers.
2. **Access application.** In Cloudflare Zero Trust, add a self-hosted application for the public hostname, with a policy that allows only your identity. Under advanced settings turn on **Managed OAuth** with dynamic client registration, and allow the clients' redirect URIs (Claude: `https://claude.ai/api/mcp/auth_callback`; ChatGPT shows its own when you add the connector). Note the application's AUD tag and your team name.
3. **Tunnel ingress.** Add a rule to the cloudflared config, above the catch-all, then restart cloudflared and create the DNS route (`cloudflared tunnel route dns <tunnel> <host>`). `access` makes cloudflared reject requests without a valid Access JWT even if the Access policy is misconfigured.

   ```yaml
   - hostname: <host>
     service: unix:<absolute path to mcp.sock>
     originRequest:
       access:
         required: true
         teamName: <team>
         audTag: [<aud>]
   ```

4. **Verify.** An unauthenticated `POST https://<host>/mcp` must return 401 with OAuth discovery, never a tool list.
5. **Clients.** Connector URL `https://<host>/mcp`, OAuth, client ID and secret left empty (dynamic registration). Set `eval`, `type`, `click` and `do` to ask before each use.

## Operating notes

- Page text is untrusted: a page can try to steer the model. Tool confirmations and the single-identity Access policy are the guards; `eval` can read anything the logged-in profile can.
- The server log (`~/Library/Logs/cdp-chrome-remote-mcp.log` under launchd) records tool name, tab prefix, exit code and duration only, never arguments or output.
- Tabs opened remotely and left open stay in the shared Chrome; close them from the window if a session abandons them.
