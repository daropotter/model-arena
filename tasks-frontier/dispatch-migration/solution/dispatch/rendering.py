from .config import CHANNELS, LOCALES, ZONES, fields, nonempty


def render(delivery):
    fields(delivery, ('tenant', 'event_id', 'contact_id', 'channel', 'destination',
                     'locale', 'timezone', 'subject', 'body'))
    if (any(not nonempty(delivery[k]) for k in ('tenant', 'event_id', 'contact_id', 'destination')) or
            delivery['channel'] not in CHANNELS or delivery['locale'] not in LOCALES or
            delivery['timezone'] not in ZONES or not isinstance(delivery['subject'], str) or
            not isinstance(delivery['body'], str)):
        raise ValueError('delivery')
    separator = {'email': '\n\n', 'sms': ': ', 'push': '\n'}[delivery['channel']]
    return dict(channel=delivery['channel'], destination=delivery['destination'],
                text=delivery['subject'] + separator + delivery['body'],
                locale=delivery['locale'], timezone=delivery['timezone'])
