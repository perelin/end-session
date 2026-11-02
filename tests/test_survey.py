"""End-to-end tests for scripts/survey.py against throwaway git repos.

`gh` is replaced by a stub on PATH that prints the PR list from $FAKE_PRS.
Run from the repo root: python3 -m unittest discover -s tests
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "skills", "end-session", "scripts", "survey.py")


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class SurveyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = os.path.realpath(self.tmp.name)
        self.env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        os.environ.update({k: self.env[k] for k in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
                                                     "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")})
        self.remote = os.path.join(t, "remote.git")
        self.repo = os.path.join(t, "repo")
        sh(t, "git", "init", "-q", "--bare", "-b", "main", self.remote)
        sh(t, "git", "clone", "-q", self.remote, self.repo)
        sh(self.repo, "git", "checkout", "-q", "-b", "main")
        sh(self.repo, "git", "commit", "-q", "--allow-empty", "-m", "init")
        sh(self.repo, "git", "push", "-q", "-u", "origin", "main")

        bindir = os.path.join(t, "bin")
        os.mkdir(bindir)
        stub = os.path.join(bindir, "gh")
        with open(stub, "w") as f:
            f.write(textwrap.dedent("""\
                #!/bin/sh
                cat "$FAKE_PRS"
                """))
        os.chmod(stub, 0o755)
        self.prs_file = os.path.join(t, "prs.json")
        self.env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
        self.env["FAKE_PRS"] = self.prs_file
        self.env.pop("CLAUDE_CODE_SESSION_ID", None)
        self.prs = []

    def tearDown(self):
        self.tmp.cleanup()

    def branch(self, name, push=True):
        sh(self.repo, "git", "branch", name, "main")
        wt = os.path.join(os.path.dirname(self.repo), f"wt-{name}")
        sh(self.repo, "git", "worktree", "add", "-q", wt, name)
        sh(wt, "git", "commit", "-q", "--allow-empty", "-m", f"work on {name}")
        if push:
            sh(wt, "git", "push", "-q", "origin", name)
        return wt, sh(wt, "git", "rev-parse", "HEAD")

    def pr(self, branch, state, oid, n):
        self.prs.append({"number": n, "title": f"t{n}", "state": state, "headRefName": branch,
                         "headRefOid": oid, "url": f"https://x/{n}", "isDraft": False})

    def survey(self, cwd=None):
        with open(self.prs_file, "w") as f:
            json.dump(self.prs, f)
        out = subprocess.run([sys.executable, SCRIPT, "--no-fetch", self.repo],
                             cwd=cwd or self.repo, env=self.env,
                             capture_output=True, text=True, check=True).stdout
        return {l.split()[1].rstrip(":"): l.split()[0]
                for l in out.splitlines() if l.split()[:1] and l.split()[0] in
                ("AUTO-PRUNE", "ASK", "KEEP")}, out

    def test_merged_clean_branch_is_auto_prune(self):
        _, oid = self.branch("done")
        self.pr("done", "MERGED", oid, 1)
        self.assertEqual(self.survey()[0]["done"], "AUTO-PRUNE")

    def test_commit_after_merge_is_ask(self):
        wt, oid = self.branch("later")
        self.pr("later", "MERGED", oid, 2)
        sh(wt, "git", "commit", "-q", "--allow-empty", "-m", "after merge")
        self.assertEqual(self.survey()[0]["later"], "ASK")

    def test_dirty_worktree_is_ask(self):
        wt, oid = self.branch("dirty")
        self.pr("dirty", "MERGED", oid, 3)
        open(os.path.join(wt, "scratch.txt"), "w").close()
        self.assertEqual(self.survey()[0]["dirty"], "ASK")

    def test_open_pr_is_keep_and_no_pr_is_ask(self):
        _, oid = self.branch("wip")
        self.pr("wip", "OPEN", oid, 4)
        self.branch("orphan")
        result, out = self.survey()
        self.assertEqual(result["wip"], "KEEP")
        self.assertEqual(result["orphan"], "ASK")
        self.assertIn("OPEN PR    #4 – t4", out)

    def test_closed_unmerged_is_ask(self):
        _, oid = self.branch("dropped")
        self.pr("dropped", "CLOSED", oid, 5)
        self.assertEqual(self.survey()[0]["dropped"], "ASK")

    def test_current_worktree_is_kept_and_closability_reported(self):
        wt, oid = self.branch("here", push=False)
        self.pr("here", "MERGED", oid, 6)
        result, out = self.survey(cwd=wt)
        self.assertEqual(result["here"], "KEEP")
        self.assertIn("squash-merged via #6 – t6", out)

    def test_clean_pushed_current_worktree_is_closable(self):
        wt, oid = self.branch("clean")
        self.pr("clean", "OPEN", oid, 7)
        self.assertIn("closable with ctrl+x", self.survey(cwd=wt)[1])

    def test_branch_in_main_checkout_is_never_auto_pruned(self):
        _, oid = self.branch("moved")
        sh(os.path.dirname(self.repo), "git", "-C", self.repo, "worktree", "remove",
           os.path.join(os.path.dirname(self.repo), "wt-moved"))
        sh(self.repo, "git", "checkout", "-q", "moved")
        self.pr("moved", "MERGED", oid, 8)
        self.assertEqual(self.survey()[0]["moved"], "ASK")

    def test_unpushed_submodule_commit_blocks_auto_prune(self):
        lib = os.path.join(os.path.dirname(self.repo), "lib.git")
        sh(self.repo, "git", "init", "-q", "--bare", "-b", "main", lib)
        seed = os.path.join(os.path.dirname(self.repo), "lib-seed")
        sh(self.repo, "git", "clone", "-q", lib, seed)
        sh(seed, "git", "commit", "-q", "--allow-empty", "-m", "lib init")
        sh(seed, "git", "push", "-q", "origin", "HEAD:main")
        wt, _ = self.branch("withsub")
        sh(wt, "git", "-c", "protocol.file.allow=always", "submodule", "add", "-q", lib, "lib")
        sh(wt, "git", "commit", "-q", "-m", "add lib")
        sh(wt, "git", "push", "-q", "origin", "withsub")
        sh(os.path.join(wt, "lib"), "git", "commit", "-q", "--allow-empty", "-m", "local only")
        sh(wt, "git", "commit", "-q", "-am", "bump pointer")
        sh(wt, "git", "push", "-q", "origin", "withsub")
        self.pr("withsub", "MERGED", sh(wt, "git", "rev-parse", "HEAD"), 10)
        result, out = self.survey()
        self.assertEqual(result["withsub"], "ASK")
        self.assertIn("submodule lib: commits on no remote", out)

    def test_gh_failure_degrades_to_ask(self):
        _, oid = self.branch("nogh")
        self.pr("nogh", "MERGED", oid, 9)
        with open(self.prs_file, "w") as f:
            json.dump(self.prs, f)
        env = dict(self.env, FAKE_PRS="/nonexistent")
        out = subprocess.run([sys.executable, SCRIPT, "--no-fetch", self.repo], cwd=self.repo,
                             env=env, capture_output=True, text=True, check=True).stdout
        self.assertIn("ASK        nogh: PR state unknown", out)


if __name__ == "__main__":
    unittest.main()
