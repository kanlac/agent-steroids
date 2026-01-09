# dev-cycle Plugin

> Automated development-evaluation feedback loop system for Claude Code

## Overview

The `dev-cycle` plugin establishes an autonomous development workflow where two specialized agents (developer and evaluator) iterate continuously until all acceptance criteria are met. Think of it as having an AI pair programming partner with built-in QA review.

**Key Benefits:**
- Clear requirements with measurable acceptance criteria
- Automated iteration until quality standards are met
- Complete audit trail of development decisions
- Systematic testing and validation
- Reduced back-and-forth by automating the feedback loop

## How It Works

```
┌──────────────┐
│ 1. /task-init│  → Create task with requirements and acceptance criteria
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  requirement │  → Clear specification of what needs to be built
│     .md      │     and how success is measured
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ 2. /task-run │  → Start automated feedback loop
└──────┬───────┘
       │
       ▼
    ┌──────────────────────────────────┐
    │   FEEDBACK LOOP (max 20 cycles)  │
    │                                   │
    │  🔵 Developer Agent               │
    │    ├─ Read requirements          │
    │    ├─ Read previous feedback     │
    │    ├─ Implement/fix features     │
    │    └─ Generate work report       │
    │                                   │
    │  🟢 Evaluator Agent               │
    │    ├─ Read requirements          │
    │    ├─ Read work report           │
    │    ├─ Run tests                  │
    │    ├─ Verify functionality       │
    │    └─ Generate evaluation report │
    │                                   │
    │  Decision:                        │
    │    ├─ ✅ PASSED → Exit (success) │
    │    └─ ❌ FAILED → Next iteration │
    └──────────────────────────────────┘
       │
       ▼
┌──────────────┐
│ 🎉 Complete  │  → All acceptance criteria met
└──────────────┘     Tests passing
                     Ready for delivery
```

## Architecture

### Components

1. **`/task-init`** - Slash command to create tasks
   - Creates `docs/{task-name}/` directory
   - Guides interactive requirements gathering
   - Generates `requirement.md` with acceptance criteria

2. **`/task-run`** - Slash command to execute feedback loop
   - Orchestrates developer and evaluator agents
   - Manages up to 20 iterations
   - Tracks progress and reports results

3. **developer** - Subagent for implementation
   - Reads requirements and feedback
   - Implements features and fixes bugs
   - Generates detailed work reports

4. **evaluator** - Subagent for verification
   - Tests against acceptance criteria
   - Runs automated/manual tests
   - Generates pass/fail evaluation reports

### File Structure

```
docs/
└── {task-name}/
    ├── requirement.md                          # Requirements and acceptance criteria
    ├── 260110143 0-work-report-sonnet.md       # Iteration 1: Developer's work
    ├── 260110144 5-eval-report-sonnet.md       # Iteration 1: Evaluation results
    ├── 260110150 0-work-report-sonnet.md       # Iteration 2: Developer's fixes
    ├── 260110151 5-eval-report-sonnet.md       # Iteration 2: Evaluation results
    └── ...                                     # Additional iterations as needed
```

## Installation

### Option 1: Local Plugin (Recommended for Development)

```bash
# Clone or create the plugin in your project
mkdir -p .claude/plugins/dev-cycle
cd .claude/plugins/dev-cycle

# Copy the plugin files
cp -r /path/to/dev-cycle-plugin/* .

# Enable the plugin in Claude Code settings
```

### Option 2: Symlink (For Development)

```bash
# Create symlink from your development location
ln -s /path/to/dev-cycle-plugin ~/.claude/plugins/dev-cycle
```

### Verify Installation

```bash
# In Claude Code, check available commands
/help

# You should see:
# - /task-init
# - /task-run
```

## Usage

### Quick Start

```bash
# 1. Create a new task with requirements
/task-init user-authentication

# Claude will interactively ask you:
# - What's the goal?
# - What technology stack?
# - What are the acceptance criteria?

# 2. Start the automated development cycle
/task-run user-authentication

# Claude will now iterate automatically until:
# - All acceptance criteria pass (✅ success)
# - OR 20 iterations reached (⚠️ timeout)
```

### Detailed Workflow

#### Step 1: Initialize Task

```bash
/task-init my-feature
```

Claude will guide you through:

1. **Core Goals**
   - What problem are you solving?
   - Who is this for?

2. **Technical Details**
   - What languages/frameworks?
   - Any integrations needed?
   - Existing code to modify?

3. **Acceptance Criteria** (Most Important!)
   - How will you know it's done?
   - What tests must pass?
   - What functionality must work?

**Example Acceptance Criteria:**

Good (Specific and Testable):
```
- [ ] User can login with email/password
- [ ] JWT token is returned on successful login
- [ ] All tests pass: npm test auth
- [ ] Protected routes redirect when not authenticated
- [ ] No console errors during auth flow
```

Bad (Vague):
```
- [ ] Authentication works
- [ ] It should be secure
- [ ] Tests should pass
```

#### Step 2: Run Development Cycle

```bash
/task-run my-feature
```

Claude will:
1. Display your requirements
2. Start iteration 1
3. Launch developer agent to implement
4. Launch evaluator agent to test
5. Show results
6. Continue iterating if needed

**You don't need to do anything** - just wait for results!

#### Step 3: Review Results

**If successful (✅ PASSED):**
```
🎉 TASK COMPLETE - ALL ACCEPTANCE CRITERIA MET

Task: my-feature
Total iterations: 3
Final status: ✅ PASSED

All reports saved in: docs/my-feature/
```

**If max iterations reached (⚠️ FAILED):**
```
⚠️  MAXIMUM ITERATIONS REACHED

Task: my-feature
Total iterations: 20
Final status: ❌ FAILED

Review the reports to understand what's blocking completion.
```

You can then:
- Review evaluation reports to see what's failing
- Manually fix blockers
- Run `/task-run my-feature` again to continue

## Configuration

### Maximum Iterations

Default: 20 iterations

To change, edit `.claude/plugins/dev-cycle/commands/task-run.md`:

```javascript
const MAX_ITERATIONS = 30;  // Increase if needed
```

### Task Directory

Default: `docs/`

To change, edit `.claude/plugins/dev-cycle/commands/task-run.md`:

```javascript
const TASK_BASE_DIR = 'tasks';  // Use different directory
```

### Agent Models

Default: Both agents use `sonnet`

To use different models, edit the agent frontmatter in:
- `.claude/plugins/dev-cycle/agents/developer.md`
- `.claude/plugins/dev-cycle/agents/evaluator.md`

```yaml
---
name: developer
model: opus  # Change to opus, haiku, etc.
---
```

## Examples

### Example 1: API Endpoint with Tests

```bash
/task-init payment-api

# Claude asks questions, you respond:
# Goal: Add a payment processing API endpoint
# Stack: Node.js, Express, Stripe API
# Tests: Jest unit tests
# Acceptance:
#   - POST /api/payment endpoint works
#   - Stripe integration processes payments
#   - All tests pass: npm test payment
#   - Error handling returns 400/500 appropriately

/task-run payment-api

# Claude iterates until all tests pass
```

### Example 2: UI Component with Manual Testing

```bash
/task-init dark-mode-toggle

# Goal: Add dark mode toggle to settings page
# Stack: React, CSS variables
# Acceptance:
#   - Toggle button appears in settings
#   - Clicking toggles between light/dark
#   - Preference persists in localStorage
#   - No visual glitches during transition

/task-run dark-mode-toggle

# Claude builds, evaluator manually tests each criterion
```

### Example 3: Bug Fix with Regression Tests

```bash
/task-init fix-memory-leak

# Goal: Fix memory leak in WebSocket connection
# Stack: JavaScript, WebSocket API
# Acceptance:
#   - Memory usage stays stable over 1 hour
#   - WebSocket cleanup happens on disconnect
#   - Existing tests still pass: npm test
#   - Chrome DevTools shows no detached listeners

/task-run fix-memory-leak

# Claude fixes, evaluator verifies with profiling
```

## Best Practices

### Writing Good Acceptance Criteria

✅ **DO:**
- Be specific and measurable
- Include test commands that can be run
- List exact functionality that must work
- Specify expected behavior for edge cases
- Include quality standards (no errors, performance)

❌ **DON'T:**
- Use vague terms like "works well" or "is good"
- Skip testing requirements
- Assume "common sense" - be explicit
- Mix implementation details with outcomes

### When to Use dev-cycle

**Good use cases:**
- New features with clear requirements
- Bug fixes that need verification
- Refactoring with test coverage
- Features requiring iteration to get right

**Not ideal for:**
- Exploratory coding without clear goals
- Quick one-off scripts
- Tasks without testable outcomes
- Open-ended research

### Managing Long-Running Tasks

If a task hits 20 iterations without completing:

1. **Review the latest evaluation report**
   ```bash
   # Find the latest eval report
   ls -t docs/{task-name}/*-eval-report-*.md | head -1

   # Read it
   cat docs/{task-name}/260110160 0-eval-report-sonnet.md
   ```

2. **Identify blockers**
   - Are acceptance criteria too strict?
   - Is there a fundamental architectural issue?
   - Are tests flaky or environment-dependent?

3. **Intervene manually**
   - Fix critical blockers yourself
   - Adjust acceptance criteria if unrealistic
   - Update requirements if scope changed

4. **Resume the cycle**
   ```bash
   /task-run {task-name}  # Continues where it left off
   ```

## Troubleshooting

### Issue: Task directory not found

```
❌ Task directory not found: docs/{task-name}/
```

**Solution:** Run `/task-init {task-name}` first to create the task.

### Issue: No requirement document

```
❌ Requirement document missing
```

**Solution:** The task directory exists but has no `requirement.md`. Run `/task-init {task-name}` to create it.

### Issue: Agent doesn't generate report

```
❌ Expected report file not found
```

**Solution:** This is a plugin bug. Check:
- Agent file exists in `agents/` directory
- Agent has proper frontmatter
- Agent instructions include report generation

### Issue: Infinite loop - keeps failing

**Symptoms:** Task fails every iteration with same error

**Solutions:**
1. Review evaluation report for root cause
2. Check if acceptance criteria are achievable
3. Verify test commands actually work
4. Look for environment issues (missing dependencies, etc.)
5. Manually fix the blocking issue
6. Update requirements if needed

### Issue: Evaluation always passes too easily

**Symptoms:** Evaluator marks work as passed when it shouldn't

**Solutions:**
1. Review acceptance criteria - are they specific enough?
2. Add explicit test commands to run
3. Include negative test cases
4. Specify quality thresholds (performance, error rates)

### Issue: Development is too slow

**Symptoms:** Each iteration takes a long time

**Solutions:**
1. Break task into smaller sub-tasks
2. Use more focused acceptance criteria
3. Consider using faster model (haiku) for simpler tasks
4. Reduce scope of the task

## Advanced Usage

### Custom Testing Strategies

#### Playwright E2E Testing

```markdown
## Acceptance Criteria

- [ ] All Playwright tests pass: `npx playwright test`
- [ ] User flow "login → dashboard → logout" works
- [ ] No console errors in browser
```

The evaluator will use Playwright MCP to run browser tests.

#### API Testing

```markdown
## Acceptance Criteria

- [ ] GET /api/users returns 200
- [ ] POST /api/users creates user and returns 201
- [ ] Invalid input returns 400 with error message
- [ ] All API tests pass: `npm run test:api`
```

The evaluator will use curl or test frameworks to verify endpoints.

#### Performance Testing

```markdown
## Acceptance Criteria

- [ ] Page load time < 2 seconds
- [ ] API response time < 200ms
- [ ] Lighthouse performance score > 90
- [ ] No memory leaks after 1 hour usage
```

The evaluator will use performance profiling tools.

### Multi-Task Workflows

You can run multiple tasks in parallel:

```bash
# Terminal 1
/task-run feature-a

# Terminal 2
/task-run feature-b
```

Each task maintains independent state in its own directory.

### Resuming After Manual Changes

If you manually edit code during a cycle:

```bash
# The next iteration will pick up your changes
/task-run {task-name}  # Developer sees your edits
```

The developer agent will see your changes in the codebase and build on them.

## FAQ

**Q: How many iterations typically needed?**
A: Most tasks complete in 2-5 iterations. Simple tasks may complete in 1 iteration. Complex tasks might need 10-15.

**Q: Can I stop the cycle mid-iteration?**
A: Yes, use Ctrl+C to interrupt. Reports generated so far are saved. Resume with `/task-run {task-name}`.

**Q: Can I modify requirements after starting?**
A: Yes, edit `docs/{task-name}/requirement.md` and run `/task-run {task-name}` again. The developer will see the updated requirements.

**Q: What models can I use?**
A: Sonnet (default, good balance), Opus (highest quality, slower), Haiku (fast, lower cost). Configure in agent frontmatter.

**Q: Does this work with any programming language?**
A: Yes, the plugin is language-agnostic. Specify your tech stack in requirements.

**Q: Can the evaluator write code?**
A: No, the evaluator is explicitly instructed to only test and verify, never to modify code.

**Q: What if I disagree with the evaluation?**
A: Review the eval report in `docs/{task-name}/`, update acceptance criteria if needed, and re-run the task.

## Contributing

This plugin is designed to be extended. You can:

1. **Add new agent types**
   - Create new `.md` files in `agents/`
   - Define specialized roles (e.g., security-reviewer, performance-optimizer)

2. **Customize commands**
   - Edit command files in `commands/`
   - Add new workflows beyond dev-eval loop

3. **Integrate tools**
   - Add MCP servers for specialized testing
   - Connect to CI/CD systems
   - Integrate project management tools

## License

MIT

## Version

1.0.0

## Support

For issues, questions, or feedback:
- Check this README
- Review example tasks in `docs/`
- Examine evaluation reports for debugging
- Modify plugin files to suit your workflow

---

**Happy iterating! Let the agents handle the feedback loop. 🔄**
