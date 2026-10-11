"""Trusted lazy preparation hook, run before freezing benchmark provenance."""
import importlib.util
import sys
from pathlib import Path


def prepare(task):
    task=Path(task)
    sys.path.insert(0,str(task))
    try:
        spec=importlib.util.spec_from_file_location('dossier_build',task/'build_corpus.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        manifest,built=module.ensure_assets(task)
        return {'built':built,'corpus_bytes':manifest['corpus_bytes'],'matters':manifest['matters'],'obligations':manifest['obligations'],'fingerprint':manifest['fingerprint']}
    finally:sys.path.pop(0)
