#!/usr/bin/env node
/**
 * Playwright Setup Script
 *
 * Checks if Playwright is installed and installs it if necessary.
 * Safe to run multiple times - will skip installation if already present.
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

function log(message, type = 'info') {
  const icons = {
    info: 'ℹ️',
    success: '✅',
    warning: '⚠️',
    error: '❌',
    working: '🔄'
  };
  console.log(`${icons[type]}  ${message}`);
}

function isPlaywrightInstalled() {
  try {
    require.resolve('playwright');
    return true;
  } catch (e) {
    return false;
  }
}

function checkChromiumInstalled() {
  try {
    const { chromium } = require('playwright');
    // Try to get executable path - this will throw if browsers aren't installed
    execSync('npx playwright --version', { stdio: 'pipe' });
    return true;
  } catch (e) {
    return false;
  }
}

async function setup() {
  console.log('\n🎭 Playwright Authentication Manager Setup\n');

  // Step 1: Check if Playwright package is installed
  log('Checking Playwright installation...', 'working');

  if (!isPlaywrightInstalled()) {
    log('Playwright not found. Installing...', 'working');
    try {
      execSync('npm install playwright', {
        stdio: 'inherit',
        cwd: process.cwd()
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

  // Step 2: Check if browsers are installed
  log('Checking Chromium browser installation...', 'working');

  if (!checkChromiumInstalled()) {
    log('Chromium browser not found. Installing...', 'working');
    try {
      execSync('npx playwright install chromium', {
        stdio: 'inherit'
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

  console.log('\n✨ Setup complete! You can now use the playwright-auth-manager skill.\n');
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
