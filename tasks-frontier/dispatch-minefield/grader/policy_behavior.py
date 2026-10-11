"""Independent policy oracle and observable CLI cases; no candidate imports."""
import copy
import hashlib
import json
from pathlib import Path
from behavior import encoded, invoke, sample, event

TENANTS = ('amber', 'birch', 'cedar', 'dune', 'ember', 'fjord', 'grove', 'harbor')
STAGES = ('preflight', 'release')
CHANNELS = ('email', 'sms', 'push')
TASK = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fixture(tenant, name):
    return json.loads((TASK / f'starter/fixtures/cohorts/{tenant}/{name}.json').read_text())


def owners():
    return json.loads((TASK / 'starter/fixtures/cohorts/owners.json').read_text())


def policy_for(tenant, stage):
    policy = fixture(tenant, 'policy')
    if stage == 'release':
        amendments = {
            'amber': {'denied_ids': ['u10'], 'route_limit': 1},
            'birch': {'urgent_bypass': True, 'route_limit': 2},
            'cedar': {'allowed_channels': ['sms', 'push']},
            'dune': {'route_limit': 0},
            'ember': {'allowed_channels': ['email', 'push'], 'consent_required': True},
            'fjord': {'denied_ids': [], 'quiet_from': 22, 'quiet_until': 6, 'urgent_bypass': True},
            'grove': {'locale_lock': 'pl', 'route_limit': 1},
            'harbor': {'hold': True, 'urgent_bypass': True, 'route_limit': 0},
        }
        policy.update(amendments[tenant])
    return policy


def expected(config, ev, policy):
    rows = []
    for key in sorted(set(ev['audience'])):
        c = next(x for x in config['contacts'] if x['id'] == key)
        locale = c['locale'] if c['locale'] is not None else config['defaults']['locale']
        zone = c['timezone'] if c['timezone'] is not None else config['defaults']['timezone']
        channels = c['channels'] if c['channels'] is not None else config['defaults']['channels']
        addresses = c.get('destinations', c)
        available = [ch for ch in CHANNELS if ch in channels and ch in policy['allowed_channels'] and addresses[ch] is not None]
        exclusions = [(not c['enabled'], 'disabled'), (key in policy['denied_ids'], 'denied'),
            (policy['consent_required'] and key not in config.get('extensions', {}).get('consented_ids', []), 'consent'),
            (c['channels'] == [], 'opted_out'), (not available, 'no_channel')]
        exclusion = next((name for match, name in exclusions if match), None)
        for channel in [None] if exclusion else available:
            rows.append(dict(contact_id=key, channel=channel, locale=locale, timezone=zone,
                             disposition='suppress' if exclusion else 'deliver', reason=exclusion or 'ready'))
    hours = set()
    h = policy['quiet_from']
    while h != policy['quiet_until']:
        hours.add(h); h = (h + 1) % 24
    eligible = []
    for r in rows:
        if r['disposition'] != 'deliver':
            continue
        if policy['hold']:
            r.update(disposition='hold', reason='tenant_hold')
        elif policy['batch_hour'] in hours and not (ev['urgent'] and policy['urgent_bypass']):
            r.update(disposition='defer', reason='quiet')
        else:
            eligible.append(r)
    for index, r in enumerate(eligible):
        if index >= policy['route_limit']:
            r.update(disposition='defer', reason='budget')
        elif policy['locale_lock'] is not None:
            r['locale'] = policy['locale_lock']
    return dict(tenant=config['tenant'], policy_version=1, rows=rows,
                summary={k: len([r for r in rows if r['disposition'] == k]) for k in ('deliver', 'defer', 'hold', 'suppress')})


def cases(public=False):
    config = sample(); config['extensions']['consented_ids'] = ['z', '2']
    ev = event(config)
    policy = dict(version=1, tenant=config['tenant'], allowed_channels=list(CHANNELS), denied_ids=[],
        consent_required=False, hold=False, quiet_from=0, quiet_until=0, batch_hour=23,
        urgent_bypass=False, route_limit=100, locale_lock=None)
    rows = []
    def add(n, name, c=None, e=None, p=None, error=False, args=None):
        rows.append(dict(id=f'F{n:02}', case=name, config=copy.deepcopy(c or config),
            event=copy.deepcopy(e or ev), policy=copy.deepcopy(p or policy), error=error, args=args))
    for field, value in [('version',True),('hold',1),('batch_hour',True),('route_limit',-1),('quiet_until',24),('locale_lock','xx')]:
        p=copy.deepcopy(policy);p[field]=value;add(25,'invalid_'+field,p=p,error=True)
    for key,value in [('allowed_channels',['email','email']),('denied_ids',['absent']),('extra',1)]:
        p=copy.deepcopy(policy);p[key]=value;add(26,'shape_'+key,p=p,error=True)
    p=copy.deepcopy(policy);del p['hold'];add(26,'missing',p=p,error=True)
    p=copy.deepcopy(policy);p['tenant']='unrelated';add(27,'policy_tenant',p=p,error=True)
    e=copy.deepcopy(ev);e['tenant']='unrelated';add(27,'event_tenant',e=e,error=True)
    for n in range(28,46):
        c=copy.deepcopy(config);e=copy.deepcopy(ev);p=copy.deepcopy(policy)
        if n==28:e['audience']*=2;p['allowed_channels']=['push','email','sms']
        if n==29:p.update(hold=True,urgent_bypass=True)
        if n==30:p.update(denied_ids=['z'],consent_required=True);c['extensions']['consented_ids']=[]
        if n==31:p['consent_required']=True
        if n==32:c['contacts'][0]['channels']=[]
        if n==33:c['defaults']['channels']=['push']
        if n==34:p['allowed_channels']=['push']
        if n==35:
            for ch in CHANNELS:c['contacts'][0][ch]=None
        if n==36:p.update(hold=True,urgent_bypass=True,route_limit=0)
        if n==37:p.update(quiet_from=6,quiet_until=22,batch_hour=6)
        if n==38:p.update(quiet_from=22,quiet_until=6,batch_hour=0)
        if n==39:p.update(quiet_from=23,quiet_until=23,batch_hour=23)
        if n==40:p.update(quiet_from=22,quiet_until=6,urgent_bypass=True)
        if n==41:p.update(route_limit=1,denied_ids=['10']);c['contacts'][0]['channels']=[]
        if n==42:p['route_limit']=0
        if n==43:p.update(locale_lock='de',route_limit=1)
        if n==44:c['defaults']['locale']='pl';p['hold']=True
        if n==45:c['contacts'][0]['timezone']='UTC';c['defaults']['timezone']='Europe/Berlin'
        add(n,'selection',c,e,p)
    p=copy.deepcopy(policy);p['version']=7;add(46,'atomic_error',p=p,error=True)
    add(46,'args',error=True,args=[])
    for tenant in TENANTS:
        for stage in STAGES:
            add(47,tenant+'_'+stage,fixture(tenant,'config'),fixture(tenant,'event'),policy_for(tenant,stage))
    add(48,'repeat_and_summary')
    if not public:
        for field,value in [('consented_ids',[None]),('consented_ids',['z','z'])]:
            c=copy.deepcopy(config);c['extensions'][field]=value;add(31,'invalid_consent',c=c,error=True)
        for hour in (5,6,21,22):
            p=copy.deepcopy(policy);p.update(quiet_from=22,quiet_until=6,batch_hour=hour);add(38,'boundary_'+str(hour),p=p)
        p=copy.deepcopy(policy);p.update(quiet_from=22,quiet_until=6,urgent_bypass=True)
        e=copy.deepcopy(ev);e['urgent']=False;add(40,'not_urgent',e=e,p=p)
    return rows


def evaluate(workspace, public=False):
    results=[]
    for case in cases(public):
        inputs={'cfg.json':case['config'],'ev.json':case['event'],'policy.json':case['policy']}
        args=case['args'] if case['args'] is not None else ['cfg.json','ev.json','policy.json','out']
        passed=True; raws=[]
        for sentinel in ((False,True) if case['error'] else ((False,False) if case['id']=='F48' else (False,))):
            rc,out,err,raw,unchanged=invoke(workspace,args,inputs,sentinel,module='dispatch.policy')
            raws.append(raw)
            if case['error']:
                ok=rc==1 and out==b'' and err==b'error\n' and unchanged and raw==(b'ORIGINAL OUTPUT\n' if sentinel else None)
            else:
                try:ok=rc==0 and json.loads(out).get('ok') is True and unchanged and raw==encoded(expected(case['config'],case['event'],case['policy']))
                except (ValueError,AttributeError):ok=False
            passed=passed and ok
        results.append(dict(id=case['id'],case=case['case'],passed=bool(passed)))
    return results


def stage_expected(tenant, stage):
    policy=policy_for(tenant,stage)
    return {'policy.json':encoded(policy),'plan.json':encoded(expected(fixture(tenant,'config'),fixture(tenant,'event'),policy))}
