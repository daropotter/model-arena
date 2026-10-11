"""Offline regrade: original private audit + frozen grader, candidate UID 1001."""
import importlib.util
import json
import shutil
import sys
from pathlib import Path


def copy_grade_input(source, destination, task):
    """Opt-in artifact selection for tasks whose scratch indexes can be huge.

    The full submission is still archived on the host. Never follow an agent
    symlink while a privileged grader selects the files to copy.
    """
    source,destination,task=map(Path,(source,destination,task))
    paths=json.loads((task/'meta.json').read_text()).get('grading_paths')
    if paths is None:
        shutil.copytree(source,destination,symlinks=True)
        return
    destination.mkdir(parents=True)
    for relative in paths:
        parts=Path(relative).parts
        if not parts or Path(relative).is_absolute() or '..' in parts:
            raise ValueError('unsafe grading artifact path')
        current=source
        for part in parts:
            current=current/part
            if current.is_symlink():break
        else:
            if current.is_file():
                target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(current,target)


def main():
    workspace = Path('/checks/final')
    task = Path('/private/task')
    copy_grade_input('/private/submission', workspace, task)
    for path in [workspace, *workspace.rglob('*')]:
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() else 0o644)
    sys.path.insert(0, str(task / 'grader'))
    spec = importlib.util.spec_from_file_location('dispatch_grade', task / 'grader/grade.py')
    grader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grader)
    audit = json.loads(Path('/private/audit.json').read_text())
    requirements = json.loads((task / 'requirements.json').read_text())
    print(json.dumps(grader.grade(workspace, audit, requirements)))


if __name__ == '__main__':
    main()
