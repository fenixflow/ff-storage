---
allowed-tools: Bash(git:*)
argument-hint: [commit message]
description: Commit and push with verified human authorship
---

Commit and push changes ensuring proper human authorship:

## Pre-flight Check
- Current branch: !`git branch --show-current`
- Changes to commit: !`git status --short`

## Commit and Push

1. First verify Git author configuration:
   ```bash
   git config user.name
   git config user.email
   ```

   If these show "Claude Code" or are not set, configure them with the actual developer's information from the global config or recent commits.

2. Stage all changes:
   ```bash
   git add .
   ```

3. Commit with message: "$ARGUMENTS"
   ```bash
   git commit -m "$ARGUMENTS"
   ```

   If no message provided, create a meaningful commit message following conventional format (feat:, fix:, chore:, docs:, refactor:, test:, style:)

4. Verify the commit author is correct:
   ```bash
   git log -1 --pretty=format:"✓ Commit created by: %an <%ae>"
   ```

   If it shows "Claude Code", amend the commit with correct author before pushing.

5. Push to remote:
   ```bash
   git push origin HEAD
   ```

   If branch doesn't exist remotely:
   ```bash
   git push -u origin HEAD
   ```

6. Confirm push was successful and show final commit:
   ```bash
   git log -1 --pretty=format:"Author: %an <%ae>%nDate: %ad%nCommit: %H%nMessage: %s"
   ```

⚠️ NEVER force push without explicit permission
✓ Always verify human authorship before pushing
