# Memory Philosophy — where each piece of memory should live

Read this before making judgment calls about what to keep, move, or cut. The scoring and the report are downstream of this taste; if the taste is wrong, the numbers are theater.

## The frame: push vs pull

Two layers, opposite failure modes.

**预置记忆 (push)** is loaded into context every session — global and project `CLAUDE.md` / `AGENTS.md`, native auto-memory. It is the most expensive real estate the agent owns, because it pays rent on *every* turn. Past a budget the harness silently drops the tail, so an overfed push layer doesn't just waste tokens — it stops loading and quietly steers nothing while making everything around it noisier. More push is not more knowledge; it is less adherence. **Push must be scarce.**

**外部记忆 (pull)** is retrieved only when the agent asks for it — skill bodies, docs, a queryable store. It can grow without taxing every turn, so its enemy is not size but decay: it goes stale, loses its links, and contradicts itself silently. **Pull must stay findable and honest.**

"Delete your memory" and "give your agent a real memory" stop being opposites once you separate these two. You cut push hard *and* you let pull accrete — as long as pull stays disciplined.

## The routing question

For any lesson, fact, or note, ask **where should this live** — not "should I keep a memory of it." Four homes:

- **Nowhere (delete)** — git history, shipped PRs, finished trackers, anything already encoded in tooling. If the record exists elsewhere, keeping a copy in memory is pure tax.
- **A skill (as an improvement)** — a lesson tied to one tool or workflow belongs *inside that skill*, where it changes behavior every time the skill runs and is version-controlled like code. A skill-specific lesson parked in global push is misfiled: it taxes every session yet only matters in one narrow context. This is the single most common defect.
- **Push (kept)** — only what is *both* cross-cutting *and* decision-changing *and* true in (almost) every session: identity, hard safety rails learned the hard way, a handful of canonical paths, rules that govern everything the agent writes. The bar is brutal. A good global file is short by design.
- **Pull (kept, but honest)** — reference knowledge that matters sometimes, retrieved on demand. Fine to grow; must stay linked and current.

## The bar for a push line

Every line in the always-on layer earns its slot or gets cut. The test is simple: **does this line change what the agent does next?** If the model could infer it from the repo (tech stack, obvious conventions), if it's generic advice ("write clean code"), or if it's too vague to act on ("handle edge cases"), it changes nothing and only dilutes the lines that do. The cut list is almost always longer than the keep list. Pay for signal, not square footage.

Prefer one instruction file over two that drift. A project `CLAUDE.md` that just imports `@AGENTS.md` (or is a symlink to it) keeps conventions written once and read by every agent, instead of two files that disagree by Tuesday.

## When NOT to record

The clinic's taste includes restraint. Do not manufacture memory:

- Do not add a push line for something the agent already does correctly, or can infer.
- Do not create a doc/page for a passing mention — only for knowledge that would be painful to re-derive.
- When a lesson is genuinely skill-specific, the right move is to improve the skill, not to also leave a memory breadcrumb. Two copies drift.
- A borderline "might be useful someday" note is a liability, not an asset. Enforced scarcity is what makes the remaining lines trustworthy.

## Refactor, don't append (the skill-improvement craft)

When a lesson does belong in a skill, the good version rewrites the skill so it reads clearer — a sharper trigger, a routing rule, a negative example, a tighter checklist — rather than stapling a raw note to the end. The measure of a good learning is that the skill got *easier to execute*, not longer. This is `meta-learning`'s domain; lean on it for the actual rewrite.

## Pull is not a license to hoard

Moving recall into a queryable store does not exempt it from discipline. Retrieval memory still goes stale, still fills with things that mattered once, still rewards pruning. Keep the pull layer as honest as the push layer — the difference is that pull earns its scarcity through periodic cleanup rather than a per-session budget.

## Diagnostic consequences

This taste is what the four dimensions measure:

- **体量** enforces push scarcity (and per-file size on pull).
- **可用性** enforces the "does it change a decision" bar.
- **新鲜度** catches pull decay and dead push facts.
- **矛盾** catches the drift that happens when the same decision is written in two places.

And it is what the prescription acts on: delete the misfiled, move the skill-specific into skills, keep the rare cross-cutting truth, reconcile the contradictions.
