"""Check proposal IDs, counts and quotations of agent-visible rules.

This validates the proposal's traceability, not benchmark correctness.
"""

import json
import re
from collections import Counter
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    data = json.loads((root / "requirements.json").read_text())
    requirements = data["requirements"]
    expected = {"functional": 24, "process": 12, "artifacts": 10,
                "tools": 6, "negative": 8, "regression": 4}
    assert data["status"] == "proposal-not-runnable"
    assert len(requirements) == data["requirement_count"] == 64
    assert Counter(row["category"] for row in requirements) == expected
    assert len({row["id"] for row in requirements}) == len(requirements)
    for row in requirements:
        assert re.fullmatch(r"[FPATNR][0-9]{2}", row["id"]), row["id"]
        assert row["source"] in ("prompt.md", "SPEC.md")
        source = (root / row["source"]).read_text()
        # Markdown line wrapping must not change the source relationship.
        assert " ".join(row["anchor"].split()) in " ".join(source.split()), (
            row["id"], row["anchor"])
        assert row["criterion"] and row["evidence"] and row["applicability"]
    for path in root.glob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            assert (path.parent / target).exists(), (path.name, target)
    print("Proposal OK: 64 unique requirements, category counts, source anchors and links")


if __name__ == "__main__":
    main()
