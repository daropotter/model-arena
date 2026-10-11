import copy
import json

CHANNELS = ('email', 'sms', 'push')
LOCALES = ('en', 'pl', 'de')
ZONES = ('UTC', 'Europe/Warsaw', 'Europe/Berlin')


def nonempty(value):
    return isinstance(value, str) and bool(value)


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or not value.keys() <= set(required) | set(optional):
        raise ValueError('fields')


def channels(value):
    if not isinstance(value, list) or any(not isinstance(v, str) or v not in CHANNELS for v in value) or len(set(value)) != len(value):
        raise ValueError('channels')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'


def load(value):
    fields(value, ('version', 'tenant', 'defaults', 'contacts'), ('extensions',))
    if value['version'] not in (1, 2) or not nonempty(value['tenant']):
        raise ValueError('identity')
    defaults = value['defaults']
    fields(defaults, ('locale', 'timezone', 'channels'))
    if defaults['locale'] not in LOCALES or defaults['timezone'] not in ZONES:
        raise ValueError('defaults')
    channels(defaults['channels'])
    if not isinstance(value['contacts'], list):
        raise ValueError('contacts')
    if 'extensions' in value and not isinstance(value['extensions'], dict):
        raise ValueError('extensions')
    result = copy.deepcopy(value)
    seen = set()
    for contact in result['contacts']:
        base = ('id', 'enabled', 'channels', 'locale', 'timezone')
        fields(contact, base + (CHANNELS if result['version'] == 1 else ('destinations',)), ('extensions',))
        if not nonempty(contact['id']) or contact['id'] in seen or type(contact['enabled']) is not bool:
            raise ValueError('contact')
        seen.add(contact['id'])
        if 'extensions' in contact and not isinstance(contact['extensions'], dict):
            raise ValueError('extensions')
        if contact['channels'] is not None:
            channels(contact['channels'])
        if contact['locale'] is not None and contact['locale'] not in LOCALES:
            raise ValueError('locale')
        if contact['timezone'] is not None and contact['timezone'] not in ZONES:
            raise ValueError('timezone')
        dest = {c: contact[c] for c in CHANNELS} if result['version'] == 1 else contact['destinations']
        fields(dest, CHANNELS)
        if any(v is not None and not nonempty(v) for v in dest.values()):
            raise ValueError('destinations')
        if result['version'] == 1:
            for c in CHANNELS:
                del contact[c]
            contact['destinations'] = dest
    result['version'] = 2
    # Preserve legacy input order.
    return result


def effective(config, contact):
    return (contact['channels'] or config['defaults']['channels'],
            config['defaults']['locale'] if contact['locale'] is None else contact['locale'],
            config['defaults']['timezone'] if contact['timezone'] is None else contact['timezone'])
