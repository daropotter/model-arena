"""Shared scoring for the code-review tasks (cartreview, notesreview,
billingreview). Every copy of this file must stay byte-identical; the
oracle suite checks that.

The candidate writes `review.json` (format in the workspace REVIEW.md).
Each task's `issues.json` lists planted problems, decoys (diff lines that
look suspicious but are correct and intended) and neutral spots (real but
unplanted nits that neither earn nor cost anything).

A location is an anchor string, unique in its file, plus a line span
around the anchor; a finding hits a location when its file matches and
its line falls inside the span widened by the location's tolerance
(LINE_TOLERANCE unless the location sets its own). Anchors are
resolved against the workspace, whose reviewed files are protected.

Scoring:
  * findings are assigned to issues one-to-one by maximum total weight
    (weights: high 3, medium 2, low 1); a finding's credit is the
    severity factor (at or above the required severity 1.0, one level
    below 0.5, two below 0.25) times 0.5 when its category is not one of
    the accepted categories;
  * further findings that also hit an already credited issue are
    duplicates: neither credit nor penalty;
  * findings hitting a decoy cost DECOY_PENALTY; any other unmatched
    finding costs FP_PENALTY (FP_PENALTY_LOW for severity low);
  * score = 0.85 * recall - penalties + 0.15 * (verdict correct),
    clamped to [0, 1]; more than max_findings findings scores 0.
Passing requires full credit on every `must` issue, recall >= min_recall,
no decoy hits, at most fp_allowance unmatched medium/high findings and
the correct verdict.
"""

import json
from pathlib import Path

SEVERITIES = {"low": 0, "medium": 1, "high": 2}
WEIGHTS = {"low": 1, "medium": 2, "high": 3}
CATEGORIES = {
    "correctness", "security", "behavior-change", "error-handling",
    "data-integrity", "concurrency", "performance", "maintainability",
}
VERDICTS = {"approve", "request_changes"}
LINE_TOLERANCE = 1
FP_PENALTY = 0.06
FP_PENALTY_LOW = 0.02
DECOY_PENALTY = 0.15
SEVERITY_FACTOR = {0: 1.0, 1: 0.5, 2: 0.25}


class SpecError(Exception):
    """issues.json does not resolve against the workspace (grader bug or
    a tampered workspace)."""


def resolve_locations(workspace, entry):
    spans = []
    for loc in entry["locations"]:
        path = workspace / loc["file"]
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise SpecError(f"{entry['id']}: cannot read {loc['file']}: {exc}")
        hits = [i + 1 for i, text in enumerate(lines) if loc["anchor"] in text]
        if len(hits) != 1:
            raise SpecError(f"{entry['id']}: anchor {loc['anchor']!r} found "
                            f"{len(hits)} times in {loc['file']}")
        line = hits[0]
        spans.append((loc["file"], line - loc.get("before", 0),
                      line + loc.get("after", 0),
                      loc.get("tolerance", LINE_TOLERANCE)))
    return spans


def normalize_file(name):
    name = name.strip().replace("\\", "/")
    for prefix in ("./", "a/", "b/", "/workspace/"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def hits(finding, spans):
    return any(finding["file"] == f and lo - tol <= finding["line"] <= hi + tol
               for f, lo, hi, tol in spans)


def parse_review(path):
    """Return (review, problems). review is None when unusable."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, ["review.json missing"]
    except (OSError, ValueError) as exc:
        return None, [f"review.json unreadable: {exc}"]
    if not isinstance(raw, dict):
        return None, ["review.json is not an object"]
    problems = []
    verdict = raw.get("verdict")
    if verdict not in VERDICTS:
        problems.append(f"invalid verdict {verdict!r}")
        verdict = None
    findings_raw = raw.get("findings")
    if not isinstance(findings_raw, list):
        return None, problems + ["findings is not a list"]
    findings = []
    for idx, item in enumerate(findings_raw):
        why = None
        if not isinstance(item, dict):
            why = "not an object"
        elif not isinstance(item.get("file"), str) or not item["file"].strip():
            why = "missing file"
        elif type(item.get("line")) is not int or item["line"] < 1:
            why = "line must be a positive integer"
        elif item.get("severity") not in SEVERITIES:
            why = f"invalid severity {item.get('severity')!r}"
        elif item.get("category") not in CATEGORIES:
            why = f"invalid category {item.get('category')!r}"
        elif not isinstance(item.get("title"), str) or not item["title"].strip():
            why = "missing title"
        elif (not isinstance(item.get("explanation"), str)
              or len(item["explanation"].strip()) < 20):
            why = "explanation shorter than 20 characters"
        if why:
            problems.append(f"finding {idx}: {why}")
            findings.append({"index": idx, "invalid": True,
                             "file": "", "line": 0, "severity": "medium",
                             "category": ""})
            continue
        findings.append({"index": idx, "invalid": False,
                         "file": normalize_file(item["file"]),
                         "line": item["line"], "severity": item["severity"],
                         "category": item["category"],
                         "title": item["title"].strip()})
    return {"verdict": verdict, "findings": findings}, problems


def credit_for(finding, issue):
    gap = SEVERITIES[issue["severity"]] - SEVERITIES[finding["severity"]]
    factor = SEVERITY_FACTOR.get(max(gap, 0), 0.0)
    if finding["category"] not in issue["categories"]:
        factor *= 0.5
    return factor


def best_assignment(findings, issues, candidates):
    """Max-weight one-to-one matching of findings to issues (DP over the
    set of used issues; sizes are small)."""
    memo = {}

    def go(i, used):
        if i == len(findings):
            return 0.0, ()
        key = (i, used)
        if key in memo:
            return memo[key]
        best = go(i + 1, used)
        for j in candidates[i]:
            if used & (1 << j):
                continue
            value = WEIGHTS[issues[j]["severity"]] * credit_for(findings[i], issues[j])
            rest, picks = go(i + 1, used | (1 << j))
            if value + rest > best[0] + 1e-12:
                best = (value + rest, ((i, j),) + picks)
        memo[key] = best
        return best

    return go(0, 0)[1]


def grade(workspace, spec):
    workspace = Path(workspace)
    issues = spec["issues"]
    for entry in issues + spec.get("decoys", []) + spec.get("neutral", []):
        entry["spans"] = resolve_locations(workspace, entry)

    review, problems = parse_review(workspace / "review.json")
    cases = []
    if review is None:
        detail = "; ".join(problems)
        for issue in issues:
            cases.append({"case": issue["id"], "passed": False,
                          "detail": "no usable review"})
        return {"passed": False, "score": 0.0, "detail": detail,
                "cases": cases}

    findings = review["findings"]
    if len(findings) > spec["max_findings"]:
        return {"passed": False, "score": 0.0,
                "detail": f"{len(findings)} findings exceed the limit of "
                          f"{spec['max_findings']}",
                "cases": [{"case": i["id"], "passed": False,
                           "detail": "too many findings"} for i in issues]}

    valid = [f for f in findings if not f["invalid"]]
    candidates = [[j for j, issue in enumerate(issues) if hits(f, issue["spans"])]
                  for f in valid]
    assignment = best_assignment(valid, issues, candidates)
    credit = {j: credit_for(valid[i], issues[j]) for i, j in assignment}
    assigned = {i for i, _ in assignment}

    penalties = 0.0
    decoy_hits, unmatched_serious, notes = [], 0, []
    for i, finding in enumerate(valid):
        if i in assigned or candidates[i]:
            continue  # credited, or a duplicate of a planted issue
        decoy = next((d for d in spec.get("decoys", [])
                      if hits(finding, d["spans"])), None)
        if decoy:
            penalties += DECOY_PENALTY
            decoy_hits.append(decoy["id"])
            notes.append(f"finding {finding['index']} flags correct code "
                         f"({decoy['id']}: {decoy['title']})")
            continue
        if any(hits(finding, n["spans"]) for n in spec.get("neutral", [])):
            continue
        if finding["severity"] == "low":
            penalties += FP_PENALTY_LOW
        else:
            penalties += FP_PENALTY
            unmatched_serious += 1
        notes.append(f"finding {finding['index']} ({finding['file']}:"
                     f"{finding['line']}) matches no known problem")
    for finding in findings:
        if finding["invalid"]:
            penalties += FP_PENALTY
            unmatched_serious += 1

    total_weight = sum(WEIGHTS[i["severity"]] for i in issues)
    recall = sum(WEIGHTS[issues[j]["severity"]] * c
                 for j, c in credit.items()) / total_weight
    verdict_ok = review["verdict"] == spec["verdict"]

    for j, issue in enumerate(issues):
        c = credit.get(j, 0.0)
        if c >= 1.0:
            detail = ""
        elif c > 0:
            detail = f"found with partial credit {c:g} (severity/category)"
        else:
            detail = "not found"
        cases.append({"case": issue["id"], "passed": c >= 1.0,
                      "detail": detail, "title": issue["title"],
                      "must": bool(issue.get("must"))})
    cases.append({"case": "verdict", "passed": verdict_ok,
                  "detail": "" if verdict_ok else
                  f"verdict {review['verdict']!r}, expected {spec['verdict']!r}"})
    cases.append({"case": "no_decoy_hits", "passed": not decoy_hits,
                  "detail": ", ".join(decoy_hits)})
    cases.append({"case": "false_positives",
                  "passed": unmatched_serious <= spec["fp_allowance"],
                  "detail": f"{unmatched_serious} unmatched medium/high or "
                            f"invalid findings (allowed {spec['fp_allowance']})"})

    score = 0.85 * recall - penalties + (0.15 if verdict_ok else 0.0)
    score = min(1.0, max(0.0, score))
    must_ok = all(credit.get(j, 0.0) >= 1.0
                  for j, issue in enumerate(issues) if issue.get("must"))
    passed = (must_ok and recall >= spec["min_recall"] - 1e-9 and not decoy_hits
              and unmatched_serious <= spec["fp_allowance"] and verdict_ok)

    missed = [c["case"] for c in cases[:len(issues)] if not c["passed"]]
    parts = [f"recall {recall:.2f}", f"penalties {penalties:.2f}",
             f"verdict {'ok' if verdict_ok else 'wrong'}"]
    if missed:
        parts.append("missed/partial: " + ", ".join(missed))
    parts.extend(problems + notes)
    return {"passed": passed, "score": round(score, 3),
            "detail": "; ".join(parts), "cases": cases,
            "recall": round(recall, 3), "penalties": round(penalties, 3)}


def main(argv, spec_path):
    workspace, out_path = Path(argv[1]), Path(argv[2])
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    try:
        result = grade(workspace, spec)
    except SpecError as exc:
        result = {"passed": False, "score": 0.0,
                  "detail": f"workspace does not match the reviewed change: {exc}",
                  "cases": []}
    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0
