"""Drop submission subprocesses to a UID that cannot read the hidden grader."""

import os
import stat
import subprocess
from pathlib import Path


_ORIGINAL_POPEN = subprocess.Popen
SUBMISSION_UID = 1000
SUBMISSION_GID = 1000


def _is_submission(args, cwd) -> bool:
    if cwd:
        try:
            if Path(cwd).resolve().is_relative_to("/submission"):
                return True
        except (OSError, RuntimeError, ValueError):
            pass
    command = args if isinstance(args, (list, tuple)) else [args]
    return any(str(arg).startswith("/submission/") for arg in command)


_CASE_OPEN_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
_PRIVATE_DIRS = {"arena-hidden-grader", "arena-private-result"}


def _grant_case_access(fd, mode) -> None:
    # Candidate-owned objects already belong to the submission UID. The
    # grader deliberately has no CAP_FOWNER to chmod other users' objects.
    if os.fstat(fd).st_uid == os.geteuid():
        os.fchmod(fd, mode)


def _open_case_tree(directory_fd) -> None:
    """Change only opened case objects, never targets of candidate symlinks."""
    _grant_case_access(directory_fd, 0o777)
    for name in os.listdir(directory_fd):
        try:
            fd = os.open(name, _CASE_OPEN_FLAGS, dir_fd=directory_fd)
        except OSError:
            continue
        try:
            mode = os.fstat(fd).st_mode
            if stat.S_ISDIR(mode):
                _open_case_tree(fd)
            elif stat.S_ISREG(mode):
                _grant_case_access(fd, 0o666)
        finally:
            os.close(fd)


def _open_case_paths(args) -> None:
    command = args if isinstance(args, (list, tuple)) else []
    for arg in command:
        parts = Path(str(arg)).parts
        if (len(parts) < 3 or parts[:2] != ("/", "tmp")
                or ".." in parts or parts[2] in _PRIVATE_DIRS):
            continue
        # Grant access to command arguments and their parents, not siblings
        # such as a grader's reference output. Descriptor-relative opens also
        # prevent a background submission from swapping in a symlink between
        # an inspection and chmod.
        fd = os.open("/tmp", _CASE_OPEN_FLAGS | os.O_DIRECTORY)
        try:
            for index, name in enumerate(parts[2:], start=2):
                try:
                    child_fd = os.open(name, _CASE_OPEN_FLAGS, dir_fd=fd)
                except OSError:
                    break  # A missing output is created by the submission.
                os.close(fd)
                fd = child_fd
                mode = os.fstat(fd).st_mode
                if stat.S_ISDIR(mode):
                    # Only the immediate parent needs write access for a new
                    # output. Earlier ancestors grant traversal, keeping
                    # private sibling directories safe from replacement.
                    _grant_case_access(fd, 0o777 if index >= len(parts) - 2 else 0o711)
                    if index == len(parts) - 1:
                        _open_case_tree(fd)
                elif stat.S_ISREG(mode):
                    if index == len(parts) - 1:
                        _grant_case_access(fd, 0o666)
                    break
                else:
                    break
        finally:
            os.close(fd)


def _drop_privileges():
    os.setgroups([])
    os.setgid(SUBMISSION_GID)
    os.setuid(SUBMISSION_UID)
    os.umask(0)


class SandboxedPopen(_ORIGINAL_POPEN):
    def __init__(self, args, *pargs, **kwargs):
        cwd = kwargs.get("cwd")
        if _is_submission(args, cwd):
            _open_case_paths(args)
            previous = kwargs.get("preexec_fn")

            def prepare():
                if previous:
                    previous()
                _drop_privileges()

            env = dict(kwargs.get("env") or os.environ)
            env.pop("PYTHONPATH", None)
            env["HOME"] = "/tmp"
            kwargs["env"] = env
            kwargs["preexec_fn"] = prepare
        super().__init__(args, *pargs, **kwargs)


subprocess.Popen = SandboxedPopen
