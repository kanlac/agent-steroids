---
name: playwright-auth-manager
description: Manage browser authentication state for Playwright MCP Server. Use when working with websites requiring login, setting up Playwright authentication, managing multiple authentication sessions, or when browser automation needs preserved login sessions. Handles authentication file creation, multi-session configuration, and MCP server setup with saved credentials.
---

# Playwright Auth Manager

Manage browser authentication state for Playwright MCP, enabling automated browser sessions with preserved login credentials.

**Use Case**: This skill is designed for **local development and testing**. Use it to help users automate browser interactions that require login during development, debugging, and local testing workflows.

**Not for Production**: This tool saves real authentication credentials and is meant for local use only. Never use it in production environments.

## Setup

### Initial Setup for Coding Agent

Before using this skill, ensure Playwright is installed by running the setup script:

```bash
node <path-to-skill>/scripts/setup.js
```

The setup script will:
- Check if Playwright is installed on the system
- Install Playwright if it's not present
- Install Chromium browser if needed
- Do nothing if everything is already installed (safe to run multiple times)

**Note**: The script handles everything automatically. No need to read its content.

## Quick Start

### Typical Workflow for Coding Agent

When helping a user set up authentication for the first time:

1. **Guide user to save authentication state**:
   - Provide the command with appropriate URL and session name
   - Instruct user to run it in a new terminal window
   - See [Saving Authentication State](#saving-authentication-state) for details

2. **Configure MCP Server** in the user's MCP configuration file:
   ```json
   {
     "mcpServers": {
       "playwright-jack": {
         "command": "npx",
         "args": [
           "@playwright/mcp@latest",
           "--isolated",
           "--storage-state=./jack-auth.json"
         ]
       }
     }
   }
   ```

3. **Verify .gitignore** includes auth file patterns (see [Ensuring Git Ignore](#ensuring-git-ignore))

4. **Instruct user to restart** their MCP client to load the authenticated session

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
Check if auth file exists for this session
    ↓
    ├─ NO → Guide to save auth state (see "Saving Authentication State")
    │        ↓
    │        Verify .gitignore (see "Ensuring Git Ignore")
    │        ↓
    │        Configure MCP Server (see "Configuring MCP Server")
    │
    └─ YES → Check if multiple sessions needed
             ↓
             ├─ NO → Use single MCP instance with one auth file
             │
             └─ YES → Configure multiple MCP instances
                      (see references/multi-session-setup.md)
```

## Saving Authentication State

### Instructions for Coding Agent

**Critical**: The authentication script must be run **manually by the user in a separate terminal window**. Do not attempt to run this script yourself as it requires interactive user input.

### How to Guide the User

When the user needs to save authentication state, provide them with a complete command to run:

1. **Generate the command** with these parameters:
   - Full absolute path to `save-auth-state.js`
   - `--url` with the login page URL
   - `--user` with a descriptive session name (recommended) OR `--output` for custom path

2. **Instruct the user** with clear steps:
   ```
   Please run the following command in a new terminal window:

   [paste the command here]

   Steps:
   1. Open a new terminal window
   2. Copy and paste the command above
   3. Press Enter to run it
   4. Log in when the browser opens
   5. Press Enter in the terminal after logging in

   This will create: [filename].auth.json
   ```

3. **Example command format**:
   ```bash
   node /path/to/skills/playwright-auth-manager/scripts/save-auth-state.js \
     --url https://app.example.com/login \
     --user jack
   ```
   This creates: `jack-auth.json`

### Script Parameters

- `--url <url>`: Starting URL (login page) - **required**
- `--output <file>`: Output filename (default: `./auth.json`)
- `--user <name>`: Session name for the auth file (creates `<name>-auth.json`) - **recommended**

**Note**: Recommend using `--user` as it creates clearly-named files. The user controls the file name through this parameter.

### Script Behavior (for Reference)

The script will:
1. Open a browser window
2. Navigate to the specified URL
3. Wait for the user to complete login manually
4. Prompt the user to press Enter when ready
5. Save cookies and localStorage to JSON file
6. Display saved data summary
7. Close the browser

### Recommended Directory Structure

Store auth files in a dedicated directory:

```
project/
├── .playwright-auth/
│   ├── account1-auth.json
│   ├── account2-auth.json
│   └── account3-auth.json
├── .gitignore  (must include .playwright-auth/)
└── ...
```

Or use a centralized location:
```
~/.playwright-auth/
├── project1-session1.json
├── project1-session2.json
└── project2-session1.json
```

## Configuring MCP Server

### Single Session Configuration

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--isolated",
        "--storage-state=/path/to/auth.json"
      ]
    }
  }
}
```

### Multiple Session Configuration

For projects requiring multiple authentication sessions (e.g., different accounts, different projects), configure separate MCP instances. **See `references/multi-session-setup.md` for complete guide.**

Quick example:
```json
{
  "mcpServers": {
    "playwright-account1": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--isolated",
        "--storage-state=./.playwright-auth/account1-auth.json"
      ]
    },
    "playwright-account2": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--isolated",
        "--storage-state=./.playwright-auth/account2-auth.json"
      ]
    }
  }
}
```

Switching between sessions:
```javascript
// Use first account
await mcp__playwright-account1__browser_navigate({ url: "..." });

// Switch to second account
await mcp__playwright-account2__browser_navigate({ url: "..." });
```

## Ensuring Git Ignore

**Critical: Always exclude auth files from version control.**

### Automatic Check

The `save-auth-state.js` script automatically checks .gitignore and warns if auth files are not excluded.

### Manual Setup

Add these patterns to `.gitignore`:

```gitignore
# Playwright authentication files
*.auth.json
auth.json
.playwright-auth/
```

Or copy the complete template:
```bash
cat <path-to-skill>/assets/gitignore-template >> .gitignore
```

### Verification

After adding to .gitignore:
```bash
git status
# Auth files should NOT appear in untracked files
```

## Refreshing Authentication

When authentication expires or needs updating, guide the user to:

1. **Re-run the save script** with the same parameters used originally:
   ```bash
   node scripts/save-auth-state.js --user jack --url https://app.example.com/login
   ```

2. **Restart MCP server** (unless the configuration uses `--save-session` option)

3. **Verify new authentication** by accessing a protected page

## Advanced Usage

### Auto-Save Session Changes

To automatically save authentication changes during the session:

```json
{
  "playwright": {
    "args": [
      "@playwright/mcp@latest",
      "--isolated",
      "--storage-state=./auth.json",
      "--save-session"
    ]
  }
}
```

With this option, any authentication changes (new cookies, localStorage updates) are automatically saved.

### Dynamic Session Switching

For runtime session switching within a single MCP instance, see the `browser_run_code` technique in `references/usage-guide.md`.

## Troubleshooting

### "Authentication not working"

When authentication fails, check:
1. Verify auth file exists at the configured path
2. Check auth file is not empty (should contain cookies array)
3. Ensure cookie domains match the target website
4. Regenerate auth file if cookies have expired

### "Script fails: Executable doesn't exist"

Guide user to install Playwright browsers:
```bash
npx playwright install chromium
```

### "Auth file appears in git status"

Help user fix this:
1. Add patterns to .gitignore (see [Ensuring Git Ignore](#ensuring-git-ignore))
2. Remove from git cache if already tracked:
   ```bash
   git rm --cached auth.json
   ```

### "Session expires too quickly"

Some websites use short-lived sessions. Suggest:
- Regenerate auth file before each use
- Use `--save-session` option to auto-update
- Implement periodic auth refresh in the workflow

## Resources

### scripts/

- **setup.js**: Initial setup script that checks and installs Playwright if needed. Run this first before using other scripts. Safe to run multiple times.
- **save-auth-state.js**: Interactive script to capture browser authentication state. Opens a browser, waits for manual login (user presses Enter when ready), and saves cookies/localStorage to JSON. **This script must be run by the user in a separate terminal window** - provide the command to the user but do not attempt to run it yourself.

### references/

- **multi-session-setup.md**: Complete guide for configuring multiple Playwright MCP instances with separate authentication sessions. Read when managing multiple sessions.
- **usage-guide.md**: Comprehensive Playwright MCP authentication documentation including storage formats, configuration options, security best practices, and advanced workflows.

### assets/

- **gitignore-template**: Template .gitignore entries for Playwright auth files. Copy to project .gitignore to prevent committing sensitive auth data.
