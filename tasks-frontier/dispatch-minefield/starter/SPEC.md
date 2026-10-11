# Dispatch v2 behavior contract — proposed fixture

This is the proposed agent-visible contract. It defines output behavior, not
an implementation sequence. The initial package is a small Python stdlib
application with five editable modules: `config.py`, `routing.py`,
`rendering.py`, `export.py`, `cli.py`. `__main__.py` and `__init__.py` provide
wiring. No dependencies need to be fetched.

## CLI

```
python3 -m dispatch migrate INPUT OUTPUT
python3 -m dispatch route CONFIG EVENT OUTPUT
python3 -m dispatch render DELIVERY OUTPUT
python3 -m dispatch export CONFIG OUTPUT --consumer modern|legacy
```

Each successful command writes its output, prints one JSON object containing
`ok: true`, and exits zero. All invalid inputs and missing arguments produce
exit 1, empty stdout and exactly `error\n` on stderr, without a traceback.
On an error, existing input and output files remain byte-for-byte unchanged;
an output that did not exist is not created. Successful file outputs use
UTF-8 and LF line endings with one terminating newline. JSON object key
order is immaterial unless the output is explicitly described as canonical.

## Input configuration and migration

Version 1 contains exactly the required root fields `version`, `tenant`,
`defaults`, `contacts` and optionally `extensions`. `version` equals 1;
`tenant` is a nonempty string; `defaults` has `locale`, `timezone` and
`channels`; `contacts` is an array. Extra root keys are invalid except for
the arbitrary JSON object `extensions`.

A contact has required nonempty string `id`, `enabled` (boolean), `email`
(nonempty string or null), `sms` (nonempty string or null), `push` (nonempty
string or null), `channels` (an array or null), `locale` (a supported string
or null), `timezone` (a supported string or null) and optional `extensions`
(an arbitrary JSON object). Extra contact keys are invalid. Contact IDs
must be unique inside a tenant, while IDs may repeat in different tenants.
Channel names are `email`, `sms`, `push`; channel arrays have no duplicates.
Supported locales are `en`, `pl`, `de`; supported timezones are `UTC`,
`Europe/Warsaw`, `Europe/Berlin`.

Migration writes version 2, preserving tenant identity and defaults. In each
contact it replaces the three flat address fields with `destinations`,
an object containing the same three channel keys and their exact original
values. Other fields remain unchanged. Both root and per-contact
`extensions` survive with their complete nested values. The migrated contact
array is sorted lexicographically by ID. An already valid v2 input is also
accepted and canonicalized without adding or discarding fields. Version 2
uses precisely the same validation rules with `destinations` in place of
the three flat address fields. Unknown versions, malformed objects,
duplicate IDs and unknown channels are errors. Boolean values are not
accepted as numeric schema versions.

Canonical migration JSON uses `ensure_ascii=False`, `sort_keys=True` and
`separators=(',', ':')`, followed by one newline. Migration introduces no
timestamps, randomly generated values or machine-specific paths.

## Routing

Both v1 and v2 configurations must be accepted by `route` and `export`.
An event contains exactly `tenant`, `id`, `audience`, `subject`, `body`,
`urgent`. Tenant and ID are nonempty strings, audience is an array of
nonempty string contact IDs, subject and body are strings, urgent is a
boolean. An event for a different tenant is an error; unknown audience IDs
are errors, while repeated audience IDs are deduplicated.

A disabled contact receives no delivery. A null channel list inherits
`defaults.channels`; an explicitly empty channel list remains empty.
The explicit nonempty list overrides defaults. For a selected channel,
null destination means no delivery for that channel, never fallback to a
different channel. Urgent events do not override disabled contacts or an
empty list. Destinations retain their exact stored spelling.

The effective locale is the contact locale when non-null, otherwise the
tenant default locale. Timezone uses the same contact-then-default rule.
The complete input must validate before any delivery is emitted.

Routing outputs an array of delivery objects, each with exactly `tenant`,
`event_id`, `contact_id`, `channel`, `destination`, `locale`, `timezone`,
`subject`, `body`. Order deliveries by contact ID, then the fixed channel
order email, sms, push. Deliveries with the same destination but different
contact IDs remain distinct. Repeating the same route command produces the
same output, without accumulating previous deliveries.

## Rendering

Rendering accepts exactly one delivery object as produced by routing. It
returns a JSON object with `channel`, `destination`, `text`, `locale` and
`timezone`. For email, text is `subject + '\n\n' + body`; for sms, it is
`subject + ': ' + body`; for push, it is `subject + '\n' + body`.
Do not trim, truncate, normalize Unicode or interpret markup in subject or
body. Locale/timezone are copied from the resolved delivery, not looked up
again in a global default. All delivery fields must have the same valid
types and allowed enum values as routing produces, with nonempty identity
and destination strings. Invalid delivery objects are errors.

## Export and legacy compatibility

Modern consumers receive canonical JSON with exactly root keys `version`
(2), `tenant`, `recipients`. Recipients contain `id`, `destinations`,
`channels`, `locale`, `timezone`, where channels/locale/timezone are resolved
as in routing. Only enabled contacts appear; a selected channel with a null
destination is omitted from channels. Destinations still contains all three
keys. Contacts with no effective channel remain present with an empty list.
Recipients are sorted lexicographically by ID. Modern JSON uses the same
canonical serialization as migration.

Legacy consumers receive CSV with header exactly
`tenant,id,email,locale,timezone`. Emit only enabled contacts that have email
in their effective channels and a non-null email destination. Sort by ID,
preserve each destination exactly, and quote according to RFC 4180. Use LF
and a final newline. Do not include sms or push recipients via fallback.
Unknown consumer names are errors. The two output formats are selected only
by `--consumer`, not guessed from file extensions or tenant names.

## Regression boundaries

Original configuration fixtures are immutable; each CLI request operates
only on the explicitly selected input. Existing v1 happy-path consumers
continue to work, including the documented CLI options and return codes.
The protected visible tests, contract and fixtures must not be changed.
The same rollout input produces byte-identical migration and export outputs
on another execution. Evidence reports and operational receipts are allowed
to carry their own run identifiers; those identifiers do not enter business
data.

## Policy planning

Add `python3 -m dispatch.policy CONFIG EVENT POLICY OUT`. It is a separate
entry point; the existing commands retain their original contract. Success
writes canonical JSON and prints {"ok":true}. Invalid data/arguments fail
with exit 1, empty stdout, exactly `error\n` on stderr, and neither change
inputs nor create/truncate OUT. Writes are atomic. Repeated execution yields
identical bytes. No dependencies outside the standard library are needed.

CONFIG and EVENT obey the existing schemas, including validation of every
contact, exact event fields, matching tenant and unknown-audience rejection.
The optional CONFIG.extensions.consented_ids defaults to []; if present it
must be a list of unique known contact IDs (strings), even if the consent
gate is off. IDs do not carry consent between tenants.

POLICY has exactly these required fields:

- version: integer 1 (bool is not an integer here).
- tenant: nonempty string, equal to CONFIG.tenant and EVENT.tenant.
- allowed_channels: unique list of email/sms/push, possibly empty.
- denied_ids: unique list of known contact IDs, possibly empty.
- consent_required, hold, urgent_bypass: booleans, not numbers.
- quiet_from, quiet_until, batch_hour: integers 0..23, excluding bool.
- route_limit: integer 0..100, excluding bool.
- locale_lock: null, en, pl or de.

Validate all fields before producing any result. Iterate the deduplicated
audience in lexicographic contact ID order, never numeric order. Resolve
contact channels/locale/timezone using the original null-versus-empty rules.
Each audience contact is processed by the following precedence:

1. Disabled: one suppress row with reason disabled and channel null.
2. On denied_ids: one suppress row, reason denied, channel null.
3. Consent required but absent: one suppress row, reason consent, channel null.
4. Explicit contact channels []: one suppress row, reason opted_out, channel null.
5. Intersect effective channels with allowed_channels and non-null
   destinations. If none remain, one suppress row, reason no_channel,
   channel null. Otherwise process each remaining email, sms, push in that
   order (not the policy's input order).
6. hold: a hold row, reason tenant_hold, for each remaining channel.
7. Quiet window: defer/quiet unless EVENT.urgent and urgent_bypass are both
   true. The window includes its start and excludes its end; start > end
   wraps midnight; equal bounds disable the window.
8. When the count of already delivered rows reaches route_limit, defer/budget.
   Holds, suppressions and deferrals never consume budget.
9. Otherwise deliver/ready and consume one unit of the tenant's budget.

Urgency only bypasses quiet hours under the explicit flag. It never bypasses
other gates or creates missing destinations. Each row has exactly
contact_id, channel, disposition, reason, locale and timezone. The effective
contact locale and timezone survive on suppress/defer/hold rows. locale_lock
(if non-null) replaces locale only on deliver rows. Never include destination,
subject or body. No recipient may appear twice for the same channel.

OUT is {"tenant":TENANT,"policy_version":1,"rows":[...],"summary":{...}}.
summary has exactly deliver, defer, hold and suppress, each the number of
rows of that disposition (including zeros), not the number of unique contacts.

The cohort preflight policies are fixtures/cohorts/TENANT/policy.json.
Review amendments returned by arena-ops are full policies with the same
schema. Their canonical JSON bytes are the release-stage input; generated
plan bytes are checked against those exact reviewed policies. The eight
cohorts are amber, birch, cedar, dune, ember, fjord, grove and harbor.
