#!/usr/bin/env python3
"""Local operations console; transport to the isolated runtime supervisor."""
import subprocess
import sys

if len(sys.argv)==1 or sys.argv[1] in ('--help','help'):
    print("status | request HOST PATH FIXTURE | build | review TICKET CANDIDATE | test CANDIDATE | deploy CANDIDATE")
else:
    raise SystemExit(subprocess.call(['arena-ops',*sys.argv[1:]]))
