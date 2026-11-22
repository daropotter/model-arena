"""Controls for the real Go review case and its idempotency mutant."""

import json
import os
import re
import shutil
import subprocess
import unittest

from tests.oracles.test_review import reviewlib, solution, task_spec
from tests.support import ROOT, TempDirTestCase

TASKS = ("goclusterreview", "goclusterreviewbug")
SOURCE = "internal/state/sqlite/clusters.go"

REPLAY_TEST = r'''package sqlite

import (
    "context"
    "database/sql"
    "database/sql/driver"
    "errors"
    "io"
    "strings"
    "testing"

    "github.com/daropotter/chmura/internal/state"
)

type replayDriver struct{}
type replayConn struct{}
type replayRows struct{ sent bool; existing bool }
func (replayDriver) Open(string) (driver.Conn, error) { return replayConn{}, nil }
func (replayConn) Prepare(string) (driver.Stmt, error) { return nil, errors.New("unused") }
func (replayConn) Close() error { return nil }
func (replayConn) Begin() (driver.Tx, error) { return nil, errors.New("unused") }
func (replayConn) QueryContext(_ context.Context, q string, _ []driver.NamedValue) (driver.Rows, error) {
    if strings.HasPrefix(q, "INSERT") { return &replayRows{}, nil }
    return &replayRows{existing: true}, nil
}
func (*replayRows) Columns() []string { return []string{"id", "name"} }
func (*replayRows) Close() error { return nil }
func (r *replayRows) Next(dst []driver.Value) error {
    if !r.existing || r.sent { return io.EOF }
    r.sent = true
    dst[0], dst[1] = "cl_existing", "alpha"
    return nil
}

func TestReplayRejectsDifferentName(t *testing.T) {
    sql.Register("replay", replayDriver{})
    db, err := sql.Open("replay", "")
    if err != nil { t.Fatal(err) }
    defer db.Close()
    s := Store{db: db}
    got, created, err := s.CreateCluster(context.Background(), state.CreateClusterRequest{Name: "beta", IdempotencyKey: "existing-key"})
    if !errors.Is(err, state.ErrConflict) || created || got != (state.Cluster{}) {
        t.Fatalf("replayed key for alpha as beta: got=%+v created=%v err=%v", got, created, err)
    }
}
'''


class GoReviewControls(TempDirTestCase, unittest.TestCase):
    def setUp(self):
        self.tmp = self.tmpdir()

    def workspace(self, task):
        ws = self.tmp / task
        if not ws.exists():
            shutil.copytree(ROOT / "tasks" / task / "starter", ws)
        return ws

    def grade(self, task, review):
        ws = self.workspace(task)
        (ws / "review.json").write_text(json.dumps(review))
        return reviewlib.grade(ws, task_spec(task))

    def test_reference_reviews_and_missing_answers(self):
        for task in TASKS:
            with self.subTest(task=task):
                missing = reviewlib.grade(self.workspace(task), task_spec(task))
                self.assertFalse(missing["passed"])
                result = self.grade(task, solution(task))
                self.assertTrue(result["passed"], result)
                self.assertEqual(result["score"], 1.0)

    def test_original_false_alarm_fails_at_every_severity(self):
        for task in TASKS:
            lines = (self.workspace(task) / SOURCE).read_text().splitlines()
            line = next(i for i, s in enumerate(lines, 1) if '"cl_"+rand.Text()' in s)
            for severity in ("low", "medium", "high"):
                with self.subTest(task=task, severity=severity):
                    review = solution(task)
                    review["findings"].append({"file": SOURCE, "line": line,
                        "severity": severity, "category": "correctness",
                        "title": "crypto/rand has no Text function, causing compile error",
                        "explanation": "The cluster ID generation uses rand.Text() from crypto/rand, which does not exist in the Go standard library. This will fail to compile."})
                    self.assertFalse(self.grade(task, review)["passed"])

    def test_clean_case_rejects_unmatched_low_severity_padding(self):
        review = {"verdict": "approve", "findings": [{"file": SOURCE,
            "line": 1, "severity": "low", "category": "maintainability",
            "title": "Rename this package", "explanation": "A style-only comment is not a demonstrated defect."}]}
        self.assertFalse(self.grade(TASKS[0], review)["passed"])

    def test_blanket_approval_and_wrong_positive_findings_fail(self):
        self.assertFalse(self.grade(TASKS[1], {"verdict": "approve", "findings": []})["passed"])
        review = solution(TASKS[1])
        review["findings"][0]["line"] = 1
        self.assertFalse(self.grade(TASKS[1], review)["passed"])
        review = solution(TASKS[1])
        review["findings"][0]["severity"] = "low"
        self.assertFalse(self.grade(TASKS[1], review)["passed"])

    def test_scorer_copies_are_identical(self):
        tasks = ("cartreview", "notesreview", "billingreview") + TASKS
        self.assertEqual(len({(ROOT / "tasks" / t / "grader/reviewlib.py").read_bytes() for t in tasks}), 1)

    def test_mutant_changes_only_the_replay_condition(self):
        clean = (self.workspace(TASKS[0]) / SOURCE).read_text()
        mutant = (self.workspace(TASKS[1]) / SOURCE).read_text()
        self.assertEqual(mutant, clean.replace('if cluster.Name != request.Name {', 'if cluster.Name == "" {'))

    def test_go_build_api_lookup_and_replay_control_offline(self):
        if not shutil.which("go"):
            self.skipTest("Go 1.25 is required for the executable fixture controls")
        env = dict(os.environ, GOTOOLCHAIN="local", GOPROXY="off", GOSUMDB="off", GOFLAGS="-p=1")
        version = subprocess.run(["go", "version"], env=env, capture_output=True, text=True, timeout=15)
        match = re.search(r"go(\d+)\.(\d+)", version.stdout)
        if not match or tuple(map(int, match.groups())) < (1, 25):
            self.skipTest("Go 1.25 is required; installed toolchain: " + version.stdout.strip())
        for task in TASKS:
            ws = self.workspace(task)
            with self.subTest(task=task):
                for args in (["go", "build", "./..."], ["go", "doc", "crypto/rand.Text"]):
                    proc = subprocess.run(args, cwd=ws, env=env, capture_output=True, text=True, timeout=90)
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("func Text() string", proc.stdout)
                (ws / "internal/state/sqlite/replay_test.go").write_text(REPLAY_TEST)
                proc = subprocess.run(["go", "test", "./internal/state/sqlite", "-run", "TestReplayRejectsDifferentName", "-count=1"],
                    cwd=ws, env=env, capture_output=True, text=True, timeout=90)
                if task == TASKS[0]:
                    self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                else:
                    self.assertNotEqual(proc.returncode, 0)
                    self.assertIn("got={ID:cl_existing Name:alpha} created=false err=<nil>", proc.stdout)
