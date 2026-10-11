#!/usr/bin/env python3
"""Run the opt-in observed Dispatch benchmark, separate from the v2 suite.

  python3 runner/frontier.py --verify
  python3 runner/frontier.py --model opencode-go/deepseek-v4.1-flash
"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4

import arena

ROOT=Path(__file__).resolve().parents[1]
TASK_METRICS=('completion_fraction','completed_stages','total_stages','longest_valid_chain',
              'max_chain','chain_fraction','dependency_complete','blocked','user_scenarios',
              'scenario_fraction','final_artifact_verified','mutation_detection','correct_instance','evidence_chain',
              'completeness','resolution_accuracy','evidence_accuracy','citation_precision','entity_error_rate',
              'stale_rule_rate','unsupported_claim_rate','unnecessary_unknown_rate','exact_rows','total_rows',
              'invented_rows','duplicate_rows','unresolved_predictions','missing_rows','family_accuracy')
MUTANT_FAILURES={
    'forbidden': {'N03'}, 'forbidden-alias': {'N03'},
    'late-baseline': {'P01','A02'}, 'late-note': {'P02','P04'},
    'late-snapshot': {'P03'}, 'stale-check': {'P07','A03','A08'},
    'fake-receipt': {'P11','A07'}, 'protected-restore': {'R01','R02'},
    'missing-consumer': {'T06','A08'}, 'noop': {'P01','P07','A03','T01'},
    'rollback': set(),
    'harness-default': {f'N{i:02}' for i in range(1,9)},
    'harness-clean': {'P01','P07','A03','T01'},
    'diagnosed-usage': set(), 'undiagnosed-check': {'P08'},
}


def scoped_auth(model):
    provider=model.split('/',1)[0]
    path=Path.home()/'.local/share/opencode/auth.json'
    try:entry=json.loads(path.read_text()).get(provider)
    except (OSError,ValueError):entry=None
    if not entry:return None
    fd,name=tempfile.mkstemp(prefix='arena-frontier-auth-',suffix='.json')
    with os.fdopen(fd,'w') as handle:json.dump({provider:entry},handle)
    os.chmod(name,0o600)
    return Path(name)


def regrade(directory, current=False):
    """Refuse changed inputs and never infer past actions from final files."""
    out=Path(directory).resolve()
    provenance=json.loads((out/'provenance.json').read_text())
    protocol=out/'protocol'
    required={
        'task_digest': arena.tree_digest(protocol/'task'),
        'runner_digest': arena.tree_digest(protocol/'runner'),
        'docker_digest': arena.tree_digest(protocol/'docker'),
        'submission_digest': arena.tree_digest(out/'submission'),
        'audit_digest': arena.file_digest(out/'evidence/audit.json'),
    }
    for key,value in required.items():
        if provenance.get(key)!=value: raise ValueError('regrade input changed: '+key)
    grading_task=protocol/'task'
    if current:
        source=ROOT/'tasks-frontier'/json.loads((grading_task/'meta.json').read_text())['name']
        # A grading correction must not silently change the task that was
        # presented to the model. Preserve both the old and revised grade.
        contract_paths=['prompt.md','starter','skills','requirements.json']
        asset_workspace=json.loads((grading_task/'meta.json').read_text()).get('asset_workspace')
        if asset_workspace:contract_paths.append(asset_workspace)
        for name in contract_paths:
            old=arena.tree_digest(grading_task/name) if (grading_task/name).is_dir() else arena.file_digest(grading_task/name)
            new=arena.tree_digest(source/name) if (source/name).is_dir() else arena.file_digest(source/name)
            if old!=new: raise ValueError('current regrade changes model contract: '+name)
        grading_task=out/('regrade-protocol-'+uuid4().hex[:8])
        shutil.copytree(source,grading_task,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    cmd=['docker','run','--rm','--user','0:0','--read-only','--network','none',
         '--cap-drop','ALL','--cap-add','SETUID','--cap-add','SETGID','--cap-add','CHOWN','--cap-add','FOWNER','--cap-add','DAC_OVERRIDE','--cap-add','KILL',
         '--security-opt','no-new-privileges','--pids-limit','128','--memory','2g','--cpus','2',
         '--tmpfs','/tmp:rw,nosuid,nodev,size=128m,mode=1777',
         '--tmpfs','/checks:rw,nosuid,nodev,size=256m,mode=0711',
         '-v',f'{out / "submission"}:/private/submission:ro',
         '-v',f'{out / "evidence/audit.json"}:/private/audit.json:ro',
         '-v',f'{grading_task}:/private/task:ro',
         '-v',f'{ROOT / "runner/frontier_regrade_container.py"}:/private/regrade.py:ro',
         provenance['image_digest'],'python3','/private/regrade.py']
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=900)
    if result.returncode: raise RuntimeError('regrade failed: '+result.stderr[-3000:])
    grade=json.loads(result.stdout)
    (out/('grade.current.json' if current else 'grade.rechecked.json')).write_text(json.dumps(grade,indent=2))
    original=json.loads((out/'grade.json').read_text())
    equal=grade==original
    if current:
        record=json.loads((out/'record.json').read_text())
        record.update(score=grade['score'],passed=grade['passed'],detail=grade['detail'],
            grading_revision=dict(original_score=original['score'],original_grader_digest=provenance['grader_digest'],
                grader_digest=arena.tree_digest(grading_task/'grader'),task_snapshot=str(grading_task),
                driver_digest=arena.file_digest(ROOT/'runner/frontier_regrade_container.py'),
                audit_digest=provenance['audit_digest'],regraded_at=datetime.now(timezone.utc).isoformat()))
        if any(k in grade for k in TASK_METRICS):
            record['task_metrics']={k:grade[k] for k in TASK_METRICS if k in grade}
        (out/'record.regraded.json').write_text(json.dumps(record,indent=2))
    print(json.dumps(dict(run=str(out),identical=equal,score=grade['score'],detail=grade['detail'],revised_grader=current),indent=2))
    return 0 if equal or current else 1


def run(args):
    task=ROOT/'tasks-frontier'/args.task
    # Generated corpora stay outside git and are reused after content checks.
    # Preparation precedes the frozen snapshot and every provenance digest.
    if (task/'prepare.py').is_file():
        spec=importlib.util.spec_from_file_location('frontier_prepare',task/'prepare.py')
        preparation=importlib.util.module_from_spec(spec);spec.loader.exec_module(preparation)
        print('Task assets:',json.dumps(preparation.prepare(task)),flush=True)
    meta=json.loads((task/'meta.json').read_text())
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:6]
    slug='reference'+('-'+args.mutant if args.mutant else '') if args.verify else args.model.replace('/','_')
    out=Path(args.results).resolve()/(stamp+'__'+args.task+'__'+slug)
    out.mkdir(parents=True)
    scratch=Path(tempfile.mkdtemp(prefix='arena-frontier-'))
    # Freeze all protocol code before starting a run; ongoing repository work
    # must not alter a running benchmark or its provenance.
    frozen=scratch/'protocol';frozen.mkdir()
    shutil.copytree(task,frozen/'task',ignore=shutil.ignore_patterns('__pycache__','*.pyc','.build.lock','.assets-*'))
    shutil.copytree(ROOT/'runner',frozen/'runner',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copytree(ROOT/'docker',frozen/'docker',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copytree(frozen,out/'protocol')
    task=frozen/'task'
    backing=scratch/'backing';shutil.copytree(task/'starter',backing)
    if meta.get('asset_workspace'):
        shutil.copytree(task/meta['asset_workspace'],backing,dirs_exist_ok=True)
    (backing/'PROMPT.txt').write_text((task/'prompt.md').read_text())
    config=dict(model=args.model,timeout=args.timeout,verify=args.verify,mutant=args.mutant,
                uid=os.getuid(),gid=os.getgid())
    (scratch/'config.json').write_text(json.dumps(config))
    auth=None if args.verify else scoped_auth(args.model)
    image=args.image
    provenance=dict(suite_id=meta.get('suite_id','model-arena-frontier-dispatch-v1'),task_digest=arena.tree_digest(task),
        starter_digest=arena.tree_digest(task/'starter'),grader_digest=arena.tree_digest(task/'grader'),
        prompt_digest=arena.file_digest(task/'prompt.md'),runner_digest=arena.tree_digest(frozen/'runner'),
        docker_digest=arena.tree_digest(frozen/'docker'),image=image,
        image_digest=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',image],text=True).strip(),
        protocol='observed-fuse-v1',timeout_s=args.timeout,agent='reference' if args.verify else arena.agent_backend(args.model),
        harness_settings={'instruction_profile':meta.get('instruction_profile','spec'),'snapshot':False,'OPENCODE_DISABLE_FFF':True,'OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER':True})
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2))
    name='arena-frontier-'+stamp
    cmd=['docker','run','--rm','--name',name,'--user','0:0','--read-only',
         '--cap-drop','ALL','--cap-add','SYS_ADMIN','--cap-add','SETUID','--cap-add','SETGID',
         '--cap-add','CHOWN','--cap-add','FOWNER','--cap-add','DAC_OVERRIDE','--cap-add','KILL','--device','/dev/fuse',
         '--security-opt','apparmor=unconfined','--security-opt','no-new-privileges',
         '--pids-limit','256','--memory','6g','--cpus','6',
         '--network','none' if args.verify else 'bridge',
         '--tmpfs','/tmp:rw,exec,nosuid,nodev,size=512m,mode=1777',
         '--tmpfs','/home/opencode:rw,nosuid,nodev,size=512m,uid=1000,gid=1000',
         '--tmpfs','/checks:rw,nosuid,nodev,size=256m,mode=0711',
         '--tmpfs','/run/arena:rw,nosuid,nodev,size=1m,mode=0755',
         '-v',f'{backing}:/private/backing','-v',f'{out}:/private/out',
         '-v',f'{scratch / "config.json"}:/private/config.json:ro',
         '-v',f'{task}:/private/task:ro','-v',f'{frozen / "runner"}:/private/runner:ro',
         '-v',f'{frozen / "docker/agent_entry.sh"}:/entry.sh:ro',
         '-v',f'{frozen / "docker/arena-ops"}:/usr/local/bin/arena-ops:ro']
    if auth:cmd+=['-v',f'{auth}:/extra_auth.json:ro']
    for key in ('OPENCODE_API_KEY','OPENROUTER_API_KEY','CLAUDE_CODE_OAUTH_TOKEN'):
        if not args.verify and os.environ.get(key):cmd+=['-e',key]
    cmd+=[provenance['image_digest'],'python3','/private/runner/observed_container.py']
    print('Run artifacts:',out,flush=True)
    try:
        proc=subprocess.run(cmd,timeout=args.timeout+180)
        if proc.returncode:raise RuntimeError(f'observer container exited {proc.returncode}; inspect {out}')
        result=json.loads((out/'grade.json').read_text())
        status=json.loads((out/'status.json').read_text())
        stats=arena.parse_events(out/'events.jsonl') if not args.verify else dict(tokens_input=0,tokens_output=0,tokens_reasoning=0,tool_calls=0,tool_errors=0,steps=0,api_errors=0,usage_limited=False)
        provider_error=stats.get('usage_limited') or (stats['api_errors'] and not stats['tool_calls'])
        submission=out/'submission';shutil.copytree(backing,submission,symlinks=True)
        provenance.update(submission_digest=arena.tree_digest(submission),audit_digest=arena.file_digest(out/'evidence/audit.json'))
        (out/'provenance.json').write_text(json.dumps(provenance,indent=2))
        record=dict(schema_version=2,run_id=stamp,batch_id=stamp,repeat_index=0,
            model='reference' if args.verify else args.model,task=args.task,
            score=result['score'],passed=result['passed'],detail=result['detail'],
            duration_s=status['duration_s'],exit_code=status['exit_code'],
            termination_reason=status['termination_reason'],timed_out=status['termination_reason']=='hard_wall',
            valid_for_quality=not provider_error and not result.get('grader_error'),
            run_outcome='provider_error' if provider_error else 'grader_error' if result.get('grader_error') else 'completed',
            tokens={k:stats['tokens_'+k] for k in ('input','output','reasoning')},
            tool_calls=stats['tool_calls'],tool_errors=stats['tool_errors'],steps=stats['steps'],
            provenance=provenance,workspace=str(submission),run_dir=str(out),
            finished_at=datetime.now(timezone.utc).isoformat())
        if any(k in result for k in TASK_METRICS):
            record['task_metrics']={k:result[k] for k in TASK_METRICS if k in result}
        (out/'record.json').write_text(json.dumps(record,indent=2))
        print(json.dumps({'run':str(out),'score':result['score'],'passed':result['passed'],
                          'valid_for_quality':record['valid_for_quality'],'groups':result['groups']},indent=2))
        if not record['valid_for_quality']: return 2
        if args.verify:
            failures={c['id'] for c in result.get('cases',[]) if c['status']=='fail'}
            expectations=meta.get('mutant_failures',MUTANT_FAILURES)
            expected=set(expectations.get(args.mutant,[]))
            correct=expected<=failures if expected else result['passed'] and result['score']==1.0
            if args.mutant=='noop': correct=correct and result['score']<0.5
            if args.mutant=='harness-clean': correct=correct and not result.get('forbidden_opened')
            if status['exit_code'] or not correct:
                print('Verification FAILED: expected rejected obligations',sorted(expected),flush=True)
                return 1
        return 0
    finally:
        subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=30)
        if auth:auth.unlink(missing_ok=True)
        shutil.rmtree(scratch,ignore_errors=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',default='opencode-go/deepseek-v4.1-flash')
    parser.add_argument('--task',default='dispatch-migration',choices=('dispatch-migration','dispatch-minefield','returns-release','returns-distributed','export-forensics','dossier'))
    parser.add_argument('--verify',action='store_true')
    parser.add_argument('--verify-all',action='store_true',help='reference and all deliberate protocol violations; no model calls')
    parser.add_argument('--regrade',metavar='RUN_DIR',help='replay frozen grading with the original audit, offline')
    parser.add_argument('--current-grader',action='store_true',help='with --regrade: preserve a revised grade and its provenance')
    parser.add_argument('--mutant',default='')
    parser.add_argument('--timeout',type=int,default=3600)
    parser.add_argument('--image',default='model-arena-observed')
    parser.add_argument('--results',default=str(ROOT/'results-frontier'))
    args=parser.parse_args()
    if args.regrade:
        if args.verify or args.verify_all or args.mutant: parser.error('regrade cannot be combined with verification')
        return regrade(args.regrade,args.current_grader)
    if args.current_grader:parser.error('--current-grader requires --regrade')
    expectations=json.loads((ROOT/'tasks-frontier'/args.task/'meta.json').read_text()).get('mutant_failures',MUTANT_FAILURES)
    if args.mutant and args.mutant not in expectations: parser.error('unknown mutant for this task')
    if args.verify_all:
        if args.mutant: parser.error('verify-all cannot be combined with mutant')
        args.verify=True
        failures=[]
        for mutant in ('',*expectations):
            args.mutant=mutant
            if run(args): failures.append(mutant or 'reference')
        print(json.dumps({'verification_failures':failures}))
        return int(bool(failures))
    if args.mutant and not args.verify:parser.error('--mutant requires --verify')
    arena.validate_model_name(args.model)
    if args.timeout<1:parser.error('timeout must be positive')
    return run(args)


if __name__=='__main__':
    raise SystemExit(main())
