# Share links and note sorting (NOTES-58)

Product wants read-only share links: the owner of a note creates a link
that works without logging in and expires after `ttl_hours` (README,
"Share links").

- New `shares` table (migration 3) holding the token, note, creator and
  expiry.
- `POST /notes/<id>/shares` creates a link with a random 192-bit token;
  `GET /s/<token>` shows the note and `GET /s/<token>/download?name=`
  serves one attachment. Both are intentionally unauthenticated.
- `NoteRepo.get_by_id()` looks a note up by id alone, since share links
  have no user context. `owned_note()` now reuses it and checks the owner
  itself, so the ownership rule lives in one place.
- `GET /notes` accepts `sort=created|updated|title`. The ORDER BY clause
  comes from the fixed `SORT_COLUMNS` table; unknown values are rejected
  with 400 before reaching SQL.
- Share creation is recorded in the audit log.

Tests: added sorting and share-creation tests; all tests pass.
