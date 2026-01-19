---
name: playwright-auth-manager
description: Manage browser authentication state for Playwright MCP Server. Use when working with websites requiring login, setting up Playwright authentication, managing multiple authentication sessions, or when browser automation needs preserved login sessions. Handles authentication file creation, multi-session configuration, and MCP server setup with saved credentials.
---

# Playwright Auth Manager

Manage browser authentication state for Playwright MCP, enabling automated browser sessions with preserved login credentials.

**Use Case**: This skill is designed for **local development and testing**. Use it to help users automate browser interactions that require login during development, debugging, and local testing workflows.

**Not for Production**: This tool saves real authentication credentials and is meant for local use only. Never use it in production environments.

## Quick Start

### Typical Workflow for Coding Agent

1. **Run setup script** to install dependencies (safe to run multiple times):
   ```bash
   node <path-to-skill>/scripts/setup.js
   ```

2. **Provide auth capture command** to user - they must run it manually in a separate terminal. See [Saving Authentication State](#saving-authentication-state).

3. **Configure MCP Server** using user-scope configuration (not project scope). See [references/how-to-install-mcp.md](references/how-to-install-mcp.md).

4. **User must restart** MCP client to load the authenticated session.

### Checking Authentication Status

To verify if authentication is working:

```javascript
// Navigate to a protected page
await browser_navigate({ url: "https://app.example.com/dashboard" });
await browser_snapshot();

// Check the snapshot:
// - If it shows "Sign In" or "Log In" → authentication needed
// - If it shows user-specific content → authenticated successfully
```

## Workflow Decision Tree

```
User needs browser automation with login
    ↓
Run setup script (node scripts/setup.js)
    ↓
Check if auth file exists in ~/.config/playwrightAuth/
    ↓
    ├─ NO → Guide to save auth state (see "Saving Authentication State")
    │        ↓
    │        Configure MCP Server (see "Configuring MCP Server")
    │
    └─ YES → Check if multiple sessions needed
             ↓
             ├─ NO → Use single MCP instance with one auth file
             │
             └─ YES → Configure multiple MCP instances
                      (see references/how-to-install-mcp.md)
```

## Saving Authentication State

**Critical**: The authentication capture script must be run **manually by the user in a separate terminal window**. It requires interactive browser login.

### Providing the Command

Generate a complete command for the user:

```bash
node /path/to/skills/playwright-auth-manager/scripts/save-auth-state.js \
  --url <login-url> \
  --domain <domain-identifier> \
  --user <user-identifier>
```

**Example**:
```bash
node /path/to/skills/playwright-auth-manager/scripts/save-auth-state.js \
  --url https://localhost:3000/login \
  --domain localhost3000 \
  --user jack
```

This creates: `~/.config/playwrightAuth/localhost3000-jack.json`

### Script Parameters

- `--url <url>`: Login page URL (required)
- `--domain <name>`: Domain identifier like `localhost3000`, `github` (required)
- `--user <name>`: User identifier like `jack`, `alice` (required)
- `--output <file>`: Custom output path (optional, overrides standard naming)

**Naming Convention**: Files are saved as `~/.config/playwrightAuth/{domain}-{user}.json`, matching the MCP server pattern `playwright-{domain}-{user}`.

## Configuring MCP Server

Add MCP server configuration using **user-scope** settings (shared across all projects, not project-specific).

**See [references/how-to-install-mcp.md](references/how-to-install-mcp.md)** for complete configuration examples covering:
- User-scope configuration for different MCP clients
- Single and multiple session setup
- Server naming conventions
- Path configuration

## Refreshing Authentication

When authentication expires:

1. **Provide the save command** to user (same parameters as initial setup):
   ```bash
   node scripts/save-auth-state.js --domain localhost3000 --user jack --url https://localhost:3000/login
   ```

2. **User must restart MCP client** (unless config uses `--save-session`)

3. **Verify** by navigating to a protected page

## Advanced Usage

### Auto-Save Session Changes

Add `--save-session` flag to MCP config to auto-save auth changes. See [references/how-to-install-mcp.md](references/how-to-install-mcp.md).

### Dynamic Session Switching

For runtime session switching, see `browser_run_code` technique in [references/usage-guide.md](references/usage-guide.md).

## Troubleshooting

### Authentication Not Working

Check:
1. Auth file exists at `~/.config/playwrightAuth/`
2. File contains cookies array
3. Cookie domains match target website
4. Cookies not expired - regenerate if needed

### Script Fails: Executable Doesn't Exist

Install Playwright browsers:
```bash
npx playwright install chromium
```

### Session Expires Quickly

Options:
- Regenerate auth file before each use
- Use `--save-session` in MCP config
- Implement periodic refresh in workflow

## Resources

### scripts/

- **setup.js**: Installs Playwright in skill directory. Run first. Safe to run multiple times.
- **save-auth-state.js**: Captures browser auth state. **User must run manually** in separate terminal.

### references/

- **how-to-install-mcp.md**: Complete MCP configuration guide for all clients.
- **usage-guide.md**: Comprehensive usage documentation and best practices.
