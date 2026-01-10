# Agile Dev Plugin

> Agile development toolkit for Claude Code with automated workflows, quality assurance, and code review

## Overview

The **agile-dev** plugin provides a comprehensive suite of tools to streamline your development workflow:

- **Automated Dev-Eval Loop**: Continuous iteration until acceptance criteria are met
- **Code Review**: AI-powered code review with actionable feedback
- **Quality Assurance**: Systematic testing and validation
- **Playwright Tools**: Browser automation and authentication management

## Components

### 1. Dev-Eval Loop (`/task-init` + `/task-run`)

Automated feedback loop where developer and evaluator agents iterate until all requirements are satisfied.

**Workflow:**
```
/task-init my-feature  →  Define requirements & acceptance criteria
          ↓
/task-run my-feature   →  Start automated iteration
          ↓
    [Developer Agent]  →  Implement features
          ↓
    [Evaluator Agent]  →  Test & verify
          ↓
    Pass? ✅ Done      →  Fail? ❌ Next iteration (max 20 cycles)
```

**When to use:**
- New features with clear acceptance criteria
- Bug fixes requiring verification
- Tasks needing iteration to perfect

### 2. Code Review (`reviewer` agent)

AI code reviewer that analyzes changes and provides constructive feedback.

**Usage:**
```bash
# Review current changes
claude "Use the reviewer agent to review my latest changes"

# Review specific files
claude "Use the reviewer agent to review src/auth.ts"
```

**Review categories:**
- 🔴 Critical: Bugs, security issues, breaking changes
- 🟡 Important: Design flaws, performance issues, missing tests
- 🔵 Minor: Improvements, suggestions, style

### 3. Playwright Auth Manager (Skill)

Manage authentication states for Playwright browser tests across multiple user roles.

**Features:**
- Create/manage auth states for different user types
- Reuse authenticated sessions across tests
- Multi-user test scenarios

## Quick Start

### Installation

```bash
# Clone to Claude plugins directory
cd ~/.claude/plugins
git clone <repo-url> agile-dev

# Or create symlink for development
ln -s /path/to/agile-dev ~/.claude/plugins/agile-dev
```

### Basic Usage

#### Create and Run a Task

```bash
# 1. Initialize task with requirements
/task-init user-login

# Claude asks:
# - What's the goal?
# - Tech stack?
# - Acceptance criteria?

# 2. Run automated dev-eval loop
/task-run user-login

# Agents iterate automatically until:
# ✅ All criteria pass → Success
# ⚠️ 20 iterations → Manual review needed
```

#### Review Code Changes

```bash
# Review uncommitted changes
claude "Use reviewer agent to review my changes"

# Review specific branch
claude "Use reviewer agent to review feature-branch compared to main"
```

## File Structure

In your working directory, the plugin creates a `docs/` folder to store task-related documents:

```
docs/
└── {task-name}/
    ├── requirement.md           # Requirements & acceptance criteria
    ├── *-work-report-*.md       # Developer iteration reports
    └── *-eval-report-*.md       # Evaluator test reports
```

## Detailed Guide

### Writing Effective Requirements

#### Good Acceptance Criteria (Specific & Testable)
```markdown
- [ ] User can login with email/password
- [ ] JWT token returned on successful auth
- [ ] All tests pass: `npm test auth`
- [ ] Protected routes redirect when unauthenticated
- [ ] No console errors during auth flow
```

#### Bad Acceptance Criteria (Vague)
```markdown
- [ ] Authentication works
- [ ] Should be secure
- [ ] Tests pass
```

### Dev-Eval Loop Best Practices

**1. Start with clear requirements**
- Define measurable acceptance criteria
- Include test commands that can be run
- Specify expected behavior for edge cases

**2. Let agents iterate**
- Don't interrupt the loop prematurely
- Review reports to understand progress
- Trust the process for 3-5 iterations

**3. Intervene when needed**
- Review evaluation reports if stuck
- Manually fix architectural blockers
- Adjust unrealistic acceptance criteria

**4. Resume after changes**
```bash
# Edit code or requirements manually
vim docs/my-task/requirement.md

# Resume iteration
/task-run my-task
```

### Code Review Best Practices

**Request specific reviews:**
```bash
# Review security
claude "Use reviewer to check for security vulnerabilities in auth module"

# Review performance
claude "Use reviewer to analyze performance of data processing code"

# Review tests
claude "Use reviewer to verify test coverage is sufficient"
```

**Act on feedback:**
- Address 🔴 Critical issues immediately
- Plan fixes for 🟡 Important issues
- Consider 🔵 Minor suggestions

## Configuration

### Maximum Iterations

Edit `commands/task-run.md`:
```javascript
const MAX_ITERATIONS = 30;  // Default: 20
```

### Task Directory

Edit `commands/task-run.md`:
```javascript
const TASK_BASE_DIR = 'tasks';  // Default: 'docs'
```

### Agent Models

Edit agent frontmatter in `agents/*.md`:
```yaml
---
name: developer
model: opus  # Options: sonnet, opus, haiku
---
```

## Troubleshooting

### Task Issues

**Error: Task directory not found**
```bash
# Solution: Initialize the task first
/task-init {task-name}
```

**Error: Infinite loop - keeps failing**
- Review latest evaluation report
- Check if acceptance criteria are achievable
- Verify test commands work
- Manually fix blocking issues
- Update requirements if needed

**Error: Evaluation passes too easily**
- Make acceptance criteria more specific
- Add explicit test commands
- Include negative test cases
- Specify quality thresholds

### Review Issues

**Review too shallow**
- Provide more context about what to focus on
- Specify areas of concern (security, performance, etc.)
- Point to specific files or functions

**Review too nitpicky**
- Reviewers are trained to avoid style nitpicks
- Focus on logic, security, and maintainability
- Use linters for formatting issues

## Advanced Usage

### Custom Testing Strategies

**Playwright E2E Testing:**
```markdown
## Acceptance Criteria
- [ ] Playwright tests pass: `npx playwright test`
- [ ] User flow works: login → dashboard → logout
- [ ] No browser console errors
```

**API Testing:**
```markdown
## Acceptance Criteria
- [ ] GET /api/users returns 200
- [ ] POST /api/users creates user (201)
- [ ] Invalid input returns 400
- [ ] API tests pass: `npm run test:api`
```

**Performance Testing:**
```markdown
## Acceptance Criteria
- [ ] Page load < 2 seconds
- [ ] API response < 200ms
- [ ] Lighthouse score > 90
```

### Multi-Task Workflows

Run tasks in parallel (separate terminals):
```bash
# Terminal 1
/task-run feature-a

# Terminal 2
/task-run feature-b
```

Each task maintains independent state.

### Extending the Plugin

**Add new agents:**
1. Create `agents/your-agent.md`
2. Define role, responsibilities, and tools
3. Use in workflows

**Add new commands:**
1. Create `commands/your-command.md`
2. Define workflow and logic
3. Invoke with `/your-command`

**Add new skills:**
1. Create `skills/your-skill/`
2. Add SKILL.md and references
3. Use in agent prompts

## FAQ

**Q: How many iterations typically needed?**
A: 2-5 for most tasks. Simple tasks: 1. Complex tasks: 10-15.

**Q: Can I stop mid-iteration?**
A: Yes, Ctrl+C to interrupt. Reports saved. Resume with `/task-run {task}`.

**Q: Can I modify requirements after starting?**
A: Yes, edit `requirement.md` and re-run `/task-run {task}`.

**Q: What models should I use?**
A: Sonnet (balanced), Opus (highest quality), Haiku (fast/cheap).

**Q: Does reviewer actually write code?**
A: No, reviewer only analyzes and suggests. Never modifies code.

**Q: Can I use this with any language?**
A: Yes, plugin is language-agnostic.

## License

MIT

## Version

1.0.0

---

**Build better, iterate faster. Let the agents handle the loop. 🔄**
