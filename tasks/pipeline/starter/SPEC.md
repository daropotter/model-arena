# pipeline format spec

This document is the authoritative contract. Where the implementation and
this document disagree, this document wins.

Two CLIs:

```
python3 pack.py <in.json> <out.pipe>
python3 unpack.py <in.pipe> <out.json>
```

`pack.py` reads a JSON object and writes a pipe file. `unpack.py` reads a
pipe file and writes the JSON object back. The round trip is exact:
`unpack(pack(x)) == x` for every valid input.

## Input JSON

- The input is a JSON **object** (mapping string keys to values).
- Values may be: strings, integers, floats, booleans, or null. No lists,
  no nested objects.

## Pipe format

1. The first line is exactly `pipe1` followed by a newline.
2. One line per entry, keys sorted lexicographically (byte order of the
   *unescaped* key). Each line is:

```
<escaped-key><TAB><typecode><escaped-value><LF>
```

3. Typecodes: `s` string, `i` integer, `f` float, `b` boolean, `n` null.
4. Escaping (used for keys and for `s` values), applied in this order:
   - `\` → `\\`
   - TAB → `\t`
   - newline → `\n`
   - carriage return → `\r`

5. `i` values are written as plain decimal digits with an optional leading
   `-`. `f` values are written with `repr(float)` (e.g. `0.5`, `1000.0`,
   `1e-05`); `unpack.py` restores them with `float(...)`. `b` values are
   `true` or `false`. `n` values are the empty string.

## Unpack rules

- The first line must be exactly `pipe1`; anything else is an error.
- Every other line must contain at least one TAB; the part before the
  first TAB is the escaped key, the rest is `<typecode><escaped-value>`.
- Unescaping must reverse the rules above. `\` followed by any character
  other than `\`, `t`, `n`, `r` is an invalid escape and an error.
- Invalid typecode, malformed `i`/`f`/`b`/`n` value, missing TAB — all
  errors.
- The output JSON is written to `<out.json>` (any key order, valid JSON).

## Errors

On any error (bad input JSON, malformed pipe file), print `error` to
stderr and exit 1.
