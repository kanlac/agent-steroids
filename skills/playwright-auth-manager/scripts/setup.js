#!/usr/bin/env node
/**
 * Playwright Setup Script
 *
 * Installs Playwright dependencies in the SKILL directory (not the user's project).
 * This keeps the user's project clean and avoids dependency pollution.
 *
 * Safe to run multiple times - will skip installation if already present.
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// Skill root directory
const SKILL_ROOT = path.dirname(__dirname);

function log(message, type = 'info') {
  const icons = {
    info: 'i',
    success: '+',
    warning: '!',
    error: 'x',
    working: '~'
  };
  console.log(`[${icons[type]}] ${message}`);
}

function isPlaywrightInstalled() {
  const playwrightPath = path.join(SKILL_ROOT, 'node_modules', 'playwright');
  return fs.existsSync(playwrightPath);
}

function checkChromiumInstalled() {
  try {
    // Check if chromium browser is installed
    execSync('npx playwright --version', { stdio: 'pipe', cwd: SKILL_ROOT });
    return true;
  } catch (e) {
    return false;
  }
}

async function setup() {
  console.log('\nPlaywright Authentication Manager Setup\n');
  console.log(`Skill directory: ${SKILL_ROOT}`);
  console.log('(Dependencies will be installed here, not in your project)\n');

  // Step 1: Install npm dependencies in skill directory
  log('Checking Playwright installation...', 'working');

  if (!isPlaywrightInstalled()) {
    log('Installing Playwright in skill directory...', 'working');
    try {
      execSync('npm install', {
        stdio: 'inherit',
        cwd: SKILL_ROOT
      });
      log('Playwright package installed successfully', 'success');
    } catch (error) {
      log('Failed to install Playwright package', 'error');
      console.error(error.message);
      process.exit(1);
    }
  } else {
    log('Playwright package is already installed', 'success');
  }

  // Step 2: Install Chromium browser
  log('Checking Chromium browser installation...', 'working');

  if (!checkChromiumInstalled()) {
    log('Installing Chromium browser...', 'working');
    try {
      execSync('npx playwright install chromium', {
        stdio: 'inherit',
        cwd: SKILL_ROOT
      });
      log('Chromium browser installed successfully', 'success');
    } catch (error) {
      log('Failed to install Chromium browser', 'error');
      console.error(error.message);
      process.exit(1);
    }
  } else {
    log('Chromium browser is already installed', 'success');
  }

  console.log('\nSetup complete!\n');
  console.log('Next steps:');
  console.log('  1. Run save-auth-state.js to capture authentication');
  console.log('  2. Configure your MCP server with the auth file');
  console.log('  3. Start automating!\n');
}

setup().catch(error => {
  log('Setup failed', 'error');
  console.error(error);
  process.exit(1);
});
