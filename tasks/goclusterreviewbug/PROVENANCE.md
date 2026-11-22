# Provenance and grading intent

Source: https://github.com/daropotter/chmura/pull/73
Reviewed head: `467a7c06f0fa4569ab6162a7c2626cd8db996ac8`.
False finding: https://github.com/daropotter/chmura/pull/73#discussion_r4658491202

`cluster.go`, `clusters.go` and `clusters.sql` come from that public commit.
The replay-name condition is deliberately mutated; this is a synthetic positive control, not a claim that the original PR contains this bug.
The module file is reduced to the original module name and Go 1.25.0 floor,
and Store/error declarations are minimal supporting stubs for an offline build.
This fixture does not exercise a real SQLite database or the full application.

The clean task requires an empty approval; every finding, including low-severity
unmatched claims, fails it. The paired mutant requires the replay conflict bug
and rejects the same rand.Text false alarm. This prevents blanket approval from
passing both tasks. Grading uses the existing anchor/severity/category matcher;
free-text semantic correctness still needs human review of model transcripts.
Go 1.25 must be present in the arena image. No model calibration has been run
for this new task pair.
