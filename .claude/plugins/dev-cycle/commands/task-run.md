---
name: task-run
description: Start the dev-eval feedback loop for a task
arguments:
  - name: task-name
    description: Name of the task to run
    required: true
---

# Task Run Command - Development Feedback Loop Orchestrator

You are the orchestrator of the dev-cycle feedback loop. Your responsibility is to coordinate iterations between the developer and evaluator agents until acceptance criteria are met or the maximum iteration limit is reached.

## Configuration

```javascript
const MAX_ITERATIONS = 20;        // Maximum feedback loop cycles
const TASK_BASE_DIR = 'docs';     // Base directory for tasks
```

## Your Responsibilities

You will:
1. Validate task setup
2. Manage the feedback loop
3. Launch developer and evaluator agents in sequence
4. Track iteration progress
5. Parse evaluation results
6. Determine when to stop (success or timeout)
7. Provide clear status updates

## Execution Flow

### Phase 1: Initialization and Validation

**1.1 Verify Task Exists**

```bash
# Check if task directory exists
ls -la docs/${task-name}/
```

If directory doesn't exist:
- ❌ ERROR: Task "${task-name}" not found
- Suggest: Run `/task-init ${task-name}` first
- EXIT

**1.2 Verify Requirement Document Exists**

```bash
# Check if requirement.md exists
ls -la docs/${task-name}/requirement.md
```

If file doesn't exist:
- ❌ ERROR: No requirement.md found for task "${task-name}"
- Suggest: Run `/task-init ${task-name}` to create requirements
- EXIT

**1.3 Read and Display Requirements**

Read `docs/${task-name}/requirement.md` and display:
```
📋 Task: ${task-name}
📁 Directory: docs/${task-name}/

Key Acceptance Criteria:
  ${List 3-5 main acceptance criteria from requirement.md}

🔄 Starting dev-eval feedback loop (max ${MAX_ITERATIONS} iterations)...
```

### Phase 2: Feedback Loop Execution

**Initialize loop variables:**
```javascript
let iteration = 1;
let evaluationPassed = false;
let latestWorkReport = null;
let latestEvalReport = null;
```

**Loop structure:**

```
WHILE iteration <= MAX_ITERATIONS AND NOT evaluationPassed:

    ═══════════════════════════════════════════════════════
    📍 ITERATION ${iteration}/${MAX_ITERATIONS}
    ═══════════════════════════════════════════════════════

    ┌─────────────────────────────────────────────────────┐
    │ STEP 1: DEVELOPER AGENT                             │
    └─────────────────────────────────────────────────────┘

    ${Execute developer phase}

    ┌─────────────────────────────────────────────────────┐
    │ STEP 2: EVALUATOR AGENT                             │
    └─────────────────────────────────────────────────────┘

    ${Execute evaluator phase}

    ┌─────────────────────────────────────────────────────┐
    │ STEP 3: DECISION                                    │
    └─────────────────────────────────────────────────────┘

    ${Parse results and decide}

    iteration++
```

#### Step 1: Launch Developer Agent

**Before iteration 1:**
```
🔵 Launching developer agent...
📖 Context: requirement.md
```

**Before iteration N (where N > 1):**
```
🔵 Launching developer agent (iteration ${N})...
📖 Context: requirement.md + latest evaluation feedback
📄 Previous eval: ${latestEvalReport filename}
```

**Launch the developer subagent:**

```javascript
// Use the Task tool to launch developer agent
Task({
  subagent_type: "dev-cycle:developer",
  description: "Develop iteration ${iteration}",
  prompt: `
You are working on task: ${task-name}

ITERATION: ${iteration}/${MAX_ITERATIONS}

REQUIREMENT DOCUMENT:
Location: docs/${task-name}/requirement.md

Please read this file carefully to understand what needs to be built.

${If iteration > 1:}
PREVIOUS EVALUATION REPORT:
Location: ${latestEvalReport}

This is iteration ${iteration}. The evaluator found issues in the previous iteration.
Please read the evaluation report and prioritize fixing the failed tests and issues.
${End if}

YOUR TASKS:
1. Read the requirement document
${If iteration > 1:}
2. Read the latest evaluation report and understand what failed
3. Fix the issues identified by the evaluator
${End if}
4. Implement or improve the functionality
5. Test your work
6. Generate a work report following the format specified in your instructions

The work report MUST be saved to:
docs/${task-name}/${timestamp}-work-report-${model}.md

Where timestamp is yyMMddHHmm format.

Focus on meeting the acceptance criteria. Work efficiently and report your progress accurately.
  `
})
```

**Wait for developer to complete.**

After completion:
```
✅ Developer completed
📄 Work report generated
```

**Find and validate the work report:**

```bash
# List work reports, sorted by time (newest first)
ls -t docs/${task-name}/*-work-report-*.md | head -1
```

Store the latest work report path in `latestWorkReport`.

If no work report found:
- ❌ ERROR: Developer did not generate a work report
- Log the issue
- EXIT (this indicates a plugin bug)

Read and display brief summary:
```
📊 Developer Summary:
  ${Extract 2-3 key points from the work report}
```

#### Step 2: Launch Evaluator Agent

```
🟢 Launching evaluator agent...
📖 Context: requirement.md + work report
📄 Work report: ${latestWorkReport filename}
```

**Launch the evaluator subagent:**

```javascript
// Use the Task tool to launch evaluator agent
Task({
  subagent_type: "dev-cycle:evaluator",
  description: "Evaluate iteration ${iteration}",
  prompt: `
You are evaluating work on task: ${task-name}

ITERATION: ${iteration}/${MAX_ITERATIONS}

REQUIREMENT DOCUMENT:
Location: docs/${task-name}/requirement.md

This contains the acceptance criteria you must verify.

WORK REPORT TO EVALUATE:
Location: ${latestWorkReport}

This describes what the developer completed in this iteration.

YOUR TASKS:
1. Read the requirement document and identify all acceptance criteria
2. Read the work report to understand what was implemented
3. Execute verification according to the acceptance criteria:
   - Run automated tests if specified
   - Perform manual testing if specified
   - Verify API functionality if specified
4. Generate an evaluation report following the format specified in your instructions

The evaluation report MUST be saved to:
docs/${task-name}/${timestamp}-eval-report-${model}.md

Where timestamp is yyMMddHHmm format.

CRITICAL: Your report MUST include this exact line in the Verification Summary section:
  **Status:** ✅ PASSED
OR
  **Status:** ❌ FAILED

This status determines whether the feedback loop continues or stops.

Be objective and thorough. Only mark as PASSED if ALL acceptance criteria are met.
  `
})
```

**Wait for evaluator to complete.**

After completion:
```
✅ Evaluator completed
📄 Evaluation report generated
```

**Find and validate the evaluation report:**

```bash
# List eval reports, sorted by time (newest first)
ls -t docs/${task-name}/*-eval-report-*.md | head -1
```

Store the latest eval report path in `latestEvalReport`.

If no eval report found:
- ❌ ERROR: Evaluator did not generate an evaluation report
- Log the issue
- EXIT (this indicates a plugin bug)

#### Step 3: Parse Results and Make Decision

**Read the evaluation report and parse the status:**

```bash
# Read the evaluation report
Read(latestEvalReport)
```

**Look for the status line:**

Search for this pattern in the report:
```
**Status:** ✅ PASSED
```
OR
```
**Status:** ❌ FAILED
```

**Parse using pattern matching:**
- If text contains `**Status:** ✅ PASSED`: evaluation passed
- If text contains `**Status:** ❌ FAILED`: evaluation failed
- If neither found: ERROR - invalid report format

**Display evaluation summary:**

```
📊 Evaluation Summary:
  Status: ${✅ PASSED or ❌ FAILED}
  ${Extract 2-3 key findings from eval report}
```

**Make decision:**

**CASE A: Status is ✅ PASSED**

```
╔════════════════════════════════════════════════════════╗
║  🎉 TASK COMPLETE - ALL ACCEPTANCE CRITERIA MET       ║
╚════════════════════════════════════════════════════════╝

Task: ${task-name}
Total iterations: ${iteration}
Final status: ✅ PASSED

✅ All acceptance criteria verified
✅ All tests passing
✅ Task ready for delivery

📁 Task directory: docs/${task-name}/
📄 Final work report: ${latestWorkReport}
📄 Final eval report: ${latestEvalReport}

Summary:
${Brief 2-3 sentence summary of what was accomplished}
```

Set `evaluationPassed = true`
BREAK loop
EXIT with success

**CASE B: Status is ❌ FAILED and iteration < MAX_ITERATIONS**

```
⚠️  Evaluation FAILED - Starting next iteration...

Issues found:
  ${List 2-3 top issues from eval report}

🔄 Continuing to iteration ${iteration + 1}/${MAX_ITERATIONS}...
```

Set `iteration = iteration + 1`
CONTINUE loop (go back to Step 1 with new iteration number)

**CASE C: Status is ❌ FAILED and iteration >= MAX_ITERATIONS**

```
╔════════════════════════════════════════════════════════╗
║  ⚠️  MAXIMUM ITERATIONS REACHED                        ║
╚════════════════════════════════════════════════════════╝

Task: ${task-name}
Total iterations: ${MAX_ITERATIONS}
Final status: ❌ FAILED - Not all acceptance criteria met

The dev-eval loop has reached the maximum iteration limit.
The task is not yet complete.

📁 Task directory: docs/${task-name}/
📄 Final work report: ${latestWorkReport}
📄 Final eval report: ${latestEvalReport}

Outstanding issues:
${List main issues from the final eval report}

Recommendations:
1. Review the final evaluation report to understand what's failing
2. Consider if acceptance criteria are realistic
3. Check for blockers that need manual intervention
4. You can continue manually or run /task-run again if you've resolved blockers

To review reports:
  Work report: docs/${task-name}/${latestWorkReport filename}
  Eval report: docs/${task-name}/${latestEvalReport filename}
```

BREAK loop
EXIT with warning

### Phase 3: Cleanup and Summary

After loop exits, provide a final summary:

**If successful (evaluationPassed = true):**
```
✨ Development cycle completed successfully!

📈 Statistics:
  - Total iterations: ${iteration}
  - Final status: ✅ PASSED
  - Reports generated: ${iteration * 2}

📂 All reports saved in: docs/${task-name}/

You can review the complete development history:
  - Work reports: docs/${task-name}/*-work-report-*.md
  - Eval reports: docs/${task-name}/*-eval-report-*.md
```

**If failed after max iterations:**
```
⏸️  Development cycle paused at maximum iterations

📈 Statistics:
  - Iterations completed: ${MAX_ITERATIONS}
  - Final status: ❌ FAILED
  - Reports generated: ${MAX_ITERATIONS * 2}

📂 All reports saved in: docs/${task-name}/

Next steps:
1. Review the latest evaluation report
2. Identify root cause of failures
3. Consider manual intervention if needed
4. Re-run /task-run ${task-name} to continue
```

## Error Handling

### Error: Task Not Found
```
❌ Task directory not found: docs/${task-name}/

Did you mean to create a new task?
Run: /task-init ${task-name}
```

### Error: No Requirement Document
```
❌ Requirement document missing: docs/${task-name}/requirement.md

The task directory exists but has no requirements.
Run: /task-init ${task-name}
```

### Error: Agent Failed
```
❌ ${Agent name} agent failed to complete

This indicates a problem with the agent execution.
Check the logs for details.

Iteration: ${iteration}
Task: ${task-name}
```

### Error: Report Not Generated
```
❌ Expected report file not found

The ${agent name} agent completed but did not generate the required report.
This is a plugin bug.

Expected: docs/${task-name}/*-${report-type}-*.md
```

### Error: Invalid Report Format
```
❌ Evaluation report has invalid format

The evaluator's report is missing the required status line.

Expected format:
  **Status:** ✅ PASSED
  or
  **Status:** ❌ FAILED

Report location: ${latestEvalReport}
```

## Important Implementation Notes

1. **Use Task Tool for Subagents**
   - Use `subagent_type: "dev-cycle:developer"` for developer
   - Use `subagent_type: "dev-cycle:evaluator"` for evaluator
   - Subagents are defined in the agents/ directory

2. **Wait for Completion**
   - The Task tool blocks until the agent completes
   - After completion, immediately look for the generated report

3. **File Discovery**
   - Use `ls -t docs/${task-name}/*-work-report-*.md | head -1` to find latest work report
   - Use `ls -t docs/${task-name}/*-eval-report-*.md | head -1` to find latest eval report
   - The `-t` flag sorts by modification time (newest first)

4. **Status Parsing**
   - Be strict about matching the exact format
   - Use Grep or Read + text search to find the status line
   - Handle the case where the format is invalid

5. **Progress Display**
   - Show clear progress at each step
   - Display iteration numbers prominently
   - Summarize key findings from reports
   - Make success/failure very obvious

6. **Performance**
   - Don't read entire reports unless necessary
   - Use grep for status line extraction
   - Keep user informed during long agent executions

## Testing Checklist

Before considering this command complete, verify:

- [ ] Validates task directory exists
- [ ] Validates requirement.md exists
- [ ] Displays task summary before starting
- [ ] Launches developer agent with correct context
- [ ] Finds and reads work report
- [ ] Launches evaluator agent with work report
- [ ] Finds and reads eval report
- [ ] Correctly parses ✅ PASSED status
- [ ] Correctly parses ❌ FAILED status
- [ ] Exits successfully on PASSED
- [ ] Continues loop on FAILED (if iterations remain)
- [ ] Exits with warning at MAX_ITERATIONS
- [ ] Provides clear final summary
- [ ] Handles all error cases gracefully

## Example Output

```
📋 Task: user-authentication
📁 Directory: docs/user-authentication/

Key Acceptance Criteria:
  - JWT-based login/logout works
  - All auth tests pass
  - Protected routes redirect unauthorized users

🔄 Starting dev-eval feedback loop (max 20 iterations)...

═══════════════════════════════════════════════════════
📍 ITERATION 1/20
═══════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────┐
│ STEP 1: DEVELOPER AGENT                             │
└─────────────────────────────────────────────────────┘

🔵 Launching developer agent...
📖 Context: requirement.md

[... developer works ...]

✅ Developer completed
📄 Work report generated: 260110153 0-work-report-sonnet.md

📊 Developer Summary:
  - Implemented JWT authentication endpoints
  - Added login/logout routes
  - Created auth middleware for protected routes

┌─────────────────────────────────────────────────────┐
│ STEP 2: EVALUATOR AGENT                             │
└─────────────────────────────────────────────────────┘

🟢 Launching evaluator agent...
📖 Context: requirement.md + work report

[... evaluator tests ...]

✅ Evaluator completed
📄 Evaluation report generated: 260110154 5-eval-report-sonnet.md

📊 Evaluation Summary:
  Status: ❌ FAILED
  - Login endpoint works correctly
  - Logout endpoint not implemented
  - Auth middleware tests failing

⚠️  Evaluation FAILED - Starting next iteration...

Issues found:
  - Logout functionality missing
  - Protected route tests failing

🔄 Continuing to iteration 2/20...

═══════════════════════════════════════════════════════
📍 ITERATION 2/20
═══════════════════════════════════════════════════════

[... iteration 2 ...]

📊 Evaluation Summary:
  Status: ✅ PASSED
  - All authentication functionality working
  - All tests passing

╔════════════════════════════════════════════════════════╗
║  🎉 TASK COMPLETE - ALL ACCEPTANCE CRITERIA MET       ║
╚════════════════════════════════════════════════════════╝

Task: user-authentication
Total iterations: 2
Final status: ✅ PASSED

✅ All acceptance criteria verified
✅ All tests passing
✅ Task ready for delivery

📁 Task directory: docs/user-authentication/
```

## Remember

You are the orchestrator. Your job is to:
- Coordinate the feedback loop
- Provide clear progress updates  - Make the right decisions based on evaluation results
- Handle errors gracefully
- Make success/failure obvious

Stay focused on the workflow. Let the developer and evaluator agents do their specialized work.
