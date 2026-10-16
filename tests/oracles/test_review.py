"""Oracle tests for the code-review tasks (cartreview, notesreview,
billingreview).

The shared scorer (reviewlib.py, one byte-identical copy per grader) is
exercised against shipped solutions and a set of cheating or sloppy
reviews: an empty review, a spray of findings over every changed line,
decoy hits, downgraded severities and over-long reviews. A second group
demonstrates that the planted problems are real by triggering them in the
starter code.
"""

import base64
import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import unittest
from decimal import Decimal
from pathlib import Path

from tests.support import ROOT, TempDirTestCase

TASKS = ("cartreview", "notesreview", "billingreview")


def load_reviewlib():
    path = ROOT / "tasks" / "cartreview" / "grader" / "reviewlib.py"
    spec = importlib.util.spec_from_file_location("arena_reviewlib", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reviewlib = load_reviewlib()


def task_spec(task):
    return json.loads((ROOT / "tasks" / task / "grader" / "issues.json").read_text())


def solution(task):
    return json.loads((ROOT / "tasks" / task / "solution" / "review.json").read_text())


def finding(file, line, severity="high", category="correctness"):
    return {"file": file, "line": line, "severity": severity, "category": category,
            "title": "problem", "explanation": "a sufficiently long explanation text"}


class ReviewGradingTest(TempDirTestCase, unittest.TestCase):
    def setUp(self):
        self.tmp = self.tmpdir()

    def workspace(self, task, review):
        ws = self.tmp / task
        if not ws.exists():
            shutil.copytree(ROOT / "tasks" / task / "starter", ws)
        if review is None:
            (ws / "review.json").unlink(missing_ok=True)
        else:
            (ws / "review.json").write_text(json.dumps(review))
        return ws

    def grade(self, task, review):
        return reviewlib.grade(self.workspace(task, review), task_spec(task))

    def test_reviewlib_copies_identical(self):
        copies = {(ROOT / "tasks" / t / "grader" / "reviewlib.py").read_bytes() for t in TASKS}
        self.assertEqual(len(copies), 1)

    def test_solutions_pass(self):
        for task in TASKS:
            with self.subTest(task=task):
                result = self.grade(task, solution(task))
                self.assertTrue(result["passed"], result["detail"])
                self.assertEqual(result["score"], 1.0)

    def test_missing_and_empty_reviews_fail(self):
        for task in TASKS:
            with self.subTest(task=task):
                self.assertEqual(self.grade(task, None)["score"], 0.0)
                empty = self.grade(task, {"verdict": "request_changes", "findings": []})
                self.assertFalse(empty["passed"])
                self.assertAlmostEqual(empty["score"], 0.15)
                approve = self.grade(task, {"verdict": "approve", "findings": []})
                self.assertEqual(approve["score"], 0.0)

    def test_too_many_findings_score_zero(self):
        for task in TASKS:
            with self.subTest(task=task):
                review = solution(task)
                limit = task_spec(task)["max_findings"]
                review["findings"] += [review["findings"][0]] * (limit + 1 - len(review["findings"]))
                result = self.grade(task, review)
                self.assertEqual(result["score"], 0.0)
                self.assertFalse(result["passed"])

    def test_spraying_changed_lines_fails(self):
        """One high finding per added line, as many as the limit allows,
        rotating categories: must not pass and must stay well below 1."""
        categories = sorted(reviewlib.CATEGORIES)
        for task in TASKS:
            with self.subTest(task=task):
                limit = task_spec(task)["max_findings"]
                added, current, line = [], None, 0
                for text in (ROOT / "tasks" / task / "starter" / "change.diff").read_text().splitlines():
                    if text.startswith("+++ "):
                        current = text[6:] if text.startswith("+++ b/") else None
                    elif text.startswith("@@"):
                        line = int(text.split("+")[1].split(",")[0].split(" ")[0]) - 1
                    elif current and not current.startswith("tests/") and text[:1] in (" ", "+"):
                        line += 1
                        if text.startswith("+") and text[1:].strip():
                            added.append((current, line))
                step = max(1, len(added) // limit)
                picks = added[::step][:limit]
                review = {"verdict": "request_changes", "findings": [
                    finding(f, n, "high", categories[i % len(categories)])
                    for i, (f, n) in enumerate(picks)]}
                result = self.grade(task, review)
                self.assertFalse(result["passed"], result["detail"])
                self.assertLess(result["score"], 0.6, result["detail"])

    def test_decoy_hit_fails_and_costs(self):
        for task in TASKS:
            spec = task_spec(task)
            ws = self.workspace(task, None)
            for decoy in spec["decoys"]:
                with self.subTest(task=task, decoy=decoy["id"]):
                    f, lo, _hi, _tol = reviewlib.resolve_locations(ws, decoy)[0]
                    review = solution(task)
                    review["findings"].append(finding(f, lo, "medium", "security"))
                    result = self.grade(task, review)
                    self.assertFalse(result["passed"], result["detail"])
                    self.assertAlmostEqual(result["score"], 1.0 - reviewlib.DECOY_PENALTY)

    def test_low_severity_everywhere_fails(self):
        for task in TASKS:
            with self.subTest(task=task):
                review = solution(task)
                for item in review["findings"]:
                    item["severity"] = "low"
                result = self.grade(task, review)
                self.assertFalse(result["passed"])
                self.assertLess(result["score"], 0.75)

    def test_false_positive_allowance(self):
        for task in TASKS:
            with self.subTest(task=task):
                review = solution(task)
                allowance = task_spec(task)["fp_allowance"]
                bogus = finding(review["findings"][0]["file"], 1, "medium")
                review["findings"].extend([bogus] * allowance)
                self.assertTrue(self.grade(task, review)["passed"])
                review["findings"].append(bogus)
                self.assertFalse(self.grade(task, review)["passed"])

    def test_one_finding_credits_one_issue(self):
        # cartreview: lines 15 (threshold) and 16 (float rate) are adjacent
        review = {"verdict": "request_changes",
                  "findings": [finding("shopcart/pricing.py", 16, "high")]}
        result = self.grade("cartreview", review)
        credited = [c["case"] for c in result["cases"][:4] if c["passed"]]
        self.assertEqual(credited, ["float_bulk_rate"])

    def test_wrong_category_halves_credit(self):
        review = {"verdict": "request_changes",
                  "findings": [finding("shopcart/pricing.py", 7, "high", "performance")]}
        result = self.grade("cartreview", review)
        self.assertAlmostEqual(result["recall"], 3 * 0.5 / 9, places=3)

    def test_paths_with_prefixes_accepted(self):
        review = solution("cartreview")
        for item in review["findings"]:
            item["file"] = "b/" + item["file"]
        self.assertTrue(self.grade("cartreview", review)["passed"])

    def test_grader_cli_writes_result(self):
        for task in TASKS:
            with self.subTest(task=task):
                ws = self.workspace(task, solution(task))
                out = self.tmp / f"{task}.json"
                proc = subprocess.run(
                    [sys.executable, str(ROOT / "tasks" / task / "grader" / "grade.py"),
                     str(ws), str(out)], capture_output=True, text=True, timeout=60)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertTrue(json.loads(out.read_text())["passed"])


class StarterTestsPass(unittest.TestCase):
    """Visible tests must pass on every starter (they only cover a slice)."""

    COMMANDS = {
        "cartreview": ["tests/test_pricing.py"],
        "notesreview": ["tests/test_api.py"],
        "billingreview": ["-m", "unittest", "discover", "-s", "tests"],
    }

    def test_visible_tests_pass(self):
        for task, args in self.COMMANDS.items():
            with self.subTest(task=task):
                proc = subprocess.run(
                    [sys.executable, "-B", *args], cwd=ROOT / "tasks" / task / "starter",
                    capture_output=True, text=True, timeout=120)
                self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])


class StarterImport(TempDirTestCase, unittest.TestCase):
    """Imports a starter package from a private copy, so the planted bugs
    can be triggered without touching the task tree or sys.modules."""

    def setUp(self):
        self.tmp = self.tmpdir()
        self._saved = (list(sys.path), dict(sys.modules))
        sys.dont_write_bytecode = True

    def tearDown(self):
        sys.path[:] = self._saved[0]
        for name in set(sys.modules) - set(self._saved[1]):
            del sys.modules[name]
        sys.dont_write_bytecode = False

    def use(self, task, package):
        copy_dir = self.tmp / task
        shutil.copytree(ROOT / "tasks" / task / "starter", copy_dir)
        for name in [m for m in sys.modules if m == package or m.startswith(package + ".")]:
            del sys.modules[name]
        sys.path.insert(0, str(copy_dir))
        sys.path.insert(0, str(copy_dir / "tests"))
        return copy_dir


class PlantedCartProblems(StarterImport):
    def test_problems_are_real(self):
        self.use("cartreview", "shopcart")
        from shopcart.models import Cart, Coupon, Item
        from shopcart.pricing import total
        with self.assertRaises(TypeError):  # float BULK_RATE
            total(Cart([Item("a", Decimal("1.00"), 11)]))
        ten = Cart([Item("a", Decimal("1.00"), 10)])
        self.assertEqual(total(ten), Decimal("10.00"))  # README: 5% off
        self.assertLess(total(Cart([Item("a", Decimal("1"), 1)], [Coupon("X", 150)])), 0)
        first, second = Cart(), Cart()
        first.add_coupon(Coupon("TEN", 10))
        self.assertEqual(len(second.coupons), 1)  # shared default list


class PlantedNotesProblems(StarterImport):
    def test_problems_are_real(self):
        self.use("notesreview", "notes")
        from notes.api import App
        from notes.settings import Settings
        from test_api import Client
        clock = [1_700_000_000]
        app = App(Settings(self.tmp / "data"), clock=lambda: clock[0])
        try:
            alice = Client(app).signup_login("alice@example.com")
            bob = Client(app).signup_login("bob@example.com")
            note_id = alice.call("POST", "/notes", {"title": "t", "body": "b"}).body["id"]
            alice.call("POST", f"/notes/{note_id}/attachments",
                       {"name": "a.txt", "content_b64": base64.b64encode(b"x").decode()})
            share = bob.call("POST", f"/notes/{note_id}/shares", {"ttl_hours": 1})
            self.assertEqual(share.status, 201)  # not the owner
            anonymous = Client(app)
            self.assertEqual(anonymous.call("GET", share.body["url"]).status, 404)  # live link
            clock[0] += 7200
            self.assertEqual(anonymous.call("GET", share.body["url"]).status, 200)  # expired
            leak = anonymous.call("GET", share.body["url"] + "/download",
                                  query={"name": "../../notes.db"})
            self.assertTrue(leak.body.startswith(b"SQLite format 3"))
            alice = Client(app).signup_login("alice@example.com")
            alice.call("DELETE", f"/notes/{note_id}")
            self.assertEqual(alice.call("GET", f"/notes/{note_id}").status, 200)
            details = [e["detail"] for e in app.audit.entries() if e["action"] == "share.create"]
            self.assertIn("token=" + share.body["token"], details)
        finally:
            app.conn.close()


class PlantedBillingProblems(StarterImport):
    def test_problems_are_real(self):
        copy_dir = self.use("billingreview", "billing")
        import helpers
        from billing.authz import Role
        from billing.http import Request
        from billing.jobs import dunning
        from billing.money import Money, convert

        self.assertFalse(Role.VIEWER < Role.ADMIN)
        self.assertEqual(convert(Money(1000, "USD"), Decimal("0.9217"), "EUR").amount, 921)

        case = helpers.BillingTestCase()
        case.setUp()
        try:
            app = case.app
            invoice_id = case.open_invoice()
            other = case.user("viewer", tenant=app.create_tenant("globex"))
            self.assertEqual(other.call("GET", f"/invoices/{invoice_id}").status, 200)
            self.assertEqual(other.call("GET", "/invoices/by-number/INV-00001").status, 200)
            other.headers["X-Tenant-Id"] = str(case.tenant)
            self.assertEqual(len(other.call("GET", "/invoices").body["invoices"]), 1)
            self.assertEqual(case.viewer.call("POST", f"/invoices/{invoice_id}/void").status, 200)

            second = case.open_invoice()
            app.payments.sleep = lambda seconds: None
            case.gateway.script = ["decline"]
            payment_id = case.clerk.call("POST", f"/invoices/{second}/pay").body["id"]
            case.gateway.script = ["lost", "ok"]
            dunning.run(app, "2025-12-01")
            self.assertEqual(case.gateway.total_charged("cus_ann"), 2 * 2500)  # double charge

            raw = json.dumps({"id": "evt", "type": "payment.succeeded",
                              "data": {"idempotency_key": "payment-999"}}).encode()
            unsigned = app.handle(Request("POST", "/webhooks/gateway", None, {}, {}, raw))
            self.assertEqual(unsigned.status, 200)

            case.gateway.script = ["timeout"]
            refund = case.admin.call("POST", f"/payments/{payment_id}/refund",
                                     {"amount": 100, "reason": "x"})
            self.assertEqual(refund.body["status"], "succeeded")
        finally:
            case.tearDown()

        # migration 0007 loses account credits: build a 0006 database first
        db = self.tmp / "mig" / "billing.db"
        base = self.tmp / "base_migrations"
        base.mkdir()
        for path in (copy_dir / "billing" / "migrations").glob("000[1-6]_*.py"):
            shutil.copy(path, base / path.name)
        import billing.db as billing_db
        original = billing_db.MIGRATIONS_DIR
        billing_db.MIGRATIONS_DIR = base
        conn = billing_db.connect(db)
        conn.executescript("""
            INSERT INTO tenants (name, base_currency) VALUES ('t', 'EUR');
            INSERT INTO customers (tenant_id, name, email, gateway_ref, created_at)
                VALUES (1, 'c', 'e', 'r', 0);
            INSERT INTO invoices (tenant_id, customer_id, number, currency, status,
                                  due_date, created_at, updated_at)
                VALUES (1, 1, 'INV-1', 'EUR', 'open', '2025-01-01', 0, 0);
            INSERT INTO payments (customer_id, invoice_id, amount_minor, currency, status,
                                  idempotency_key, created_at)
                VALUES (1, 1, 100, 'EUR', 'succeeded', 'payment-1', 0),
                       (1, NULL, 5000, 'EUR', 'succeeded', 'payment-2', 0);
        """)
        conn.close()
        billing_db.MIGRATIONS_DIR = original
        conn = billing_db.connect(db)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0], 1)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
