from .config import CHANNELS, effective, fields, load, nonempty


def route(config, event):
    config = load(config)
    fields(event, ('tenant', 'id', 'audience', 'subject', 'body', 'urgent'))
    if (not nonempty(event['tenant']) or event['tenant'] != config['tenant'] or
            not nonempty(event['id']) or type(event['urgent']) is not bool or
            not isinstance(event['subject'], str) or not isinstance(event['body'], str) or
            not isinstance(event['audience'], list) or not all(nonempty(x) for x in event['audience'])):
        raise ValueError('event')
    audience = set(event['audience'])
    if not audience <= {c['id'] for c in config['contacts']}:
        raise ValueError('audience')
    deliveries = []
    for c in config['contacts']:
        if c['id'] not in audience or (not c['enabled'] and not event['urgent']):
            continue
        selected, locale, zone = effective(config, c)
        for channel in CHANNELS:
            dest = c['destinations'][channel]
            if channel in selected and dest is not None and channel != 'push':
                deliveries.append(dict(tenant=config['tenant'], event_id=event['id'], contact_id=c['id'],
                    channel=channel, destination=dest, locale=locale, timezone=zone,
                    subject=event['subject'], body=event['body']))
    return deliveries
