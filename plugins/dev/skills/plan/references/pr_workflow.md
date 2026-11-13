# Plan conventions for a git-branch + PR workflow

Read this when the project uses feature branches and pull requests. It layers naming and lifecycle conventions on top of the base skill. Ignore it entirely for projects without that workflow; the plan is still a valid standalone design doc.

## Slug ↔ branch

Match the plan slug to the branch's feature slug so the two are easy to associate:

- branch `feat/token-cache` ↔ `plans/plan_token_cache.md`

Branch prefixes (`feat/`, `fix/`) and kebab-vs-snake case differences are expected; only the root slug needs to agree.

## The plan grounds the PR

The plan is the design artifact behind the PR. Reference the plan file from the PR description so reviewers can see the intended design, and keep the plan and the PR in sync while the branch is open.

## Lifecycle after merge

After the PR merges, add `Status: implemented in #<PR>` at the top of the plan (under the H1). Keep the plan in the repo as a historical record of design intent. Do not delete it, do not maintain it. Once marked implemented, the plan is frozen; the codebase is the source of truth from that point on.
