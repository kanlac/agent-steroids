---
name: playwright-auth-manager
description: Manage browser authentication state for Playwright MCP Server. Use when working with websites requiring login, setting up Playwright authentication, managing multiple authentication sessions, or when browser automation needs preserved login sessions. Handles authentication file creation, multi-session configuration, and MCP server setup with saved credentials.
---

# Playwright Auth Manager

Manage browser authentication state for Playwright MCP, enabling automated browser sessions with preserved login credentials.

## Setup

Before using this skill, run the setup script to ensure Playwright is installed:

```bash
node <path-to-skill>/scripts/setup.js
```

The setup script will:
- Check if Playwright is installed on your system
- Install Playwright if it's not present
- Install Chromium browser if needed
- Do nothing if everything is already installed (safe to run multiple times)

**Note**: You don't need to read the script content - just run it and it will handle everything automatically.

## Quick Start

### First-Time Setup

1. **Save authentication state** for a website:
   ```bash
   cd <project-directory>
   node <path-to-skill>/scripts/save-auth-state.js \
     --url https://app.example.com/login \
     --user myaccount
   ```

2. **Configure MCP Server** with authentication:
   ```json
   {
     "mcpServers": {
       "playwright-myaccount": {
         "command": "npx",
         "args": [
           "@playwright/mcp@latest",
           "--isolated",
           "--storage-state=./myaccount-auth.json"
         ]
       }
     }
   }
   ```

3. **Verify .gitignore** includes auth files (see [Ensuring Git Ignore](#ensuring-git-ignore))

4. **Restart MCP client** to load the authenticated session

### Checking Authentication Status

When accessing a protected page, verify authentication by checking the page content:

```javascript
// Navigate to protected page
await browser_navigate({ url: "https://app.example.com/dashboard" });
await browser_snapshot();

// If snapshot shows "Sign In" or "Log In" → authentication needed
// If snapshot shows user-specific content → authenticated successfully
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

### Using the Script

The `scripts/save-auth-state.js` script opens a browser for manual login and saves the authentication state.

**Basic usage:**
```bash
node <path-to-skill>/scripts/save-auth-state.js \
  --url https://app.example.com/login \
  --output ./auth.json
```

**With session name (recommended for multiple sessions):**
```bash
node <path-to-skill>/scripts/save-auth-state.js \
  --url https://app.example.com/login \
  --user myproject
# Creates: myproject-auth.json
```

**Options:**
- `--url <url>`: Starting URL (login page)
- `--output <file>`: Output filename (default: `./auth.json`)
- `--user <name>`: Session name for the auth file (creates `<name>-auth.json`)

### Manual Process

The script will:
1. Open a browser window
2. Navigate to the specified URL
3. Wait for you to complete login manually
4. Prompt you to press Enter
5. Save cookies and localStorage to JSON file
6. Display saved data summary

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

When authentication expires or needs updating:

1. **Re-run the save script** with the same parameters:
   ```bash
   node scripts/save-auth-state.js --user mysession --url https://app.example.com/login
   ```

2. **Restart MCP server** (unless using `--save-session` option)

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

### CI/CD Integration

For automated testing environments:

1. **Encrypt auth files** before committing:
   ```bash
   gpg -c myauth.json
   ```

2. **Decrypt in CI pipeline**:
   ```bash
   gpg -d myauth.json.gpg > myauth.json
   ```

3. **Use in MCP configuration** with environment variables:
   ```json
   {
     "args": [
       "@playwright/mcp@latest",
       "--storage-state=${CI_PROJECT_DIR}/myauth.json",
       "--headless"
     ]
   }
   ```

## Troubleshooting

### "Authentication not working"

1. Verify auth file exists at configured path
2. Check auth file is not empty (should contain cookies array)
3. Ensure cookie domains match target website
4. Regenerate auth file if cookies expired

### "Script fails: Executable doesn't exist"

Install Playwright browsers:
```bash
npx playwright install chromium
```

### "Auth file appears in git status"

1. Add patterns to .gitignore (see [Ensuring Git Ignore](#ensuring-git-ignore))
2. Remove from git cache if already tracked:
   ```bash
   git rm --cached auth.json
   ```

### "Session expires too quickly"

Some websites use short-lived sessions. Solutions:
- Regenerate auth file before each use
- Use `--save-session` to auto-update
- Implement periodic auth refresh in workflow

## Resources

### scripts/

- **setup.js**: Initial setup script that checks and installs Playwright if needed. Run this first before using other scripts. Safe to run multiple times.
- **save-auth-state.js**: Interactive script to capture browser authentication state. Opens a browser, waits for manual login, and saves cookies/localStorage to JSON.

### references/

- **multi-session-setup.md**: Complete guide for configuring multiple Playwright MCP instances with separate authentication sessions. Read when managing multiple sessions.
- **usage-guide.md**: Comprehensive Playwright MCP authentication documentation including storage formats, configuration options, security best practices, and advanced workflows.

### assets/

- **gitignore-template**: Template .gitignore entries for Playwright auth files. Copy to project .gitignore to prevent committing sensitive auth data.
