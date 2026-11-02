#!/usr/bin/env python3
"""Read-only end-of-session survey for one or more git repos.

Prints, per repo: unsaved work, open PRs, every local branch and worktree
classified as AUTO-PRUNE / ASK / KEEP, and whether the worktree this session
runs in can be closed cleanly. It never deletes, commits or pushes; the only
write is `git fetch --prune` (skip with --no-fetch).

Usage: survey.py [--no-fetch] [REPO ...]   (default: current directory)
"""
import argparse
import json
import os
import subprocess
import sys


def run(args, cwd, check=False):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(args)}: {p.stderr.strip()}")
    return p.returncode, p.stdout.strip()


def git(cwd, *args):
    return run(["git", "-C", cwd, *args], cwd)[1]


def real(path):
    return os.path.realpath(path)


def default_branch(repo):
    ref = git(repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if ref:
        return ref.split("/", 1)[1]
    for name in ("main", "master"):
        if git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"):
            return name
    return ""


def worktrees(repo):
    out, cur = [], {}
    for line in git(repo, "worktree", "list", "--porcelain").splitlines() + [""]:
        if not line:
            if cur:
                out.append(cur)
            cur = {}
        elif line.startswith("worktree "):
            cur["path"] = line[9:]
        elif line.startswith("branch "):
            cur["branch"] = line[7:].removeprefix("refs/heads/")
        elif line == "bare":
            cur["bare"] = True
    return out


def prs_by_branch(repo):
    """Most recent PR per head branch, or None when gh is unusable here."""
    code, out = run(
        ["gh", "pr", "list", "--state", "all", "--limit", "300",
         "--json", "number,title,state,headRefName,headRefOid,url,isDraft"],
        repo,
    )
    if code != 0:
        return None
    prs = {}
    for pr in sorted(json.loads(out or "[]"), key=lambda p: p["number"]):
        prs[pr["headRefName"]] = pr
    return prs


def submodule_problems(wt):
    """Moved pointers ('+') and submodule commits that exist on no remote."""
    problems = []
    for line in git(wt, "submodule", "status", "--recursive").splitlines():
        flag, rest = line[:1], line[1:].split()
        if len(rest) < 2:
            continue
        sub = rest[1]
        if flag == "+":
            problems.append(f"submodule {sub}: pointer moved")
        if git(os.path.join(wt, sub), "rev-list", "HEAD", "--not", "--remotes"):
            problems.append(f"submodule {sub}: commits on no remote")
    return problems


def pr_label(pr):
    return f"#{pr['number']} – {pr['title']}"


def classify(tip, wt, pr, here, main_wt=""):
    """Apply the step-3 auto-prune predicate. Returns (bucket, reason)."""
    if wt and real(wt) == main_wt:
        return "ASK", "checked out in the main checkout"
    if pr is None:
        return "ASK", "no PR"
    if pr["state"] == "OPEN":
        return "KEEP", f"open PR {pr_label(pr)}"
    if pr["state"] != "MERGED":
        return "ASK", f"PR {pr_label(pr)} closed without merge"
    if tip != pr["headRefOid"]:
        return "ASK", f"merged {pr_label(pr)}, but local tip differs from the merged head"
    if wt:
        if real(wt) == here:
            return "KEEP", f"merged {pr_label(pr)}; this session runs here"
        if git(wt, "status", "--porcelain"):
            return "ASK", f"merged {pr_label(pr)}, worktree dirty"
        subs = submodule_problems(wt)
        if subs:
            return "ASK", f"merged {pr_label(pr)}; " + "; ".join(subs)
    return "AUTO-PRUNE", f"merged {pr_label(pr)}"


def closability(wt, branch, prs):
    blockers = []
    if git(wt, "status", "--porcelain"):
        blockers.append("uncommitted or untracked changes")
    blockers += submodule_problems(wt)
    if git(wt, "rev-list", "HEAD", "--not", "--remotes"):
        pr = (prs or {}).get(branch)
        if pr and pr["state"] == "MERGED":
            blockers.append(
                f"commits on no remote, content squash-merged via {pr_label(pr)}: "
                "ctrl+x twice discards them")
        else:
            blockers.append("commits on no remote (unsaved work)")
    return blockers


def survey(repo, fetch, here):
    repo = git(repo, "rev-parse", "--show-toplevel") or repo
    print(f"## {repo}")
    if fetch:
        run(["git", "-C", repo, "fetch", "--prune", "--quiet"], repo)
    print(git(repo, "status", "-sb").splitlines()[0] if git(repo, "status", "-sb") else "")
    base = default_branch(repo)
    prs = prs_by_branch(repo)
    if prs is None:
        print("gh: unavailable for this repo; every branch below is ASK")

    all_wts = worktrees(repo)
    main_wt = real(all_wts[0]["path"]) if all_wts else ""
    wts = {w.get("branch"): w["path"] for w in all_wts if w.get("branch")}
    rows = []
    for line in git(repo, "for-each-ref", "--format=%(refname:short) %(objectname)",
                    "refs/heads").splitlines():
        branch, tip = line.split(" ")
        wt = wts.get(branch)
        unpushed = git(repo, "rev-list", "--count", branch, "--not", "--remotes")
        if branch == base:
            bucket, reason = "KEEP", "default branch"
        elif prs is None:
            bucket, reason = "ASK", "PR state unknown"
        else:
            bucket, reason = classify(tip, wt, prs.get(branch), here, main_wt)
        extra = []
        if unpushed and unpushed != "0":
            extra.append(f"{unpushed} commit(s) on no remote")
        if wt:
            extra.append(f"worktree {wt}")
            if git(wt, "status", "--porcelain"):
                extra.append("dirty")
        rows.append((bucket, branch, reason, extra))

    order = {"AUTO-PRUNE": 0, "ASK": 1, "KEEP": 2}
    for bucket, branch, reason, extra in sorted(rows, key=lambda r: (order[r[0]], r[1])):
        tail = f" [{', '.join(extra)}]" if extra else ""
        print(f"{bucket:10} {branch}: {reason}{tail}")

    if prs:
        open_prs = [p for p in prs.values() if p["state"] == "OPEN"]
        for pr in open_prs:
            draft = " (draft)" if pr.get("isDraft") else ""
            print(f"OPEN PR    {pr_label(pr)}{draft} — {pr['url']}")

    for w in worktrees(repo):
        if real(w["path"]) == here:
            blockers = closability(w["path"], w.get("branch"), prs)
            verdict = "closable with ctrl+x" if not blockers else "; ".join(blockers)
            print(f"THIS WORKTREE {w['path']}: {verdict}")
    print()


def main():
    ap = argparse.ArgumentParser(description="Read-only end-of-session survey.")
    ap.add_argument("repos", nargs="*", default=["."])
    ap.add_argument("--no-fetch", action="store_true")
    a = ap.parse_args()

    here_top = run(["git", "rev-parse", "--show-toplevel"], os.getcwd())[1]
    here = real(here_top) if here_top else ""
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if sid:
        projects = os.path.expanduser("~/.claude/projects")
        hits = [os.path.join(projects, d, f"{sid}.jsonl") for d in os.listdir(projects)
                if os.path.exists(os.path.join(projects, d, f"{sid}.jsonl"))] \
            if os.path.isdir(projects) else []
        print(f"session {sid}")
        print(f"transcript {hits[0].replace(os.path.expanduser('~'), '~', 1) if hits else '(not found)'}")
    # CLAUDE_CODE_SESSION_KIND is not always exported; CLAUDE_JOB_DIR is set in every background job.
    bg = os.environ.get("CLAUDE_JOB_DIR") or os.environ.get("CLAUDE_CODE_SESSION_KIND") == "bg"
    print(f"session kind {'background (closing deletes this worktree)' if bg else 'interactive'}\n")

    for repo in a.repos:
        try:
            survey(os.path.abspath(os.path.expanduser(repo)), not a.no_fetch, here)
        except Exception as e:  # one broken repo must not hide the others
            print(f"## {repo}\nerror: {e}\n")


if __name__ == "__main__":
    sys.exit(main())
