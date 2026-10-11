"""Root supervisor for one observed task; agent runs as unprivileged UID 1000."""
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from observed_protocol import Evidence, serve_ops
from observed_fs import mount
from frontier_regrade_container import copy_grade_input


def kill_uid(uid):
    for p in Path('/proc').glob('[0-9]*'):
        try:
            fields=(p/'status').read_text().splitlines()
            if any(line.startswith('Uid:') and int(line.split()[1])==uid for line in fields):
                os.kill(int(p.name),signal.SIGKILL)
        except (OSError,ValueError):pass


def main():
    task=Path('/private/task');out=Path('/private/out');backing=Path('/private/backing')
    config=json.loads(Path('/private/config.json').read_text())
    evidence_class=Evidence
    if (task/'protocol.py').is_file():
        sys.path.insert(0,str(task/'grader'))
        spec=importlib.util.spec_from_file_location('task_protocol',task/'protocol.py')
        extension=importlib.util.module_from_spec(spec);spec.loader.exec_module(extension)
        evidence_class=extension.Evidence
    evidence=evidence_class(backing,task,out/'evidence')
    server=serve_ops(evidence,'/run/arena/ops.sock')
    status={}
    def driver():
        proc=None;start=time.monotonic()
        try:
            for _ in range(200):
                if os.path.ismount('/workspace'):break
                time.sleep(.05)
            else:raise RuntimeError('FUSE mount not ready')
            env=os.environ.copy();env.update(HOME='/home/opencode',PYTHONDONTWRITEBYTECODE='1')
            profile=evidence.meta.get('instruction_profile','spec')
            if profile not in ('spec','forensics','reconstruction'):raise ValueError('unknown instruction profile')
            env['ARENA_INSTRUCTION_PROFILE']=profile
            # Background indexing must not contaminate no-open evidence.
            env['OPENCODE_CONFIG_CONTENT']=json.dumps({'snapshot':False})
            env['OPENCODE_DISABLE_FFF']='true'
            env['OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER']='true'
            if config.get('verify'):
                payload={str(p.relative_to(task/'solution')):p.read_text() for p in (task/'solution').rglob('*') if p.is_file() and p.suffix in ('.py','.mjs','.json')}
                if evidence.meta.get('asset_solution'):
                    reference_root=task/evidence.meta['asset_solution']
                    payload.update({str(p.relative_to(reference_root)):p.read_text() for p in reference_root.rglob('*') if p.is_file() and p.suffix in ('.py','.mjs','.json')})
                Path('/tmp/reference-solution.json').write_text(json.dumps(payload))
                shutil.copy2(task/'reference_run.py','/tmp/reference_run.py')
                shutil.copy2('/private/runner/harness_probe.py','/tmp/harness_probe.py')
                env['REFERENCE_MUTANT']=config.get('mutant','')
                command=[sys.executable,'/tmp/reference_run.py']
            else:
                command=['sh','/entry.sh',config['model'],'/workspace/PROMPT.txt',str(config['timeout']),config.get('ollama_url','http://172.22.0.1:11435/v1')]
            with (out/'events.jsonl').open('wb') as stdout,(out/'stderr.log').open('wb') as stderr:
                proc=subprocess.Popen(command,cwd='/workspace',env=env,user=1000,group=1000,extra_groups=[],
                                      stdout=stdout,stderr=stderr,start_new_session=True)
                print('observed workspace ready; agent running',flush=True)
                try:
                    rc=proc.wait(timeout=config['timeout'])
                    termination='completed'
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGKILL);rc=proc.wait();termination='hard_wall'
            kill_uid(1000)
            kill_uid(1001)
            # No actor remains that can mutate FUSE or manufacture later evidence.
            server.shutdown()
            audit=evidence.finish()
            grading=Path('/checks/final')
            copy_grade_input(backing,grading,task)
            grading.chmod(0o755)
            for p in grading.rglob('*'):
                if not p.is_symlink():p.chmod(0o755 if p.is_dir() else 0o644)
            sys.path.insert(0,str(task/'grader'))
            spec=importlib.util.spec_from_file_location('dispatch_grade',task/'grader/grade.py')
            grader=importlib.util.module_from_spec(spec);spec.loader.exec_module(grader)
            result=grader.grade(grading,audit,json.loads((task/'requirements.json').read_text()))
            (out/'grade.json').write_text(json.dumps(result,indent=2))
            status.update(exit_code=rc,termination_reason=termination,duration_s=round(time.monotonic()-start,3))
            print(json.dumps({'passed':result['passed'],'score':result['score'],'detail':result['detail']}),flush=True)
        except BaseException as exc:
            status.update(error=f'{type(exc).__name__}: {exc}',duration_s=round(time.monotonic()-start,3))
            # Traceback stays in a private local artifact; no credential values
            # or environment are serialized in the status channel.
            import traceback
            (out/'supervisor-error.txt').write_text(traceback.format_exc())
            print(json.dumps(status),flush=True)
        finally:
            kill_uid(1000);kill_uid(1001)
            (out/'status.json').write_text(json.dumps(status,indent=2))
            subprocess.run(['fusermount','-u','/workspace'],capture_output=True,timeout=15)
    worker=threading.Thread(target=driver)
    worker.start()
    try:mount(evidence,'/workspace')
    finally:
        worker.join(timeout=config['timeout']+60)
        server.server_close()
        for root in (out,backing):
            for p in [root,*root.rglob('*')]:
                try:os.chown(p,config['uid'],config['gid'],follow_symlinks=False)
                except OSError:pass
    return 1 if status.get('error') else 0


if __name__=='__main__':
    raise SystemExit(main())
