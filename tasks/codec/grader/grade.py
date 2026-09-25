#!/usr/bin/env python3
"""Hidden grader for codec.

Runs the submission's encode/decode on unseen payloads (across varint
boundaries, unicode) and feeds corrupted frames that must be rejected.
Byte-exact comparison against the reference frame format.
"""

import json
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference import encode_reference, decode_reference  # noqa: E402

PAYLOADS = [
    ("empty", ""),
    ("short", "hello"),
    ("unicode", "zażółć gęślą jaźń 🚀"),
    ("boundary_126", "x" * 126),
    ("boundary_127", "x" * 127),
    ("boundary_128", "x" * 128),
    ("boundary_129", "x" * 129),
    ("two_bytes", "y" * 300),
    ("max_two_bytes", "z" * 16383),
    ("three_bytes", "w" * 16384),
    ("escapes", '{"text": "a\\"b"}'),
]

BAD_FRAMES = [
    ("bad_magic", b"XX" + b"\x02hi" + struct.pack("<I", zlib.crc32(b"hi"))),
    ("bad_crc", b"MC" + b"\x02hi" + struct.pack("<I", 0xDEADBEEF)),
    ("truncated_payload", b"MC" + b"\x05hi"),
    ("varint_never_ends", b"MC" + b"\x80\x80\x80\x80\x80\x80" + b"hi"),
    ("length_mismatch", b"MC" + b"\x0ahi" + struct.pack("<I", zlib.crc32(b"hi"))),
]


def run(tool, workspace: Path, in_path: Path, out_path: Path):
    proc = subprocess.run(
        [sys.executable, str(workspace / tool), str(in_path), str(out_path)],
        capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main(workspace_arg: str, out_arg: str):
    workspace = Path(workspace_arg)
    out_path = Path(out_arg)

    results = []
    total = 0.0
    earned = 0.0

    for name, text in PAYLOADS:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            in_json = tmp / "in.json"
            in_json.write_text(json.dumps({"text": text}))
            frame_ref = tmp / "ref.bin"
            encode_reference(in_json, frame_ref)
            want_frame = frame_ref.read_bytes()

            frame_got = tmp / "got.bin"
            back_got = tmp / "got.json"
            total += 1
            rc, _, err = run("encode.py", workspace, in_json, frame_got)
            if rc != 0:
                results.append({"case": name, "passed": False,
                                "detail": f"encode exit {rc}: {err[-120:]}"})
                continue
            if frame_got.read_bytes() != want_frame:
                results.append({
                    "case": name, "passed": False,
                    "detail": "frame bytes differ from reference format"})
                continue
            rc, _, err = run("decode.py", workspace, frame_got, back_got)
            if rc != 0:
                results.append({"case": name, "passed": False,
                                "detail": f"decode exit {rc}: {err[-120:]}"})
                continue
            got_obj = json.loads(back_got.read_text())
            if got_obj != {"text": text}:
                results.append({"case": name, "passed": False,
                                "detail": f"json {got_obj!r} != "
                                          f"{{'text': {text!r}}}"})
                continue
            earned += 1
            results.append({"case": name, "passed": True, "detail": ""})

    for name, content in BAD_FRAMES:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bad = tmp / "bad.bin"
            out_json = tmp / "out.json"
            bad.write_bytes(content)
            total += 1
            rc, _, _ = run("decode.py", workspace, bad, out_json)
            if rc != 0 and not out_json.exists():
                earned += 1
                results.append({"case": name, "passed": True, "detail": ""})
            else:
                results.append({"case": name, "passed": False,
                                "detail": f"rc={rc}, output exists="
                                          f"{out_json.exists()}"})

    score = earned / total if total else 0.0
    passed = all(r["passed"] for r in results)
    detail = "all hidden cases passed" if passed else "; ".join(
        f"{r['case']}: {r['detail']}" for r in results if not r["passed"])
    result = {"passed": passed, "score": round(score, 3), "detail": detail,
              "cases": results}
    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
