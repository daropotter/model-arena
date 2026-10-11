import csv
import io
from .config import canonical, effective, load


def export(config, consumer):
    config = load(config)
    if consumer not in ('modern', 'legacy'):
        raise ValueError('consumer')
    recipients = []
    for c in config['contacts']:
        if not c['enabled']:
            continue
        selected, locale, zone = effective(config, c)
        recipients.append(dict(id=c['id'], destinations=c['destinations'],
            channels=[x for x in selected if c['destinations'][x] is not None], locale=locale, timezone=zone))
    if consumer == 'modern':
        return canonical(dict(version=2, tenant=config['tenant'], recipients=recipients))
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(['tenant', 'id', 'email', 'locale', 'timezone'])
    for r in recipients:
        if 'email' in r['channels']:
            writer.writerow([config['tenant'], r['id'], r['destinations']['email'], r['locale'], r['timezone']])
    return output.getvalue()
