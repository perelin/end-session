# Worktrees, submodules and closing a background session

Load this when the survey shows worktrees, submodules, or a background session whose worktree isn't "closable with ctrl+x".

## Why PR state, not `git branch --merged`

Squash-merged branches are not ancestors of main, so `git branch --merged main` misses them. The PR state is the source of truth, which is why `scripts/survey.py` looks up every branch's PR (`state`, `headRefOid`) instead.

## Auto-prune predicate, explained

1. `state == MERGED`: a PR that was closed without merging may hold work nobody saved.
2. Local tip == PR `headRefOid`: nothing was committed after the merged head, so nothing can be lost.
3. Worktree clean (`git status --porcelain` empty, untracked files included): a line like ` M <submodule>` is a moved submodule pointer or changed submodule content and counts as dirty. Never the worktree this session runs in, never the main checkout.
4. Submodules: `git -C <worktree>/<submodule> rev-list HEAD --not --remotes` is empty for each. A worktree's submodule repositories live in the worktree's own gitdir and are deleted with it.

## Removing worktrees with submodules

Git refuses to remove any worktree with checked-out submodules, clean or not (`working trees containing submodules cannot be moved or removed`; `submodule deinit` doesn't change that). For such a worktree, and only once predicates 1–4 hold, `git worktree remove --force <path>` is the removal, the same thing Claude Code's own session delete does. Outside this case, never `--force`.

## Making the current background session closable

You cannot remove the worktree the session is standing in. In a background session (`$CLAUDE_JOB_DIR` is set), closing it in Agent View (ctrl+x, or `claude rm <id>`) deletes that worktree, and Claude Code refuses while it can't prove nothing is lost. With a moved submodule pointer the session can't be closed at all until someone deletes the directory by hand.

The survey's `THIS WORKTREE` line gives the verdict; the lines under it are `AUTO` / `LAST` commands to run and `BLOCKER`s to resolve. Agent View's checks, as of Claude Code 2.1.322:

- **unpushed:** `git log HEAD --not --remotes` in the worktree is non-empty. It doesn't know about squash merges.
- **live_lock:** the worktree's `git worktree lock` reason (`claude session <name> (pid N start …)`, written when the session entered the worktree) names a process that is alive and not among the job's own. Agent View kills the session first and then checks; the session's process is the child under its `bg-pty-host`, and while it is still exiting it counts as live. Unlocking from inside the session avoids that: with no lock, the check passes. (Derived from the bundle and from transcripts where an unlock got past the check; a respawn after the unlock may lock the worktree again under the new pid, also only derived. If Agent View refuses with the lock message anyway, ask the session to run the unlock again.)

Resolve them like this:

- **Uncommitted changes:** unsaved work; propose commit/push (ask tier).
- **Moved submodule pointer** (`+` in `git submodule status`): if the session meant to change the submodule, push the submodule's commits and commit the new pointer in the superproject (ask tier, like any commit). If not, save any submodule commits first, then reset the pointer with `git -C <worktree> submodule update -- <submodule>` (ask tier; it moves the submodule's HEAD).
- **Commits on no remote, PR merged as-is (`AUTO`):** the commits are gone from the remote once the PR's branch is deleted (any `git fetch --prune` drops the tracking ref), but their content is in main. The printed `git switch --detach origin/<default>` puts HEAD on a remote commit, and `git branch -D` deletes the merged branch under the step-3 predicate (PR merged, tip == merged head, worktree clean). Run them without asking.
- **Commits on no remote, PR merged but a commit after the merged head, or the worktree dirty (`BLOCKER`):** unsaved work on top of the merge; propose a follow-up PR (ask tier).
- **Claude Code lock (`LAST`):** run the printed `git worktree unlock` as the last tool call before the handover. Another session's survey keeps a worktree locked by a running session and never prunes it; after the unlock that protection is gone, which is fine for a session that is about to be closed.
- **Locked by something other than Claude Code (`BLOCKER`):** someone ran `git worktree lock` on purpose; ask before unlocking.
- **Commits on no remote, no merged PR:** unsaved work; propose push/PR (ask tier).
