# Agent Pipeline: Hardware Hub

Copy the four `.md` agent files into `.claude/agents/` in the project repo.

## The chain

```
STAGE 0   /grill-me                 YOU, main thread, never delegated
STAGE 1   project-architect         agent, once      → PROJECT_SPEC.md
  │
  ├─ per MVP ──────────────────────────────────────────────────────────
  │
STAGE 2   /grill-me → /to-spec      YOU + skill      → docs/specs/mvp-N.md
STAGE 3   test-author               agent            → failing tests (red)
STAGE 4   /implement (drives /tdd)  main thread      → green
STAGE 5   architecture-scout        agent, read-only → ranked report
STAGE 6   mvp-reviewer              agent, read-only → docs/reviews/REVIEW_mvp-N.md
STAGE 7   HUMAN GATE                YOU              → approve, merge, tag
```

## Two rules that make it work

**1. Every handoff is a file.** Agents share no memory. A handoff that exists only
in conversation is a handoff that was dropped. Each stage reads a file and writes
a file, which is why every agent above names its input and output explicitly.

**2. Authorship and verification never share a context.** `test-author` cannot
write `src/`. The implementer cannot edit `tests/`. `architecture-scout` and
`mvp-reviewer` have no Write tool at all. That separation is the entire point:
without it you have one agent grading its own homework in four costumes.

> The `src/` vs `tests/` split is enforced by instruction, not by the tool layer.
> Verify it at the review gate: `git diff --stat` between the test commit and the
> feature commit makes a violation obvious at a glance.

## What is deliberately NOT an agent

- **Grilling**: needs a human with opinions. A subagent interviewing itself
  reaches the conclusion it already held.
- **The AI log**: per commit, by you. Batched at the end by an agent, it reads
  exactly like it was batched at the end by an agent, which is the specific thing
  Booksy is scanning for.
- **The gate**: the human decision this whole structure exists to protect.

## Skills at each stage

| Stage | Skill |
|---|---|
| 0, 2 | `/grill-me`, `/to-spec` |
| 3–4 | `/tdd`, `/implement` |
| 5 | `/improve-codebase-architecture` |
| 6 | `/code-review` |
| any | `/handoff` when a session runs long, `/diagnosing-bugs` when stuck |

## Cost note

Four opus agents per MVP across six MVPs is not cheap, and each one starts cold.
If you need to economise, `test-author` and `mvp-reviewer` are the two that earn
their keep: they are the genuine authorship/verification splits. `architecture-scout`
can be replaced by invoking `/improve-codebase-architecture` in the main thread,
and `project-architect` runs only once anyway.
