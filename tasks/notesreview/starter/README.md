# notes

A small multi-user notes service. `notes.api.App(settings).handle(request)`
takes a `notes.http.Request` and returns a `notes.http.Response`; the HTTP
transport is out of scope. Bodies are JSON objects; errors are
`{"error": message}` with the status below.

## Authentication

`POST /signup {"email", "password"}` creates an account (201 `{"id"}`,
409 if the email is taken). `POST /login` returns `{"token"}`; send it as
`Authorization: Bearer <token>`. Sessions expire after `session_ttl`.
Missing or invalid tokens get 401.

## Notes

A note belongs to the user who created it. **Only its owner can read,
change, delete or attach to it**; for anybody else the note does not exist
(404, never 403, so ids cannot be probed).

| request | result |
|---|---|
| `GET /notes?limit=N&sort=S` | the caller's notes; `limit` 1..`page_limit` (default `page_limit`); `sort` is `created` (default, newest first), `updated` (most recently changed first) or `title` (A to Z, case-insensitive); anything else is 400 |
| `POST /notes {"title", "body"}` | 201, the note |
| `GET /notes/<id>` | the note plus `attachments`, a sorted list of names |
| `PATCH /notes/<id> {"title"?, "body"?}` | the updated note |
| `DELETE /notes/<id>` | 204; soft delete |

A deleted note is gone for every reader: all endpoints answer 404 for it,
and its attachments can no longer be downloaded.

## Attachments

`POST /notes/<id>/attachments {"name", "content_b64"}` stores a file
(201). `GET /notes/<id>/attachments/<name>` returns its bytes. Names are
plain file names (`[A-Za-z0-9][A-Za-z0-9._-]*`, no `..`, at most 100
characters); anything else is 400. Files never leave the note's own
attachment folder.

## Share links

The owner of a note can publish it read-only:

- `POST /notes/<id>/shares {"ttl_hours"?}` (owner only, like every other
  note endpoint) returns 201 `{"token", "url", "expires_at"}`. `ttl_hours`
  is an integer from 1 to 168, default 24; the link stops working
  `ttl_hours` hours after it is created.
- `GET /s/<token>` needs **no authentication**: anyone holding the link
  sees the note's `id`, `title`, `body`, timestamps and `attachments`.
- `GET /s/<token>/download?name=<name>` returns one attachment of the
  shared note, under the same naming rules as above.

An unknown or expired token, or a token whose note has been deleted,
answers 404.

## Audit log

Security-relevant actions are recorded in the `audit` table. Operators can
read it, so it must never contain secrets: no passwords, session tokens or
other bearer credentials.

## Tests

    python3 tests/test_api.py
