#!/usr/bin/env python3
"""Hidden semantic grader for codec."""

import json
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference import decode_varint, encode_varint  # noqa: E402

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
    ("controls", "line one\nline two\t\u0000"),
]
MAX_OUTPUT = 2_000_000


def frame(payload: bytes, length: bytes = None, crc: int = None) -> bytes:
    length = encode_varint(len(payload)) if length is None else length
    crc = zlib.crc32(payload) if crc is None else crc
    return b"MC" + length + payload + struct.pack("<I", crc)


VALID_FRAMES = [
    ("decode_compact_json", frame(b'{"text":"compact"}'), "compact"),
    ("decode_whitespace_json", frame(b' { "text" : "spaces" }\n'), "spaces"),
    ("decode_utf8_json", frame('{"text":"🚀"}'.encode()), "🚀"),
]

BAD_FRAMES = [
    ("bad_magic", b"XX" + b"\x02hi" + struct.pack("<I", zlib.crc32(b"hi"))),
    ("bad_crc", b"MC" + b"\x02hi" + struct.pack("<I", 0xDEADBEEF)),
    ("truncated_payload", b"MC" + b"\x05hi"),
    ("truncated_varint", b"MC\x80"),
    ("varint_never_ends", b"MC" + b"\x80" * 6 + b"hi"),
    ("uint32_overflow", b"MC\xff\xff\xff\xff\x10"),
    ("uint32_max_with_no_payload", b"MC\xff\xff\xff\xff\x0f"),
    ("length_mismatch", b"MC" + b"\x0ahi" + struct.pack("<I", zlib.crc32(b"hi"))),
    ("trailing_bytes", frame(b'{"text":"x"}') + b"junk"),
    ("invalid_utf8", frame(b'\xff')),
    ("invalid_json", frame(b'{')),
    ("payload_array", frame(b'["text"]')),
    ("payload_extra_key", frame(b'{"text":"x","extra":1}')),
    ("payload_non_string", frame(b'{"text":1}')),
]

BAD_INPUTS = [
    ("encode_array", []),
    ("encode_missing_key", {}),
    ("encode_extra_key", {"text": "x", "extra": 1}),
    ("encode_non_string", {"text": 1}),
    ("encode_bool", {"text": True}),
]


def run(tool: str, workspace: Path, in_path: Path, out_path: Path):
    try:
        proc = subprocess.run(
            [sys.executable, str(workspace / tool), str(in_path), str(out_path)],
            capture_output=True, text=True, timeout=15,
        )
        return proc.returncode, proc.stdout, proc.stderr, ""
    except subprocess.TimeoutExpired:
        return None, "", "", "timed out"
    except OSError as exc:
        return None, "", "", f"could not execute {tool}: {exc}"


def read_limited(path: Path, binary=False):
    try:
        if path.stat().st_size > MAX_OUTPUT:
            return None, "output is too large"
        return (path.read_bytes() if binary else path.read_text()), ""
    except (OSError, UnicodeError) as exc:
        return None, f"output unreadable: {exc}"


def parse_frame(raw: bytes):
    if raw[:2] != b"MC":
        raise ValueError("bad magic")
    length, pos = decode_varint(raw, 2)
    end = pos + length
    if end > len(raw) or len(raw) - end != 4:
        raise ValueError("length mismatch")
    payload = raw[pos:end]
    if struct.unpack("<I", raw[end:])[0] != zlib.crc32(payload):
        raise ValueError("crc mismatch")
    obj = json.loads(payload.decode("utf-8"))
    if (not isinstance(obj, dict) or set(obj) != {"text"}
            or not isinstance(obj["text"], str)):
        raise ValueError("bad payload shape")
    return obj


def error_contract(rc, stderr, out_path: Path, run_error: str):
    if run_error:
        return False, run_error
    if rc != 1:
        return False, f"expected exit 1, got {rc}"
    if stderr.strip() != "error":
        return False, f"stderr must be 'error', got {stderr[-120:]!r}"
    if out_path.exists():
        return False, "output file exists after error"
    return True, ""


def main(workspace_arg: str, out_arg: str):
    workspace = Path(workspace_arg)
    out_path = Path(out_arg)
    results = []

    def record(name, passed, detail=""):
        results.append({"case": name, "passed": passed, "detail": detail})

    for name, text in PAYLOADS:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            in_json = tmp / "in.json"
            encoded = tmp / "encoded.bin"
            decoded = tmp / "decoded.json"
            expected = {"text": text}
            in_json.write_text(json.dumps(expected))

            rc, _, err, run_error = run("encode.py", workspace, in_json, encoded)
            if run_error or rc != 0:
                record(name, False, run_error or f"encode exit {rc}: {err[-120:]}")
                continue
            raw, detail = read_limited(encoded, binary=True)
            try:
                encoded_obj = parse_frame(raw) if raw is not None else None
            except (ValueError, UnicodeError, json.JSONDecodeError, struct.error) as exc:
                encoded_obj = None
                detail = f"invalid encoded frame: {exc}"
            if encoded_obj != expected:
                record(name, False, detail or f"encoded payload was {encoded_obj!r}")
                continue

            rc, _, err, run_error = run("decode.py", workspace, encoded, decoded)
            if run_error or rc != 0:
                record(name, False, run_error or f"decode exit {rc}: {err[-120:]}")
                continue
            text_out, detail = read_limited(decoded)
            try:
                got = json.loads(text_out) if text_out is not None else None
            except json.JSONDecodeError as exc:
                got = None
                detail = f"decoder output is not JSON: {exc}"
            ok = isinstance(got, dict) and set(got) == {"text"} and got == expected
            record(name, ok, "" if ok else detail or f"decoded {got!r}")

    for name, content, expected_text in VALID_FRAMES:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            source, output = tmp / "in.bin", tmp / "out.json"
            source.write_bytes(content)
            rc, _, err, run_error = run("decode.py", workspace, source, output)
            detail = run_error or (f"decode exit {rc}: {err[-120:]}" if rc != 0 else "")
            got = None
            if not detail:
                text_out, detail = read_limited(output)
                try:
                    got = json.loads(text_out) if text_out is not None else None
                except json.JSONDecodeError as exc:
                    detail = f"decoder output is not JSON: {exc}"
            ok = not detail and isinstance(got, dict) and set(got) == {"text"} \
                and got == {"text": expected_text}
            record(name, ok, "" if ok else detail or f"decoded {got!r}")

    for name, content in BAD_FRAMES:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            source, output = tmp / "bad.bin", tmp / "out.json"
            source.write_bytes(content)
            rc, _, err, run_error = run("decode.py", workspace, source, output)
            ok, detail = error_contract(rc, err, output, run_error)
            record(name, ok, detail)

    for name, value in BAD_INPUTS:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            source, output = tmp / "bad.json", tmp / "out.bin"
            source.write_text(json.dumps(value))
            rc, _, err, run_error = run("encode.py", workspace, source, output)
            ok, detail = error_contract(rc, err, output, run_error)
            record(name, ok, detail)

    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        source, output = tmp / "bad.json", tmp / "out.bin"
        source.write_text("{")
        rc, _, err, run_error = run("encode.py", workspace, source, output)
        ok, detail = error_contract(rc, err, output, run_error)
        record("encode_malformed_json", ok, detail)

    earned = sum(case["passed"] for case in results)
    score = earned / len(results) if results else 0.0
    passed = all(case["passed"] for case in results)
    detail = "all hidden cases passed" if passed else "; ".join(
        f"{case['case']}: {case['detail']}" for case in results
        if not case["passed"])
    result = {"passed": passed, "score": round(score, 3), "detail": detail,
              "cases": results}
    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
