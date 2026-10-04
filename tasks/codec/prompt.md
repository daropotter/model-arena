You are working in /workspace.

`encode.py` and `decode.py` implement a binary frame format. They have bugs:
the CRC is computed over the wrong bytes and the length field breaks for
payloads longer than 127 bytes.

Read SPEC.md: it defines the frame layout, the varint encoding and the CRC
rules exactly. Fix both tools so they match it. The encoder may choose any
valid JSON serialization allowed by the spec; frames are graded semantically,
not against one particular JSON byte representation.

The visible tests cover only a short payload. Hidden tests exercise payloads
across the varint boundaries (0, 1, 127, 128, 16384 bytes), Unicode text,
and corrupted frames that must be rejected using the specified error contract.

Do not modify SPEC.md or tests/. Use relative paths only.

Verify your fix by round-tripping a few payloads yourself:

    python3 encode.py in.json out.bin
    python3 decode.py out.bin back.json
    python3 tests/test_visible.py
