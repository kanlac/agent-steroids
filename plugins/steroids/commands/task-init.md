---
name: task-init
description: Create a new task directory and write requirement document
arguments:
  - name: task-name
    description: Name of the task/feature to implement
    required: true
---

# Task Initialization Command

You are helping the user create a new development task with comprehensive requirements.

## Your Responsibilities

1. **Create Task Directory Structure**
   - Create directory: `docs/${task-name}/`
   - Verify the directory doesn't already exist
   - If it exists, ask the user if they want to overwrite or use a different name

2. **Gather Requirements Interactively**

   Use the AskUserQuestion tool to collect the following information. Ask questions progressively, building on previous answers:

   **First Round - Core Information:**
   - What is the main goal or purpose of this task?
   - What problem does it solve?
   - Who is the target user or beneficiary?

   **Second Round - Technical Details:**
   - What technology stack will be used? (languages, frameworks, libraries)
   - Are there any existing systems this needs to integrate with?
   - Any specific architectural patterns or constraints?

   **Third Round - Acceptance Criteria (MANDATORY):**
   - How will you know when this task is complete?
   - What specific functionality must work?
   - What tests need to pass? (Playwright tests, unit tests, API tests, manual validation steps)
   - Are there any performance or quality requirements?

   **CRITICAL**: The acceptance criteria MUST be:
   - Specific and measurable
   - Testable (either automated or with clear manual steps)
   - Complete (covering all major functionality)

   If the user provides vague criteria, ask clarifying questions until you have concrete, verifiable acceptance criteria.

3. **Generate requirement.md File**

   After gathering all information, create a well-structured `docs/${task-name}/requirement.md` file with the following format:

```markdown
# ${Task Name}

**Created:** ${current-date}
**Status:** Planning

## Overview

${Brief summary of the task and its purpose}

## Problem Statement

${Description of the problem this task solves}

## Target Users

${Who will benefit from this task}

## Functional Requirements

${Detailed description of what needs to be built}

### Core Features

- ${Feature 1}
- ${Feature 2}
- ${Feature 3}

### Technical Stack

- **Languages:** ${languages}
- **Frameworks:** ${frameworks}
- **Libraries:** ${libraries}
- **Integration Points:** ${integrations}

## Acceptance Criteria

**IMPORTANT:** All criteria below must be satisfied for this task to be considered complete.

### Functional Acceptance

- [ ] ${Criterion 1 - specific functionality that must work}
- [ ] ${Criterion 2 - specific functionality that must work}
- [ ] ${Criterion 3 - specific functionality that must work}

### Test Acceptance

${Choose appropriate testing approach:}

**Option A: Automated Testing**
- [ ] All Playwright E2E tests pass: `${test-command}`
- [ ] All unit tests pass: `${test-command}`
- [ ] Code coverage meets ${X}% threshold

**Option B: Manual Testing**
- [ ] ${Manual test step 1 with expected result}
- [ ] ${Manual test step 2 with expected result}
- [ ] ${Manual test step 3 with expected result}

**Option C: API Testing**
- [ ] ${API endpoint 1} returns ${expected result}
- [ ] ${API endpoint 2} returns ${expected result}
- [ ] Error cases handled correctly

### Quality Acceptance

- [ ] Code follows project style guidelines
- [ ] No console errors or warnings
- [ ] Performance meets requirements (if applicable)
- [ ] Documentation updated (if applicable)

## Open Questions

${List any questions or concerns that need clarification}

## Out of Scope

${Explicitly state what is NOT included in this task}

## Notes

${Any additional context, constraints, or considerations}
```

4. **Confirm and Finalize**

   After creating the file:
   - Display the path to the created file
   - Summarize the key acceptance criteria
   - Confirm the user can now run `/task-run ${task-name}` to start the development cycle

## Important Guidelines

- **Be thorough**: Don't rush through requirements gathering. Ask follow-up questions if answers are vague.
- **Validate acceptance criteria**: Ensure they are concrete and testable. If not, ask clarifying questions.
- **Document everything**: Capture all relevant information in the requirement.md file.
- **Set clear expectations**: Make sure the user understands what "done" means for this task.

## Example Interaction Flow

```
User: /task-init user-authentication

You: I'll help you create the task requirements. Let me start by understanding the core goals.

[Ask questions about goals, problem, users]
[Ask questions about technical details]
[Ask questions about acceptance criteria - probe until specific]

You: Thank you! I've gathered all the information. Let me create the requirement document.

[Create docs/user-authentication/requirement.md]

You: ✅ Task initialized successfully!

📁 Requirement document created: docs/user-authentication/requirement.md

📋 Key Acceptance Criteria:
   - JWT-based login/logout functionality works
   - All auth tests pass: npm test auth
   - Protected routes redirect unauthorized users

Next step: Run `/task-run user-authentication` to start the development cycle.
```

## Error Handling

- If `docs/` directory doesn't exist, create it
- If task directory already exists, ask before overwriting
- If acceptance criteria are insufficient, keep asking until they're concrete
- If user wants to skip acceptance criteria, explain why they're mandatory
