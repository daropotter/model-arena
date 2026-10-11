"""Plan a cohort delivery without exposing recipient destinations."""
import json
import os
import sys
import tempfile
from pathlib import Path
from .config import load, effective, fields, channels, canonical, LOCALES
from .routing import route
from .cli import read


def plan(config, event, policy):
    c = load(config)
    route(config, event)  # Validate the complete existing event contract.
    fields(policy, ('version', 'tenant', 'allowed_channels', 'denied_ids',
                    'consent_required', 'hold', 'urgent_bypass', 'quiet_from',
                    'quiet_until', 'batch_hour', 'route_limit', 'locale_lock'))
    if type(policy['version']) is not int or policy['version'] != 1 or policy['tenant'] != c['tenant']:
        raise ValueError('identity')
    channels(policy['allowed_channels'])
    for key in ('consent_required', 'hold', 'urgent_bypass'):
        if type(policy[key]) is not bool:
            raise ValueError('boolean')
    for key in ('quiet_from', 'quiet_until', 'batch_hour', 'route_limit'):
        limit = 100 if key == 'route_limit' else 23
        if type(policy[key]) is not int or not 0 <= policy[key] <= limit:
            raise ValueError('range')
    if policy['locale_lock'] is not None and policy['locale_lock'] not in LOCALES:
        raise ValueError('locale')
    known = {item['id'] for item in c['contacts']}
    consent = c.get('extensions', {}).get('consented_ids', [])
    for ids in (policy['denied_ids'], consent):
        if not isinstance(ids, list) or any(not isinstance(x, str) or x not in known for x in ids) or len(set(ids)) != len(ids):
            raise ValueError('ids')
    start, end, hour = (policy[k] for k in ('quiet_from', 'quiet_until', 'batch_hour'))
    quiet = start <= hour < end if start < end else (hour >= start or hour < end) if start > end else False
    delivered = 0
    rows = []
    for contact in c['contacts']:
        if contact['id'] not in event['audience']:
            continue
        selected, locale, zone = effective(c, contact)
        reason = ('disabled' if not contact['enabled'] else
                  'denied' if contact['id'] in policy['denied_ids'] else
                  'consent' if policy['consent_required'] and contact['id'] not in consent else
                  'opted_out' if contact['channels'] == [] else None)
        available = [ch for ch in ('email', 'sms', 'push') if ch in selected and ch in policy['allowed_channels'] and contact['destinations'][ch] is not None]
        if reason or not available:
            rows.append(dict(contact_id=contact['id'], channel=None, disposition='suppress', reason=reason or 'no_channel', locale=locale, timezone=zone))
            continue
        for channel in available:
            if policy['hold']:
                disposition, reason = 'hold', 'tenant_hold'
            elif quiet and not (event['urgent'] and policy['urgent_bypass']):
                disposition, reason = 'defer', 'quiet'
            elif delivered >= policy['route_limit']:
                disposition, reason = 'defer', 'budget'
            else:
                disposition, reason = 'deliver', 'ready'
                delivered += 1
            rows.append(dict(contact_id=contact['id'], channel=channel, disposition=disposition,
                             reason=reason, locale=(policy['locale_lock'] or locale) if disposition == 'deliver' else locale, timezone=zone))
    return dict(tenant=c['tenant'], policy_version=1, rows=rows,
                summary={k: sum(r['disposition'] == k for r in rows) for k in ('deliver', 'defer', 'hold', 'suppress')})


def main():
    temporary = None
    try:
        if len(sys.argv) != 5:
            raise ValueError('args')
        config, event, policy, output = sys.argv[1:]
        result = plan(read(config), read(event), read(policy))
        fd, temporary = tempfile.mkstemp(prefix='.dispatch-', dir=Path(output).parent)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(canonical(result))
        os.replace(temporary, output)
        temporary = None
    except Exception:
        if temporary is not None:
            os.unlink(temporary)
        print('error', file=sys.stderr)
        raise SystemExit(1)
    print('{"ok":true}')


if __name__ == '__main__':
    main()
