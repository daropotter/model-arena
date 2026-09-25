# codec frame format spec

This document is the authoritative contract. Where the implementation and
this document disagree, this document wins.

Two CLIs:

```
python3 encode.py <in.json> <out.bin>
python3 decode.py <in.bin> <out.json>
```

`encode.py` reads a JSON object and writes a binary frame. `decode.py`
reads a binary frame and writes the JSON object back. The round trip is
exact: `decode(encode(x)) == x` for every valid input.

## Input JSON

The input is a JSON object with exactly one key, `text`, whose value is a
string.

## Frame layout (all integers little-endian)

```
+----------+--------+-----------+----------+
| magic 2B | length | payload   | crc32 4B |
+----------+--------+-----------+----------+
```

1. **magic**: bytes `0x4d 0x43` (`b"MC"`).
2. **length**: the payload length in bytes as an unsigned LEB128 varint:
   - 7 bits per byte, least significant first;
   - the high bit (0x80) is set on every byte except the last;
   - lengths below 128 use one byte, up to 16383 use two, etc.
   - a varint longer than 5 bytes, or one that would exceed 2^32-1, is
     invalid.
3. **payload**: the JSON object serialized as UTF-8 with `json.dumps(obj)`
   (the encoder may use any valid JSON serialization; the decoder must
   accept any valid UTF-8 JSON object with the required shape).
4. **crc32**: `zlib.crc32(payload_bytes)` as 4 bytes little-endian.

## Decode rules

- Wrong magic: error.
- Malformed varint (longer than 5 bytes, or truncated before the payload):
  error.
- Length that does not match the actual remaining payload bytes: error.
- CRC mismatch: error.
- Payload that is not a valid UTF-8 JSON object with the `text` key (the
  only key): error.
- On success the output JSON is written to `<out.json>` (any key order,
  valid JSON, exact `{"text": ...}` content).

## Errors

On any error print `error` to stderr and exit 1. The exact message on
stderr is not graded; the exit code and the absence of the output file are.
