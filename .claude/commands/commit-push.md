---
description: Commit all current changes with a short English message and push to the default branch
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git add:*), Bash(git commit:*), Bash(git push:*), Bash(git branch:*), Bash(git symbolic-ref:*), Bash(git rev-parse:*)
---

## Context

- Status: !`git status --short`
- Diff summary: !`git diff HEAD --stat`
- Current branch: !`git branch --show-current`
- Default branch: !`git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main`
- Recent commits (style reference): !`git log --oneline -5`

## Task

Commit the current changes and push them to the default branch.

1. If there are no changes, say so and stop.
2. Read the diff if the stat is not enough to understand the change.
3. Do not stage secrets (`.env*` except `.env.example`, credentials, keys). If any are present, leave them out and say so.
4. Stage the changes and commit with a message that is:
   - **English**, imperative mood ("Add", "Fix", "Remove"), e.g. `Fix SDK install URL`
   - **One line, at most 72 characters**, no trailing period, no body unless essential
   - Simple: describe what changed, not how or why. Group unrelated changes into one short summary, not a list.
   - Follow the attribution trailer given in the session's system reminder, if there is one.
5. Push to the default branch (`git push origin <default-branch>`).
   - If the current branch is not the default branch, ask before switching or pushing; do not push another branch by accident.
   - Never force-push. If the push is rejected, report why and stop.
6. Reply with the commit hash and message in one line.
