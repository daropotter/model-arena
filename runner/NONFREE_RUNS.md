The non-free completion queue selects model identifiers without `free`,
including Ollama and Big Pickle. It preserves valid failures and reruns
missing, infrastructure-invalid, legacy or changed-input results.

```bash
python3 runner/complete_nonfree.py                 # preview only
python3 runner/complete_nonfree.py --status        # live frozen-suite coverage
systemctl --user status model-arena-nonfree.service
```

The authorized service runs against a frozen copy of `runner/`, `docker/`
and `tasks/`, with a pinned Docker image. Later working-tree edits do not
change its inputs. Arena, prescreen and regrade entry points share a host
lock, so the existing free-model watcher cannot run alongside this queue.

Progress, blockers, the snapshot manifest and the controller log are under
`results/nonfree-completion/`. Original attempts and submissions remain in
`results/`. Each completed attempt refreshes the main report; derived
reports are refreshed at the end.

During the current controller correction, the one-time
`model-arena-nonfree-resume.service` waits for the active run and its graceful
checkpoint, then resumes the frozen suite. Its log is
`results/nonfree-completion/resume.log`. It checks the unchanged controller,
allowlist and previous snapshot before restarting; it never interrupts a run.

The service covers the 38 models from the main benchmark. Additional
prescreen-only models are outside the currently approved execution scope.

Resume a stopped series with its pinned image and unchanged benchmark inputs:

```bash
python3 runner/complete_nonfree.py --run --background --resume-frozen \
  --models-file results/nonfree-completion/models.txt
```

This copies the previous suite and updates only the completion controller.
It refuses changed frozen inputs or an unavailable pinned image. Completed
pairs, including valid failures, are skipped. The allowlist fixes the scope
to the original 38 approved models even if other results are added later.
After resolving a recorded blocker, also add `--retry-blocked`.
Omitting `--resume-frozen` starts against the current working-tree inputs;
that is a separate experiment when its benchmark hashes differ.
