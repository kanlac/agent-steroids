#!/usr/bin/env node
/**
 * Playwright Authentication State Saver
 *
 * Saves browser authentication state (cookies, localStorage) to a JSON file
 * for use with Playwright MCP Server.
 *
 * This script does NOT manage user permissions or access control. It simply
 * saves the authentication state from whatever account you log in to.
 *
 * Usage:
 *   node save-auth-state.js [options]
 *
 * Options:
 *   --url <url>       Starting URL (default: https://example.com)
 *   --output <file>   Output filename (default: ./auth.json)
 *   --user <name>     Session name for the auth file (creates <name>-auth.json)
 *
 * Examples:
 *   node save-auth-state.js --url https://app.example.com/login
 *   node save-auth-state.js --user myproject --url https://app.example.com
 *   node save-auth-state.js --output ./auth/session1.json
 */

const fs = require('fs');
const path = require('path');
const readline = require('readline');

// Parse command line arguments
function parseArgs() {
  const args = process.argv.slice(2);
  const options = {
    url: 'https://example.com',
    output: './auth.json',
    user: null
  };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--url':
        options.url = args[++i];
        break;
      case '--output':
        options.output = args[++i];
        break;
      case '--user':
        options.user = args[++i];
        break;
      case '--help':
      case '-h':
        console.log(`
Playwright Authentication State Saver

This script saves the authentication state from whatever account you log in to.
It does NOT manage user permissions or access control.

Usage:
  node save-auth-state.js [options]

Options:
  --url <url>       Starting URL (default: https://example.com)
  --output <file>   Output filename (default: ./auth.json)
  --user <name>     Session name for the auth file (creates <name>-auth.json)

Examples:
  node save-auth-state.js --url https://app.example.com/login
  node save-auth-state.js --user myproject --url https://app.example.com
  node save-auth-state.js --output ./auth/session1.json
        `);
        process.exit(0);
    }
  }

  // If user is specified, use it to generate filename
  if (options.user) {
    options.output = `./${options.user}-auth.json`;
  }

  return options;
}

// Check if file should be added to .gitignore
function checkGitignore(authFilePath) {
  const gitignorePath = path.join(process.cwd(), '.gitignore');
  const authFileName = path.basename(authFilePath);

  // Check if .gitignore exists
  if (!fs.existsSync(gitignorePath)) {
    console.log('\n⚠️  No .gitignore file found in current directory');
    console.log('💡 Consider creating one to avoid committing auth files:');
    console.log(`   echo "*.auth.json" >> .gitignore`);
    console.log(`   echo "auth.json" >> .gitignore`);
    return;
  }

  // Check if auth files are already in .gitignore
  const gitignoreContent = fs.readFileSync(gitignorePath, 'utf8');
  const lines = gitignoreContent.split('\n');

  const hasPattern = lines.some(line => {
    const trimmed = line.trim();
    return trimmed === '*.auth.json' ||
           trimmed === 'auth.json' ||
           trimmed === authFileName;
  });

  if (!hasPattern) {
    console.log('\n⚠️  Auth file pattern not found in .gitignore');
    console.log('💡 Add these lines to .gitignore to avoid committing auth files:');
    console.log(`   *.auth.json`);
    console.log(`   auth.json`);
  }
}

async function saveAuthState() {
  const options = parseArgs();

  // Check if playwright is available
  let chromium;
  try {
    chromium = require('playwright').chromium;
  } catch (e) {
    console.error('❌ Playwright not found. Please install it:');
    console.error('   npm install playwright');
    console.error('   npx playwright install chromium');
    process.exit(1);
  }

  console.log('🚀 Starting browser...');
  console.log(`📍 Starting URL: ${options.url}`);

  let browser;
  try {
    // Try to launch with Chrome channel first
    try {
      browser = await chromium.launch({
        headless: false,
        channel: 'chrome'
      });
    } catch (e) {
      // Fallback to default chromium
      console.log('⚠️  Chrome not found, using default Chromium');
      browser = await chromium.launch({
        headless: false
      });
    }

    const context = await browser.newContext();
    const page = await context.newPage();

    // Navigate to the starting URL
    await page.goto(options.url);

    console.log('\n📝 Please complete login in the browser window...');
    console.log('⏳ After logging in, return here and press Enter to save auth state');

    // Wait for user to press Enter
    await new Promise(resolve => {
      const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout
      });
      rl.question('\nPress Enter when ready to save...', () => {
        rl.close();
        resolve();
      });
    });

    // Ensure output directory exists
    const outputDir = path.dirname(options.output);
    if (outputDir !== '.' && !fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }

    // Save authentication state
    const authStatePath = path.resolve(options.output);
    await context.storageState({ path: authStatePath });

    console.log(`\n✅ Authentication state saved to: ${authStatePath}`);

    // Show what was saved
    const authState = JSON.parse(fs.readFileSync(authStatePath, 'utf8'));
    const cookieCount = authState.cookies ? authState.cookies.length : 0;
    const originCount = authState.origins ? authState.origins.length : 0;

    console.log('\n📊 Saved data:');
    console.log(`   - ${cookieCount} cookie(s)`);
    console.log(`   - ${originCount} origin(s) with localStorage`);

    // Check .gitignore
    checkGitignore(authStatePath);

    await browser.close();

    console.log('\n🎉 Done! Authentication state saved successfully.');
    console.log('\n💡 Next steps:');
    console.log('   1. Add to MCP config: --storage-state=' + authStatePath);
    console.log('   2. Ensure auth file is in .gitignore');
    if (options.user) {
      console.log(`   3. Configure MCP Server as: playwright-${options.user}`);
      console.log(`      (The name "${options.user}" is just a label for this session)`);
    }

  } catch (error) {
    console.error('\n❌ Error:', error.message);
    if (error.message.includes('Executable doesn\'t exist')) {
      console.log('\n💡 Playwright browser not installed. Run:');
      console.log('   npx playwright install chromium');
    }
    if (browser) {
      await browser.close();
    }
    process.exit(1);
  }
}

saveAuthState().catch(console.error);
