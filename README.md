# end-session

A Claude Code skill for closing a work session cleanly and starting the next one from a fresh context.

Run it when a unit of work is done, or when the context window is getting full. It:

1. **Surveys** every repo the session touched with a read-only script: unsaved work, open PRs, and every local branch and worktree classified `AUTO-PRUNE` / `ASK` / `KEEP`.
2. **Gets PRs ready**: description, checks, draft → ready. It never merges without an explicit yes.
3. **Updates tracking**: posts a project update (e.g. Linear) and moves tickets to match reality.
4. **Cleans up**: deletes branches and worktrees whose PR is verifiably merged, asks about everything else, and makes sure a background session can be closed without losing work.
5. **Persists recurring gotchas** in the narrowest durable place (a code comment, the repo's `CLAUDE.md`, or auto-memory) instead of copying them from handover to handover.
6. **Prints a handover**: one short markdown block of pointers (PRs, tickets, paths, commands that show live state) that you paste as the first prompt of the next session.

## Install

Inside Claude Code:

```
/plugin install end-session --marketplace perelin/end-session
```

or from a shell:

```
claude plugin marketplace add perelin/end-session
claude plugin install end-session@end-session --scope user
```

Then say "end session" (or "wrap up", "hand over") at the end of a session, or invoke the skill directly.

## Requirements

- `git` and `python3` (standard library only)
- `gh`, authenticated, for PR state. Without it every branch is classified `ASK` and nothing is pruned automatically.
- Optional: a Linear (or other tracker) connector for project updates

## Side effects

The skill sorts actions into two tiers:

- **Done without asking, reported afterwards**: posting a project update, moving a ticket, marking a PR ready when checks are green, pushing the session's own commits to a branch with an open PR, deleting a branch/worktree the survey marks `AUTO-PRUNE`, writing technical gotchas to auto-memory.
- **Shown first, done only after a yes**: merging, force-pushing, deleting anything else, deleting temp files, writing to repo files, writing or deleting memories about how you work.

`AUTO-PRUNE` requires all of: the branch's PR is merged, the local tip equals the merged head, the worktree is clean and isn't the main checkout or the current session's, and no submodule holds commits that exist on no remote.

## The handover

The handover carries pointers, not status prose, because the next session checks live state anyway. It targets 2.5k characters at most. The first two lines are my greeting and working mode (German, "ask before acting, with a weighted recommendation"); replace them with yours in `skills/end-session/SKILL.md`.

```
## Goal · ## Pointers · ## Check current state · ## Open decisions
## Next steps · ## Unverified assumptions · ## Gotchas (this transition only)
```

## The survey script

```
python3 skills/end-session/scripts/survey.py [--no-fetch] REPO [REPO ...]
```

It's read-only apart from `git fetch --prune`. Example output:

```
session 6c8612e1-…
transcript ~/.claude/projects/…/6c8612e1-….jsonl
session kind background (closing deletes this worktree)

## ~/code/app
AUTO-PRUNE fix-login: merged #41 – Fix login redirect [worktree ~/code/app/.claude/worktrees/fix-login]
ASK        spike-cache: no PR
KEEP       main: default branch
KEEP       feature-x: open PR #44 – Add export
OPEN PR    #44 – Add export (draft) — https://github.com/…/pull/44
THIS WORKTREE ~/code/app/.claude/worktrees/feature-x: closable with ctrl+x
```

## Tests

```
python3 -m unittest discover -s tests
```

The tests build throwaway git repos with a bare remote and replace `gh` with a stub.

## Background

Why a fresh session per unit of work, and where the ideas in this skill come from: see the blog post on [ghost.p2lab.com](https://ghost.p2lab.com/).

## License

MIT
