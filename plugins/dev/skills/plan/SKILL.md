---
name: plan
description: "Creates implementation plans for software features, saved to plans/plan_*.md. TRIGGER when: user asks to plan a feature, write an implementation plan, design before coding, or mentions plans/plan_*.md."
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Plan

Creates an implementation plan for a software feature as a markdown document under `plans/plan_<feature>.md`. The plan captures the design *before* code is written, so it can be reviewed and used to guide implementation.

If the project uses feature branches and pull requests, also read `references/pr_workflow.md` for the branch↔slug naming and post-merge lifecycle conventions. Skip it for projects without that workflow; the plan stands on its own.

## When to use

- User asks to plan, design, or scope a feature before implementing it.
- User references `plans/plan_*.md` or wants to update an existing plan.
- A non-trivial change is requested with no existing plan: propose creating one first.

Skip the skill for straightforward edits, bug fixes, or anything that fits in a single short PR without design discussion.

## Output

A single markdown file at `plans/plan_<feature>.md` (snake_case, no date prefix). The `<feature>` slug is a short, descriptive name for the feature. Iterate on the file in place. Do not create new versions or rename it as the design evolves. (In a branch/PR workflow, align the slug with the branch; see `references/pr_workflow.md`.)

## Plan structure

Use these sections, in this order. Omit a section only when it is genuinely not applicable.

- **Title** (H1): clear and concise.
- **Summary**: the first section of every plan. States the problem being solved, in plain English, for someone who has never seen this conversation, this repo, or this bug before. Two short paragraphs at most, ideally one. It must answer three things: what is wrong or missing today, who or what it affects, and what is true once the plan is implemented. That last sentence is the plan's goal. There is no separate Goal section, because two sections stating the same outcome drift apart as the design changes. Write it so it stands alone (see **Writing the Summary** below).
- **References**: orientation pointers, not detailed code citations. List relevant docs (whole files or specific sections), package READMEs, the key modules/files involved (paths only, no line numbers), external links. Detailed file:line citations belong in **Implementation details**. (This is a section *inside* the plan, not the skill's own `references/` directory.)
- **Requirements**: one per line, each stating *what* is required and *why*.
- **Out of scope** *(optional)*: one per line, each stating what the plan intentionally does *not* cover and why (deferred, handled elsewhere, explicitly rejected). Include only when readers are likely to assume coverage that isn't there.
- **Constraints**: one per line, with file/doc references where applicable.
- **High-level design**: a few paragraphs covering key components and their interactions; add a numbered workflow if it clarifies.
- **Implementation details**: specific technologies, APIs, data structures, algorithms, and the concrete file paths (with line numbers when helpful) where each change lands; detailed enough to guide implementation. Describe behavior in prose; include a short code snippet only when prose is genuinely unclear.
- **Testing**: what needs verification, namely the key behaviors and edge cases to cover, the test type (unit / integration / eval), and where tests should live. Skip only for trivial changes with no meaningful behavior to verify. Include these reminders for the implementer (who will execute **Test steps**):
  - Follow the project's existing testing conventions: match the framework, layout, and style of the tests already in the repo.
  - Never mock. Two reasons: a test that needs mocking is usually telling you the design is wrong, and the mock bypasses the very code under test, so you end up testing the mocking library. Use real objects, or real fakes written for the project (an in-repo fake client/adapter for a specific dependency). Generic mocking/patching libraries (`unittest.mock`, `pytest-mock`, `sinon`, `jest.mock`) are off limits. When a test appears to need one, treat that as a finding about the design and say so; only the user can waive the rule, and they have to be asked explicitly.
  - Test meaningful behavior only. No tautological tests, no tests of trivial getters/setters, no padding for coverage.
- **Documentation updates**: bullet list of docs and package READMEs that need to be created or updated, each with a one-line note on what changes. Omit only if the feature is genuinely not user- or developer-facing.
- **Implementation steps**: ordered checklist of code changes that realize the design from **Implementation details**. One task per line. Open the section with this preamble (verbatim) so the implementer can run unattended:

  > **For the implementer:** Work autonomously end-to-end. Do not pause to ask for permission to run shell commands during the writing phase; assume any such request will be denied. Complete **Implementation steps**, **Test steps**, and **Documentation updates** by editing files only. Once everything is written, run **Verification steps** yourself in one batch at the end.
- **Test steps**: ordered checklist for writing the tests per **Testing**. One test case per line.
- **Verification steps**: how to confirm the feature works after implementation and tests are in place. Standard order:
  1. Lint / format using the project's configured tooling.
  2. Run the new tests.
  3. Run the full unit test suite.
  4. Manual / human verification when warranted: exercise the feature end-to-end and confirm it behaves correctly. Spell out the specific scenarios to try (what input, what to run, what to look for). Skip only when the feature has no user-visible surface, or is fully covered by the test cases above.

## Writing the Summary

The reader of the Summary is an independent, competent engineer who was not in the room. Assume they know nothing beyond general software knowledge.

Do:
- Name the concrete problem. What breaks, what is missing, what is slow, what is wrong.
- Spell out anything that was context in the conversation: a failing test, an observed runtime error, a customer complaint, a limitation someone hit. State the fact itself, not a reference to it.
- Expand names on first use: repo-internal components, scripts, flags, jargon. One clause of explanation is enough.
- Say what the situation is after the plan is implemented.
- Keep it short. A few sentences that a reader actually understands beat a page they skim.

Do not:
- Assume shared memory. No "the failure we saw earlier", "the issue from the ticket", "as discussed", "the current approach".
- Use marketing, click-bait, or consultant phrasing. No "unlocks", "seamless", "step change", "at scale", "leverage", "journey", "robust", "best-in-class", "game-changer".
- Dress a plain statement up as a metaphor. No "the gate", "load-bearing", "the wedge", "the hot path", "north star", "flywheel", "moat", "table stakes", "forcing function", "surface area", "first-class citizen", "source of truth" used figuratively. If the sentence means "this check rejects bad input" or "everything else depends on this file", write that.
- Reach for analogies. Describe the system, not something it resembles.
- Overstate. No claims about impact that the plan does not support.
- Restate the section as a list of tasks. Implementation belongs further down.

Check before moving on: re-read the Summary as if the rest of the plan, this conversation, and the repo did not exist. If any sentence only makes sense with that context, rewrite it.

Example (good):

> `edgar pull` downloads SEC filings into a local SQLite catalog. When the same filing is fetched twice (which happens whenever a poll overlaps a previous run), the second fetch inserts a duplicate row instead of replacing the first. Duplicates then show up as repeated findings in the review loop, and there is no way to tell which copy is current. This plan makes the fetch stage upsert on the filing's accession number, so a filing appears exactly once in the catalog.

Example (bad, and why):

> Building on our earlier discussion, this plan addresses the duplicate-row issue in the pull pipeline and unlocks a more robust ingestion story at scale.

Assumes the reader was in the earlier discussion, never says what the duplicate-row issue actually is, and pads the rest with marketing words.

## A plan is finished or it is not

A plan that still contains "TBD", "to be decided", "open question", "we could either X or Y", or any choice left to the reader is not a finished plan. Do not hand one over and do not call it done.

- **Resolve questions yourself, from first principles.** Read the code, read the docs, weigh the options, pick one, and write down why. A decision you can defend beats a question you left open.
- **Do not ask the user what you can answer.** If the answer is in the request, in the plan's own title or Summary, in the repo, or one `grep` away, go find it. Asking a question whose answer is already written is worse than not asking.
- **Ask only for what is genuinely the user's.** A product or priority call, a tradeoff with no technical winner where the two outcomes differ for the user, an external constraint you cannot see, or access you do not have. Ask once, briefly, with a recommendation, then write the answer into the plan as a decision.
- **Every decision states its reason.** Write "we do X, because Y", not "we do X". Record the rejected alternative when the rejection is not self-evident. A decision without a reason gets re-argued by the next person who reads it, or quietly reversed during implementation.

Example of a decision written properly:

> Tests run against a real SQLite file in a temp directory, not a mocked DB connection, because mocking the connection would test the mock rather than the query, and it would not catch the schema errors this change is most likely to introduce.

## Workflow

The plan is built iteratively. Save / update the file at every step. Do not hold the plan in conversation context only.

1. **Skeleton**: write the **Summary** first (the problem in plain English, self-contained, ending with what is true once the plan is implemented), per **Writing the Summary**. Then capture any stated requirements. Write `plans/plan_<feature>.md` with placeholders for the remaining sections, then save it.
2. **Refine requirements**: answer the open questions yourself from the request, the repo, and the docs. Ask the user only what is genuinely theirs to decide (see **A plan is finished or it is not**), no more than four questions, each with a recommendation. Write the answers into the plan as decisions with reasons.
3. **Gather references**: start from the repo's `README.md`, follow into the relevant docs and package READMEs, identify the code files involved. Add findings under **References**.
4. **Extract constraints**: pull the technical facts and constraints implied by the references into **Constraints**, citing the source.
5. **Draft the high-level design**: propose a design grounded in the requirements and constraints. When iterating with the user, keep messages tight (under half a terminal screen, preferably less). Update the plan once the design stabilizes.
6. **Break down implementation details**: once the design is stable, fill in the detailed mechanics.
7. **Testing strategy**: fill in **Testing** with the key behaviors and edge cases to cover, the test type (unit / integration / eval), where tests should live, and the implementer reminders verbatim from the **Testing** spec above (follow existing test conventions; never mock, and why; no useless tests).
8. **Documentation updates**: list the docs and package READMEs that need to be created or updated, each with a one-line note on what changes.
9. **Execution checklists**: build the three checklists, **Implementation steps** (code changes; open with the verbatim implementer preamble from the Plan structure spec), **Test steps** (tests to write), **Verification steps** (lint, run new tests, run all unit tests, manual checks if needed).
10. **Review**: re-read the **Summary** first and check it still describes the problem the rest of the plan solves, with no assumed context. Then search the plan for leftover open items ("TBD", "either/or", unanswered questions, decisions stated without a reason) and close every one of them. Then re-read the referenced docs, the relevant code (including any existing tests the new ones will live alongside), and the full plan end-to-end. Verify it is technically solid, free of gaps, and succinct. Surface issues to the user briefly, fix them, update the plan. Repeat until the plan is solid.

## Rules

- Every plan opens with a **Summary** that states the problem in plain English and assumes no prior knowledge: no conversation history, no ticket, no remembered test failure.
- A plan is finished or it is not. No TBDs, no open questions, no choices left to the reader. Resolve them from first principles and record the reason.
- Every decision in the plan carries its reason: "X, because Y".
- Save the file at step 1; update it in place as the design evolves.
- Be clear, succinct, and to the point: no fluff, no marketing language.
- No emojis and no em-dashes in the plan file. Where an em-dash would go, use a colon, a comma, parentheses, or a new sentence.
- Solid engineering: attend to edge cases and pitfalls, but do not over-engineer or design for hypothetical future requirements.
- A plan describes design, not code. Avoid code blocks; include a short snippet (a few lines) only when prose cannot convey the API shape or data structure clearly. Function bodies, full classes, and pasted implementations do not belong in a plan.
- No diagrams or visuals unless they are genuinely useful for understanding the design.
- During iteration, keep user-facing messages brief: half a terminal screen or less.
- When direction changes mid-conversation, update the plan, not just the conversation. The implementer reads the plan and nothing else.
- Do not implement the feature from this skill. Planning ends with a complete `plan_*.md`; coding is a separate step.
