# feat(state): persist explicit cluster registration

Add durable explicit registration of an initially empty cluster, with a stable
server-assigned ID, installation-wide unique name and idempotent creation
receipt. Exact retries recover the original identity. Conflicting name/key
bindings return ErrConflict without a cluster record. SQL uniqueness handles
independent database clients. Opening the database creates no default cluster.
This change adds the state records, SQLite methods and schema in change.diff;
API/CLI commands and database startup are outside its scope.
