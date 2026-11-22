# Cluster registry persistence

This is an offline review fixture for a cluster registry adapter. The module
requires Go 1.25.0. There are no external module dependencies. Inspect the
project and use local documentation or `go build ./...` to verify claims.
The Store declaration and error values are supporting code already present
before this change. The database driver and service bootstrap are outside
this fixture; the change adds the methods and schema in change.diff.

Contract:
- Register an explicit cluster with an opaque server-assigned ID and exact name.
- Names are unique within an installation. Hash creation keys before storage.
- An exact name/key retry returns the original cluster with created=false.
- Reusing a creation key with a different name, or a name with another key,
  returns ErrConflict and a zero Cluster; it must not return someone else's
  cluster as a successful registration.
- Missing lookups return ErrNotFound. Opening a database creates no cluster.
- Callers authorize access and validate domain naming; this adapter rejects
  blank fields and preserves supplied names without normalization.
