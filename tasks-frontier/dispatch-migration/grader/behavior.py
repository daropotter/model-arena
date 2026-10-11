"""Independent CLI oracle cases. Never imports candidate or solution code."""
import copy
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CHANNELS = ['email', 'sms', 'push']
SCOPES = {'config': set(range(1, 9)), 'routing': set(range(9, 20)),
          'rendering': {20, 21}, 'export': {22, 23}, 'cli': {24}}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()


def sample():
    return {'version': 1, 'tenant': 'tenant,α', 'defaults':
            {'locale': 'pl', 'timezone': 'Europe/Warsaw', 'channels': ['email', 'sms']},
            'extensions': {'retain': {'list': [False, None, {'x': '✓'}]}},
            'contacts': [dict(id=k, enabled=k != 'disabled',
                email='same,"addr"@example.test', sms='+48123456789', push='device:'+k,
                channels=None, locale=None, timezone=None,
                extensions={'nested': [k, {'keep': True}]})
                for k in ['z', '10', '2', 'disabled']]}


def event(config):
    return dict(tenant=config['tenant'], id='evt-42',
                audience=[c['id'] for c in config['contacts']],
                subject='  Subject, "ó"  ', body='a\nb\t<b>✓</b> ', urgent=True)


def migrated(config):
    out = copy.deepcopy(config)
    if out['version'] == 1:
        for contact in out['contacts']:
            contact['destinations'] = {k: contact.pop(k) for k in CHANNELS}
    out['version'] = 2
    out['contacts'] = sorted(out['contacts'], key=lambda c: c['id'])
    return out


def expected_routes(config, ev):
    out = []
    for contact in sorted(config['contacts'], key=lambda c: c['id']):
        if not contact['enabled'] or contact['id'] not in ev['audience']:
            continue
        dest = contact.get('destinations', contact)
        selected = config['defaults']['channels'] if contact['channels'] is None else contact['channels']
        for channel in CHANNELS:
            if channel not in selected or dest[channel] is None:
                continue
            out.append({'tenant': config['tenant'], 'event_id': ev['id'],
                'contact_id': contact['id'], 'channel': channel, 'destination': dest[channel],
                'locale': config['defaults']['locale'] if contact['locale'] is None else contact['locale'],
                'timezone': config['defaults']['timezone'] if contact['timezone'] is None else contact['timezone'],
                'subject': ev['subject'], 'body': ev['body']})
    return out


def expected_export(config, consumer):
    recipients = []
    for contact in sorted(config['contacts'], key=lambda c: c['id']):
        if contact['enabled']:
            destinations = contact.get('destinations', {k: contact.get(k) for k in CHANNELS})
            channels = config['defaults']['channels'] if contact['channels'] is None else contact['channels']
            recipients.append(dict(id=contact['id'], destinations=destinations,
                channels=[k for k in channels if destinations[k] is not None],
                locale=config['defaults']['locale'] if contact['locale'] is None else contact['locale'],
                timezone=config['defaults']['timezone'] if contact['timezone'] is None else contact['timezone']))
    if consumer == 'modern':
        return encoded(dict(version=2, tenant=config['tenant'], recipients=recipients))
    s = io.StringIO(newline='')
    w = csv.writer(s, lineterminator='\n')
    w.writerow(['tenant', 'id', 'email', 'locale', 'timezone'])
    for r in recipients:
        if 'email' in r['channels']:
            w.writerow([config['tenant'], r['id'], r['destinations']['email'], r['locale'], r['timezone']])
    return s.getvalue().encode()


def cases(public=False):
    rows = []
    def add(req, name, command, inputs, expected=None, error=False, exact=False):
        rows.append(dict(req=req, name=name, command=command, inputs=inputs,
                         expected=expected, error=error, exact=exact))
    c = sample()
    for req in range(1, 6):
        cfg = migrated(c) if req == 5 else c
        add(f'F{req:02}', 'migration', ['migrate','cfg.json','out'], {'cfg.json':cfg}, migrated(cfg))
    for kind in ['version', 'duplicate', 'extra', 'channel', 'destination', 'locale', 'defaults', 'extensions']:
        cfg = copy.deepcopy(c)
        if kind == 'version': cfg['version'] = 7
        if kind == 'duplicate': cfg['contacts'].append(copy.deepcopy(cfg['contacts'][0]))
        if kind == 'extra': cfg['surprise'] = True
        if kind == 'channel': cfg['contacts'][0]['channels'] = ['fax']
        if kind == 'destination': cfg['contacts'][0]['email'] = 12
        if kind == 'locale': cfg['contacts'][0]['locale'] = 'xx'
        if kind == 'defaults': cfg['defaults']['channels'] = ['email','email']
        if kind == 'extensions': cfg['extensions'] = []
        add('F06',kind,['migrate','cfg.json','out'],{'cfg.json':cfg},error=True)
    cfg = copy.deepcopy(c); cfg['version'] = True
    add('F07','boolean',['migrate','cfg.json','out'],{'cfg.json':cfg},error=True)
    add('F08','canonical',['migrate','cfg.json','out'],{'cfg.json':c},encoded(migrated(c)),exact=True)
    for version in (1,2):
        cfg = c if version == 1 else migrated(c)
        add('F09',f'v{version}', ['route','cfg.json','ev.json','out'],
            {'cfg.json':cfg,'ev.json':event(c)},expected_routes(cfg,event(c)))
    for kind in ['wrongtenant','unknown','duplicate']:
        e=event(c)
        if kind=='wrongtenant': e['tenant']='other'
        if kind=='unknown': e['audience'].append('absent')
        if kind=='duplicate': e['audience']*=2
        add('F10',kind,['route','cfg.json','ev.json','out'],{'cfg.json':c,'ev.json':e},
            expected_routes(c,e) if kind=='duplicate' else None,error=kind!='duplicate')
    for req in range(11,20):
        cfg=copy.deepcopy(c); e=event(cfg)
        if req==13: cfg['contacts'][0]['channels']=[]
        if req==14: cfg['contacts'][0]['channels']=['push','sms']
        if req==15: cfg['contacts'][0]['email']=None
        if req==16: cfg['contacts'][0]['locale']='de'
        if req==17: cfg['contacts'][0]['timezone']='UTC'
        if req==18: cfg['contacts'][-1]['channels']=['unknown']
        add(f'F{req:02}', 'routing', ['route','cfg.json','ev.json','out'],
            {'cfg.json':cfg,'ev.json':e}, None if req==18 else expected_routes(cfg,e), error=req==18)
    for channel in CHANNELS:
        d=expected_routes(c,event(c))[0]; d['channel']=channel; d['locale']='de'; d['timezone']='UTC'
        sep={'email':'\n\n','sms':': ','push':'\n'}[channel]
        expected={k:d[k] for k in ['channel','destination','locale','timezone']}
        expected['text']=d['subject']+sep+d['body']
        add('F20','template_'+channel,['render','d.json','out'],{'d.json':d},expected)
        add('F21','preserve_'+channel,['render','d.json','out'],{'d.json':d},expected)
    d=expected_routes(c,event(c))[0]; d['destination']=None
    add('F20','invalid_delivery',['render','d.json','out'],{'d.json':d},error=True)
    for consumer,req in [('modern','F22'),('legacy','F23')]:
        cfg=copy.deepcopy(c); cfg['contacts'][0]['channels']=[]; cfg['contacts'][1]['email']=None
        cfg['contacts'][2]['locale']='de'; cfg['contacts'][2]['timezone']='UTC'
        for version in (1,2):
            data=cfg if version==1 else migrated(cfg)
            add(req,f'{consumer}_v{version}', ['export','cfg.json','out','--consumer',consumer],
                {'cfg.json':data},expected_export(data,consumer),exact=True)
    for args in [[],['bogus'],['migrate'],['export','cfg.json','out','--consumer','x'],['render','missing','out']]:
        add('F24','args_'+str(len(rows)),args,{'cfg.json':c},error=True)
    if not public:
        # Invalid event shapes and poisoned later contacts exercise validation
        # before output and rule out implementations matching only happy paths.
        for key,val in [('urgent',1),('audience',[None]),('subject',{}),('id','')]:
            e=event(c);e[key]=val
            add('F18','event_'+key,['route','cfg.json','ev.json','out'],{'cfg.json':c,'ev.json':e},error=True)
    return rows


def run_child(command, workspace, env, timeout=5):
    """Execute candidate code without privileges and reap its process group."""
    opts = dict(user=1001, group=1001, extra_groups=[]) if os.geteuid() == 0 else {}
    proc = subprocess.Popen(command, cwd=workspace, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True, **opts)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return proc.returncode, stdout, stderr
    finally:
        import signal
        try: os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        proc.wait()


def consumer_checks(workspace):
    rows = []
    for consumer in ('legacy', 'modern'):
        rc, _, _, raw, unchanged = invoke(workspace,
            ['export', 'cfg.json', 'out', '--consumer', consumer], {'cfg.json': sample()})
        ok = rc == 0 and unchanged and raw == expected_export(sample(), consumer)
        if ok:
            with tempfile.TemporaryDirectory(prefix='dispatch-consumer-') as tmp:
                folder = Path(tmp)
                if os.geteuid() == 0:
                    folder.chmod(0o700); os.chown(folder, 1001, 1001)
                output = folder / 'export'; output.write_bytes(raw); output.chmod(0o644)
                try:
                    status, stdout, _ = run_child([sys.executable, f'consumers/{consumer}.py', str(output)],
                        workspace, {'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
                                    'PYTHONDONTWRITEBYTECODE': '1', 'HOME': str(folder)})
                    ok = status == 0 and stdout.strip().isdigit() and int(stdout) > 0
                except (OSError, subprocess.TimeoutExpired): ok = False
        rows.append(dict(id=consumer, case='shipped_consumer', passed=ok))
    return rows


def invoke(workspace, command, inputs, sentinel=False):
    with tempfile.TemporaryDirectory(prefix='dispatch-case-') as tmp:
        tmp=Path(tmp)
        if os.geteuid()==0:
            tmp.chmod(0o700);os.chown(tmp,1001,1001)
        for name,value in inputs.items():
            p=tmp/name;p.write_bytes(encoded(value));p.chmod(0o644)
        out=tmp/'out'
        if sentinel: out.write_bytes(b'ORIGINAL OUTPUT\n');out.chmod(0o666)
        before={n:(tmp/n).read_bytes() for n in inputs}
        args=[str(tmp/a) if a in inputs or a in ('out','missing') else a for a in command]
        env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL')}
        env.update(HOME=str(tmp),PYTHONDONTWRITEBYTECODE='1')
        try:
            rc,stdout,stderr=run_child([sys.executable,'-m','dispatch',*args],workspace,env)
            raw=out.read_bytes() if not out.is_symlink() and out.is_file() and out.stat().st_size<2_000_000 else None
            unchanged=all(not (tmp/n).is_symlink() and (tmp/n).is_file() and (tmp/n).stat().st_size==len(b) and (tmp/n).read_bytes()==b for n,b in before.items())
            return rc,stdout,stderr,raw,unchanged
        except (OSError,subprocess.TimeoutExpired):
            return None,b'',b'candidate failed or timed out',None,False


def evaluate(workspace, public=False, scope=None):
    results=[]
    allowed=SCOPES.get(scope)
    for case in cases(public):
        if allowed is not None and int(case['req'][1:]) not in allowed: continue
        if public and scope=='compatibility' and case['req'] not in ('F09','F22','F23'): continue
        ok=True
        for sentinel in ((False,True) if case['error'] else (False,)):
            rc,out,err,raw,unchanged=invoke(workspace,case['command'],case['inputs'],sentinel)
            if case['error']:
                passed=rc==1 and out==b'' and err==b'error\n' and raw==(b'ORIGINAL OUTPUT\n' if sentinel else None) and unchanged
            else:
                try:
                    passed=rc==0 and json.loads(out).get('ok') is True and unchanged
                    if passed and case['exact']:
                        passed=raw==case['expected']
                    elif passed:
                        got=json.loads(raw);want=case['expected'];req=case['req']
                        # Separate observations avoid making a sorting bug
                        # automatically fail preservation, schema and identity.
                        if req=='F01':
                            passed=all(got[k]==want[k] for k in ('version','tenant','defaults'))
                        elif req=='F02':
                            passed={c['id']:c['destinations'] for c in got['contacts']}=={c['id']:c['destinations'] for c in want['contacts']}
                        elif req=='F03':
                            passed=got['extensions']==want['extensions'] and {c['id']:c['extensions'] for c in got['contacts']}=={c['id']:c['extensions'] for c in want['contacts']}
                        elif req=='F04':
                            passed=[c['id'] for c in got['contacts']]==[c['id'] for c in want['contacts']]
                        elif req in ('F12','F13','F14','F15','F16','F17'):
                            got=[d for d in got if d['contact_id']=='z'];want=[d for d in want if d['contact_id']=='z']
                            passed=got==want
                        elif req=='F11':
                            passed=bool(got) and not any(d['contact_id']=='disabled' for d in got)
                        else:passed=got==want
                except (TypeError,ValueError,AttributeError,KeyError): passed=False
            ok=ok and passed
        results.append(dict(id=case['req'],case=case['name'],passed=bool(ok)))
    return results
