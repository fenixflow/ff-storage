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

CRITICAL: NEVER commit as "Claude Code" or "Claude". ALL commits must be by the human developer only.

1. First verify Git author configuration:
   ```bash
   git config user.name
   git config user.email
   ```

   If these show "Claude Code", "Claude", or are not set, configure them with the actual developer's information from recent commits:
   ```bash
   # Get the human author from recent commits
   git log -1 --pretty=format:"%an%n%ae" | head -2

   # Then set it if needed
   git config user.name "Developer Name"
   git config user.email "developer@email.com"
   ```

2. Stage all changes:
   ```bash
   git add .
   ```

3. Commit with message: "$ARGUMENTS"
   ```bash
   git commit -m "$ARGUMENTS"
   ```

   IMPORTANT: Do NOT include "Generated with Claude Code" or "Co-Authored-By: Claude" in the commit message.

   If no message provided, create a meaningful commit message following conventional format (feat:, fix:, chore:, docs:, refactor:, test:, style:)

4. Verify the commit author is ONLY the human developer:
   ```bash
   git log -1 --pretty=format:"✓ Commit created by: %an <%ae>"
   ```

   If it shows "Claude Code" or "Claude", ABORT and amend the commit with correct author before pushing:
   ```bash
   git commit --amend --author="Developer Name <developer@email.com>" --no-edit
   ```

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
