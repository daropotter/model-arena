"""Oracle tests for the codec task.

Frames are built by hand from literal LEB128 bytes plus struct/zlib, so the
reference decoder is exercised independently of the reference encoder.
"""

import importlib.util
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

from tests.support import ROOT, TempDirTestCase

GRADER = ROOT / "tasks" / "codec" / "grader"


def _load_reference():
    if str(GRADER) not in sys.path:
        sys.path.insert(0, str(GRADER))
    spec = importlib.util.spec_from_file_location(
        "codec_grader_reference", GRADER / "reference.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REF = _load_reference()


def _leb128(value):
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _frame(payload, length=None, crc=None):
    if length is None:
        length = _leb128(len(payload))
    if crc is None:
        crc = zlib.crc32(payload)
    return b"MC" + length + payload + struct.pack("<I", crc)


VARINT_TABLE = [
    (0, b"\x00"),
    (1, b"\x01"),
    (127, b"\x7f"),
    (128, b"\x80\x01"),
    (129, b"\x81\x01"),
    (300, b"\xac\x02"),
    (16383, b"\xff\x7f"),
    (16384, b"\x80\x80\x01"),
    (2 ** 32 - 1, b"\xff\xff\xff\xff\x0f"),
]


class VarintTests(unittest.TestCase):
    def test_hand_encoded_varints_decode(self):
        for value, raw in VARINT_TABLE:
            with self.subTest(value=value, raw=raw):
                self.assertEqual(REF.decode_varint(raw, 0), (value, len(raw)))

    def test_varint_decodes_at_offset(self):
        for value, raw in VARINT_TABLE:
            with self.subTest(value=value, raw=raw):
                prefixed = b"MC" + raw
                self.assertEqual(REF.decode_varint(prefixed, 2),
                                 (value, 2 + len(raw)))

    def test_reference_encoder_matches_hand_bytes(self):
        for value, raw in VARINT_TABLE:
            with self.subTest(value=value, raw=raw):
                self.assertEqual(REF.encode_varint(value), raw)

    def test_literal_bytes_for_common_lengths(self):
        self.assertEqual(_leb128(0), b"\x00")
        self.assertEqual(_leb128(127), b"\x7f")
        self.assertEqual(_leb128(128), b"\x80\x01")
        self.assertEqual(_leb128(300), b"\xac\x02")
        self.assertEqual(_leb128(16384), b"\x80\x80\x01")


class DecodeAcceptanceTests(unittest.TestCase):
    def decode(self, raw):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.bin"
            out = Path(tmp) / "out.json"
            src.write_bytes(raw)
            REF.decode_reference(src, out)
            return json.loads(out.read_text())

    def test_compact_json_payload(self):
        raw = _frame(b'{"text":"compact"}')
        self.assertEqual(self.decode(raw), {"text": "compact"})

    def test_whitespace_json_payload(self):
        raw = _frame(b' { "text" : "spaces" }\n')
        self.assertEqual(self.decode(raw), {"text": "spaces"})

    def test_empty_text(self):
        self.assertEqual(self.decode(_frame(b'{"text":""}')), {"text": ""})

    def test_unicode_text(self):
        payload = '{"text":"zażółć 🚀"}'.encode("utf-8")
        self.assertEqual(self.decode(_frame(payload)),
                         {"text": "zażółć 🚀"})

    def test_two_byte_length_manual(self):
        text = "y" * 300
        payload = json.dumps({"text": text}).encode("utf-8")
        self.assertEqual(REF.decode_varint(_leb128(len(payload)), 0),
                         (len(payload), len(_leb128(len(payload)))))
        self.assertEqual(self.decode(_frame(payload)), {"text": text})

    def test_three_byte_length_manual(self):
        text = "w" * 16384
        payload = json.dumps({"text": text}).encode("utf-8")
        self.assertEqual(self.decode(_frame(payload)), {"text": text})

    def test_escaped_json_text(self):
        raw = _frame(b'{"text": "a\\"b"}')
        self.assertEqual(self.decode(raw), {"text": 'a"b'})


class DecodeRejectionTests(unittest.TestCase):
    def assert_rejected(self, raw):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.bin"
            out = Path(tmp) / "out.json"
            src.write_bytes(raw)
            with self.assertRaises(ValueError):
                REF.decode_reference(src, out)
            self.assertFalse(out.exists())

    def test_bad_magic(self):
        valid = _frame(b'{"text":"x"}')
        self.assert_rejected(b"XX" + valid[2:])

    def test_bad_crc(self):
        self.assert_rejected(_frame(b'{"text":"x"}', crc=0xDEADBEEF))

    def test_truncated_varint(self):
        self.assert_rejected(b"MC\x80")

    def test_six_byte_varint(self):
        self.assert_rejected(b"MC" + b"\x80" * 5 + b"\x00" + b"hi")

    def test_varint_never_terminates(self):
        self.assert_rejected(b"MC" + b"\x80" * 6 + b"hi")

    def test_varint_value_above_uint32(self):
        self.assert_rejected(b"MC" + b"\xff\xff\xff\xff\x10" + b"hi" +
                             struct.pack("<I", zlib.crc32(b"hi")))

    def test_varint_value_is_two_to_the_32(self):
        self.assert_rejected(b"MC" + b"\x80\x80\x80\x80\x10" + b"hi" +
                             struct.pack("<I", zlib.crc32(b"hi")))

    def test_length_longer_than_payload(self):
        self.assert_rejected(b"MC" + _leb128(10) + b"hi" +
                             struct.pack("<I", zlib.crc32(b"hi")))

    def test_length_shorter_than_payload(self):
        self.assert_rejected(b"MC" + _leb128(1) + b"hi" +
                             struct.pack("<I", zlib.crc32(b"h")))

    def test_trailing_bytes(self):
        self.assert_rejected(_frame(b'{"text":"x"}') + b"junk")

    def test_truncated_crc_field(self):
        self.assert_rejected(_frame(b'{"text":"x"}')[:-1])

    def test_empty_payload(self):
        self.assert_rejected(_frame(b""))

    def test_invalid_utf8(self):
        self.assert_rejected(_frame(b'\xff'))

    def test_invalid_json(self):
        self.assert_rejected(_frame(b"{"))

    def test_json_scalar(self):
        self.assert_rejected(_frame(b"1"))

    def test_json_array(self):
        self.assert_rejected(_frame(b'["text"]'))

    def test_json_extra_key(self):
        self.assert_rejected(_frame(b'{"text":"x","extra":1}'))

    def test_json_non_string_value(self):
        self.assert_rejected(_frame(b'{"text":1}'))

    def test_json_nested_value(self):
        self.assert_rejected(_frame(b'{"text":{"a":1}}'))

    def test_json_null_value(self):
        self.assert_rejected(_frame(b'{"text":null}'))


class ReferenceEncoderTests(unittest.TestCase):
    def test_reference_encoder_frame_is_well_formed(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.json"
            dst = Path(tmp) / "out.bin"
            src.write_text(json.dumps({"text": "hello"}))
            REF.encode_reference(src, dst)
            raw = dst.read_bytes()
            self.assertEqual(raw[:2], b"MC")
            length, pos = REF.decode_varint(raw, 2)
            payload = raw[pos:pos + length]
            self.assertEqual(len(payload), length)
            self.assertEqual(json.loads(payload.decode("utf-8")),
                             {"text": "hello"})
            self.assertEqual(len(raw) - pos - length, 4)
            crc = struct.unpack("<I", raw[pos + length:])[0]
            self.assertEqual(crc, zlib.crc32(payload))

    def test_reference_encoder_rejects_bad_objects(self):
        bad_values = [[], {}, {"text": 1}, {"text": True},
                      {"text": "x", "extra": 1}]
        for value in bad_values:
            with self.subTest(value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    src = Path(tmp) / "in.json"
                    dst = Path(tmp) / "out.bin"
                    src.write_text(json.dumps(value))
                    with self.assertRaises(ValueError):
                        REF.encode_reference(src, dst)


class CodecGraderTests(TempDirTestCase, unittest.TestCase):
    def _workspace_from_solution(self, name):
        workspace = self.tmpdir() / name
        shutil.copytree(ROOT / "tasks" / "codec" / "solution", workspace,
                        ignore=shutil.ignore_patterns("__pycache__"))
        return workspace

    def test_shipped_solution_passes_grader(self):
        from runner.verify_tasks import grade_locally
        workspace = self._workspace_from_solution("solution-ws")
        result = grade_locally(ROOT / "tasks" / "codec", workspace)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["score"], 1.0)

    def test_compact_json_encoder_variant_still_passes_grader(self):
        from runner.verify_tasks import grade_locally
        workspace = self._workspace_from_solution("compact-ws")
        encode_path = workspace / "encode.py"
        original = encode_path.read_text()
        self.assertIn("json.dumps(obj)", original)
        encode_path.write_text(original.replace(
            "json.dumps(obj)",
            'json.dumps(obj, separators=(",", ":"))'))
        result = grade_locally(ROOT / "tasks" / "codec", workspace)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["score"], 1.0)

    def test_compact_variant_writes_compact_payload(self):
        workspace = self._workspace_from_solution("compact-check-ws")
        encode_path = workspace / "encode.py"
        original = encode_path.read_text()
        encode_path.write_text(original.replace(
            "json.dumps(obj)",
            'json.dumps(obj, separators=(",", ":"))'))
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.json"
            dst = Path(tmp) / "out.bin"
            src.write_text(json.dumps({"text": "hi"}))
            proc = subprocess.run(
                [sys.executable, str(encode_path), str(src), str(dst)],
                capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            raw = dst.read_bytes()
            length, pos = REF.decode_varint(raw, 2)
            payload = raw[pos:pos + length]
            self.assertEqual(payload, b'{"text":"hi"}')
            self.assertEqual(raw[pos + length:],
                             struct.pack("<I", zlib.crc32(payload)))


if __name__ == "__main__":
    unittest.main()
