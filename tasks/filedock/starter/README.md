# filedock

`organize.py` organizes report files from an inbox directory and writes a
manifest describing the work done.

```
python3 organize.py <inbox_dir> <manifest_path>
```

## Input

- `<inbox_dir>` contains plain-text files. Each has a filename of the form
  `report-YYYYMMDD.txt` where `YYYYMMDD` is a valid calendar date.
- Any file in the inbox whose name does not match that pattern, or whose
  date is not a real calendar date, is **left in place** and must not
  appear in the manifest's `moved` or `duplicates` lists. (It is simply
  ignored by this tool.)
- There are no subdirectories in the inbox; only regular files matter.
- Files may be empty. An empty file still counts as a file.

## Output

1. For every valid `report-YYYYMMDD.txt` file: move it to
   `reports/YYYY/MM/` keeping its original filename. `YYYY` is the
   4-digit year, `MM` the 2-digit month of its date. `reports/` is created
   next to the inbox directory (same parent). Directories are created as
   needed. If the destination file already exists (same path), it is
   overwritten with the inbox content.

2. **Duplicates.** Two files with *identical content* (exact bytes) are
   duplicates, even if their names differ. For each duplicate group, the
   file whose filename sorts first lexicographically is the representative
   and is moved; the other files are deleted from the inbox. Duplicates are
   detected across the whole inbox, regardless of date. Only valid
   (pattern-matching, real-date) files take part in duplicate detection
   and in moving.

3. `manifest.json` is written at `<manifest_path>`:

```json
{
  "moved": ["report-20260115.txt", "..."],
  "duplicates": ["report-20260116-b.txt"]
}
```

- `moved`: filenames of files moved to `reports/`, sorted lexicographically.
- `duplicates`: filenames of files deleted as duplicates, sorted
  lexicographically.
- A file appears in exactly one of the two lists.

## Idempotency

Running the tool on an already-processed inbox (no valid files left) must
write `{"moved": [], "duplicates": []}` and change nothing else.

## Rules

- Files that do not match the pattern, and files with impossible dates,
  are never moved or deleted, and never appear in the manifest.
- After the run, the inbox contains only the ignored files.
- The manifest must be valid JSON with exactly the two keys shown.
