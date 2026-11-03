"""Twitch Helix discovery with a locally configured app credential."""
import re
from datetime import timedelta

import requests

from .store import instant, now


class Twitch:
    def __init__(self, client_id, secret):
        self.client_id = client_id
        self.secret = secret
        self.session = requests.Session()
        self.session.trust_env = False
        self.token = ''

    def get(self, endpoint, params):
        for attempt in range(2):
            if not self.token:
                response = self.session.post(
                    'https://id.twitch.tv/oauth2/token',
                    data={'client_id': self.client_id, 'client_secret': self.secret,
                          'grant_type': 'client_credentials'}, timeout=10)
                if not response.ok:
                    raise ValueError('Twitch-App-Anmeldung abgelehnt. Client-ID und Secret prüfen.')
                self.token = response.json()['access_token']
            response = self.session.get(
                'https://api.twitch.tv/helix/' + endpoint, params=params,
                headers={'Client-Id': self.client_id, 'Authorization': 'Bearer ' + self.token},
                timeout=10)
            if response.status_code == 401 and attempt == 0:
                self.token = ''
                continue
            if not response.ok:
                raise RuntimeError(f'Twitch-Abfrage fehlgeschlagen (HTTP {response.status_code}).')
            return response.json()

    def broadcaster(self, channel):
        users = self.get('users', {'login': channel})['data']
        if not users:
            raise ValueError('Twitch-Kanal wurde nicht gefunden.')
        return users[0]['id']

    def clips(self, broadcaster, start, end):
        params = {'broadcaster_id': broadcaster, 'started_at': start.isoformat(),
                  'ended_at': end.isoformat(), 'first': 100}
        seen = set()
        while True:
            page = self.get('clips', params)
            yield from page['data']
            cursor = page.get('pagination', {}).get('cursor')
            if not cursor:
                return
            if cursor in seen:
                raise RuntimeError('Twitch hat eine Ergebnisseite wiederholt.')
            seen.add(cursor)
            params['after'] = cursor


def listen(service):
    client = Twitch(service.credentials['twitch_client_id'], service.credentials['twitch_client_secret'])
    broadcaster = str(service.cfg['broadcaster_id'])
    cutoff = max(instant(service.store.armed_at), instant(service.cfg['twitch_started_at']))
    checked_until = cutoff
    connected = False
    service.log('Twitch-Direkterkennung startet.')
    while not service.stop.is_set():
        if service.cfg.get('enabled'):
            try:
                end = instant(now())
                start = max(cutoff, checked_until - timedelta(minutes=5))
                for clip in client.clips(broadcaster, start, end):
                    if service.stop.is_set() or not service.cfg.get('enabled'):
                        break
                    ident = clip['id']
                    if str(clip['broadcaster_id']) != broadcaster or not re.fullmatch(r'[A-Za-z0-9_-]{8,200}', ident):
                        continue
                    if not cutoff < instant(clip['created_at']) <= end:
                        continue
                    with service.guard:
                        if service.store.get(ident) or ident in service.resolving:
                            continue
                        service.resolving[ident] = 0
                        try:
                            service.store.put(ident, 'resolving', clip=clip, event_at=now(),
                                              resolve_attempts=0, next_resolve=0)
                        except Exception:
                            service.resolving.pop(ident, None)
                            raise
                else:
                    checked_until = end
                    if not connected:
                        service.log('Twitch verbunden · prüft alle 30 Sekunden auf neue Clips.')
                        connected = True
            except (requests.RequestException, ValueError, KeyError, RuntimeError, TypeError):
                connected = False
                service.log('Twitch-Abfrage fehlgeschlagen. Erneuter Versuch folgt.')
        service.stop.wait(30)
