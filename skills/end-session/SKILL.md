---
name: end-session
description: End a coding session cleanly. Use at the end of a work session or when the user says "end session", "end the session", "finish up", "close out", or "hand over". Checks PR readiness, updates project tracking and tickets (e.g. Linear project updates), prunes stale branches/worktrees/temp files while keeping anything tied to an open PR, persists recurring gotchas where they belong instead of carrying them in handovers, then prints a pointer-based, copy-pasteable handover note for the next session.
---

# End session

Run the steps in order. Skip any that don't apply: not every session has a PR, a ticket, or cleanup to do. Decide what applies from the survey in step 0, then tell the user which steps you're running and which you're skipping.

**Side-effect rule:** there are two tiers.

- **Status updates that just reflect reality: do them, no confirmation needed.** Posting a Linear/project update, moving a ticket to match the work, marking a PR ready (when checks are green and the description is complete), and pushing this session's own commits on a branch that has an open PR. Also pruning everything the survey marks `AUTO-PRUNE`, and running the `AUTO` and `LAST` commands the survey prints for this session's worktree (step 3), and saving `reference`/`discovery` gotchas to auto-memory when they pass the step-4 filter. Show what you did right after; don't ask first. The answer to "should I post this?" / "should I prune this merged branch?" is always yes; stop asking.
- **Destructive, cross-system or knowledge-placing actions: show the exact plan and get a yes first.** Merge, force-push, delete any branch/worktree the survey doesn't mark `AUTO-PRUNE`, delete temp files, write `feedback` memories, place gotchas in repo files, or delete memories (step 4). Drafting and proposing is free; executing these is not.

**Sequencing:** the handover (step 5) is the last thing you output, once, after every step above is finished and every question to the user is answered. It is a snapshot of the completed state, not of the plan.

## 0. Survey state

Gather facts before touching anything. **Cover every repo this session touched**, not just the cwd: sessions regularly span several repos (submodules, sibling services, an ops/infra repo). Run the survey script from this skill's base directory once, with all of them:

```
python3 <skill-dir>/scripts/survey.py <repo> [<repo> …]
```

It is read-only apart from `git fetch --prune`, and prints the session id, transcript path and session kind, then per repo: every local branch and worktree classified `AUTO-PRUNE` / `ASK` / `KEEP` with the reason, commits on no remote, open PRs, and whether the worktree this session runs in can be closed. Don't re-run its git/gh checks by hand; read them from its output. Read the whole output: never pipe it through `head`, `tail`, `cut` or similar, because the lines about this session's worktree come last. Remote hosts and non-git state (a running migration, a deployed service) still need their own look.

Note what changed this session (commits, modified files, tickets, remote hosts touched). Use this to pick which steps below apply.

## 1. PRs

For each PR from this session:

- **Description**: has a clear title, a summary, and a test plan? If thin, draft a better body and offer to apply it (`gh pr edit`).
- **Checks**: `gh pr checks`. If failing, surface the failures; do not mark ready.
- **Reviewer**: only if the repo relies on human review and none is assigned. Propose reviewers (CODEOWNERS or recent touchers). Skip where a bot/pipeline review flow handles it.
- **Draft → ready**: when checks pass and the description is complete, run `gh pr ready`; no need to ask. Report that you did it. If checks are failing or the description is thin, fix that first instead.
- **Merge**: never on your own. If the PR looks merge-ready, propose the merge (exact command, e.g. `gh pr merge <n>`); once the user explicitly approves, execute it yourself and report the result.

## 2. Tracking, docs, tickets

- **Project update** (e.g. Linear): if the MCP/connector is available, write the update (what shipped, what's in progress, blockers) and post it. Don't ask first; show what you posted afterward. If no connector is available, output the text for the user to paste.
- **Ticket state**: move tickets to match reality (In Progress → In Review when a PR opened, etc.) directly, then report the change.
- **Docs**: if the session changed public behavior, APIs, config, or commands, check README / CHANGELOG / relevant docs. Make the edits, or flag exactly what needs updating.

## 3. Cleanup and unsaved work

**Unsaved work first.** Uncommitted changes or unpushed commits disappear with a removed worktree or a deleted background job.

- Commits on no remote on a branch with an open PR → push (status-update tier).
- Uncommitted changes, or commits on no remote without a PR → propose commit/push/PR (ask tier). Never leave it silently; if the user declines, name it in the handover under Open decisions.

**Auto-prune** what the survey marks `AUTO-PRUNE`. The script applies this predicate; all must hold:

1. The branch's PR is `MERGED` (not just closed).
2. Local tip == the PR's `headRefOid`.
3. Its worktree, if any, is clean (submodule lines count as dirty), and is neither this session's worktree nor the main checkout.
4. Each submodule in that worktree has no commits on no remote.

Then, without asking:

```
git worktree remove <path>          # never --force, except a worktree with submodules: see references/worktrees.md
git branch -D <branch>              # -D is needed after squash merges; only for AUTO-PRUNE
git push origin --delete <branch>   # only if the remote branch still exists after fetch --prune
```

**Ask bucket**: everything marked `ASK`, plus temp files created this session (scratch files, `.bak`, debug logs, leftover test artifacts; the script can't see their provenance). Present one list, confirm, then act.

**Guard**: `KEEP` means keep: an open PR's branch, worktree and WIP; the default branch; this session's worktree; a worktree locked by a running session. Never delete commits on no remote. Never `git branch -D` a branch the survey didn't mark `AUTO-PRUNE`, except the one in this worktree's `AUTO` commands.

**This session's worktree**: the goal is that one ctrl+x in Agent View closes the session. The survey's `THIS WORKTREE` line gives the verdict, and the indented lines under it say what's left:

- `AUTO` (the branch's PR is merged as-is, its pre-squash commits are on no remote): run the printed commands now, without asking. They detach the worktree to the default branch and delete the merged branch; nothing is lost, the content is in the default branch. Otherwise Agent View refuses with "N unpushed commits".
- `LAST` (Claude Code's lock on this worktree, background sessions only): run the printed `git worktree unlock` as your last tool call, after every other step and right before the handover. Otherwise Agent View can refuse with "worktree holds a Claude Code lock for a running process".
- `BLOCKER`: needs a decision. Treat it as unsaved work above (ask tier), or see `references/worktrees.md`.

Run each printed command as its own Bash call, exactly as printed. If a blocker shows up, or the survey lists worktrees with submodules, read `references/worktrees.md` from this skill's directory before acting. Report the result as one line.

Report auto-pruned items as one short list (branch, PR `#<n> – <title>`, what was removed).

## 4. Persist recurring gotchas

Handovers are for *this* transition. Knowledge that will bite again belongs somewhere durable; otherwise it gets copied from handover to handover and lost when one isn't pasted.

Collect the non-obvious things learned this session (traps, workarounds, conventions, domain rules, data-protection constraints). For each, ask: **will this still be true and relevant in a month?**

- **No: one-off** (state of a running migration, a flaky run today) → stays in the handover's Gotchas.
- **Project status is never a gotcha.** What's dispatched, merged, blocked or next lives in the ticket, the project update and the handover, not in memory, not in a memory description or index line.
- **Yes** → pick the *narrowest* place that will be read when it matters:
  - Applies to one module, script or file → doc next to the code (module README, docstring) or a code comment at the exact spot, following the project's comment rules.
  - Applies to the repo as a whole → the repo's `CLAUDE.md` / docs.
  - Applies across repos, or is about how the user works → auto-memory.
  - Never promote a repo-local gotcha to global `CLAUDE.md` or memory.
- Already persisted somewhere (check before proposing) → update or link it instead of adding a near-duplicate.

**Memory filter**: a memory entry is written only if all hold:

1. No date in the filename; name, description and index line carry no state of tickets or PRs (dispatched, merged, blocked, …).
2. States a mechanism or rule, not an observation of one day.
3. If the project's memory uses hubs (`hub_*.md`), the entry is linked from the fitting hub; otherwise from `MEMORY.md`. Don't grow `MEMORY.md` when a hub fits.

**Who decides:**

- `reference` / `discovery` memories that pass the filter → write them, then list `name — one-line hook` in the report. Don't ask: the user can't judge technical gotchas better than you; the filter is the gate.
- `feedback` memories (how the user wants to work) → ask tier, shown as `rule → exact text`. The user is the authority on these.
- Repo files (`CLAUDE.md`, READMEs, code comments) → ask tier, as `gotcha → target → exact text`. Repo edits go on the session's branch/PR (or propose a small PR), never uncommitted into someone's working copy.

**Prune pass**: every run, on the current project's memory directory (plus any other you wrote to), whether or not this session saved anything. Propose deletion candidates (ask tier, one list, one yes/no):

- `project_*` entries tied to this session's tickets/PRs (already resolved in steps 1–2) that are now Done/Canceled or merged, unless they hold a rule that outlives the project. Don't look up tickets of unrelated entries.
- Entries this session proved wrong or superseded.
- Index or hub lines that carry status or dates: propose the rewritten line.

Skip the pass when nothing qualifies; don't present an empty list. On deletion, also remove the index/hub link.

In the handover, durable gotchas appear only as a pointer to where they now live.

## 5. Handover note

**Gate:** only once steps 0–4 are complete, nothing is waiting on the user, and the `LAST` command from step 3 (if any) ran.

Print **one** fenced markdown block in the chat (not a file) that the user pastes as the *entire* first prompt of the next session. The next session re-checks live state first anyway, so the note carries **pointers, not status prose**: IDs, paths, hosts, and the commands that reveal current state. Don't restate what a PR, commit, ticket or Linear update already says; point to it. Target ≤ 2.5k characters; Pointers is where notes grow, so one line per item, no explanations there.

Rules:

- Keep the first two lines **verbatim**: they are the user's greeting and working mode.
- PRs and tickets always as `ID – short title` plus URL; paths absolute with `~`.
- What this session finished shows up as its PRs/commits under Pointers; there is no separate Done section.
- No status adjectives that go stale (draft/ready/green) except where they drive a decision.
- Drop any section that's empty.
- Background session: one Gotchas line on closing it, from step 3, only when a `BLOCKER` is left and the user decided to keep it (e.g. "ctrl+x twice: discards the uncommitted scratch files in <path>").
- **Open decisions** holds only what the user alone can settle: a product call with no default, access or credentials, something irreversible. Anything with a clear default goes under Next steps as `Default: <what>`; a listed decision makes the next session wait for an answer it does not need.
- Work that runs under a skill names it as the first Pointer; the skill's rules on when to ask apply on top of the working-mode line.

```
moin! lass uns hier weitermachen. stop and ask. mit gewichtetem vorschlag.
Lies den Handover, verschaff dir selbst ein Bild vom aktuellen Stand und entscheide dann mit mir, wie es weitergeht.

# Handover — <short title> — <date>

## Goal
<one sentence: what this work is for>

## Pointers
- Skill: /<skill> (only if the work runs under one)
- Repos/worktrees: <~/path> (branch <branch>) …
- PRs: #<n> – <title> — <url>   (this session's work, merged or open)
- Tickets: <ID> – <title> — <url>
- Hosts/services: <ssh target, dashboard, DB gateway — where, not secrets>
- Docs/notes: <ADR, README, persisted gotchas from step 4>
- Previous session: `claude --resume <session-id>` · transcript <~/.claude/projects/…/<id>.jsonl>

## Check current state
<2–4 commands that show live state: gh pr view …, git -C … status, linear query, journalctl …>

## Open decisions
- <only what needs the user: product call without default / access / irreversible — with your weighted recommendation>

## Next steps
1. <concrete action> — <why / what it unblocks>

## Unverified assumptions
- <things assumed but not checked or not confirmed by the user>

## Gotchas (this transition only)
- <one-off traps; durable ones live in step-4 targets and are linked under Pointers>
```
