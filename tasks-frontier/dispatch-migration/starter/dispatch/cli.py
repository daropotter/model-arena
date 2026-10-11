import json
import os
import sys
import tempfile
from pathlib import Path
from .config import canonical, load
from .routing import route
from .rendering import render
from .export import export


def read(path):
    def bad_constant(_):
        raise ValueError('non-JSON number')
    return json.loads(Path(path).read_text(encoding='utf-8'), parse_constant=bad_constant)


def main():
    temporary = None
    try:
        args = sys.argv[1:]
        if not args:
            raise ValueError('args')
        if args[0] == 'migrate' and len(args) == 3:
            value, output = canonical(load(read(args[1]))), args[2]
        elif args[0] == 'route' and len(args) == 4:
            value, output = canonical(route(read(args[1]), read(args[2]))), args[3]
        elif args[0] == 'render' and len(args) == 3:
            value, output = canonical(render(read(args[1]))), args[2]
        elif args[0] == 'export' and len(args) == 5 and args[3] == '--consumer':
            value, output = export(read(args[1]), args[4]), args[2]
        else:
            raise ValueError('args')
        target = Path(output)
        fd, temporary = tempfile.mkstemp(dir=target.parent, prefix='.dispatch-')
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(value)
        os.replace(temporary, target)
        temporary = None
    except Exception:
        if temporary is not None:
            os.unlink(temporary)
        print('invalid input', file=sys.stderr)
        raise SystemExit(1)
    print('{"ok":true}')
