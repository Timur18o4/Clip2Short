"""Explicit Twitch clip imports and channel browsing."""
from datetime import timedelta
import re

from .downloads import inspect_link
from .service import allowed_media
from .store import instant, now
from .twitch import Twitch


def preview(service, clip, thumbnail, category=''):
    ident = clip['id']
    return {
        'title': clip.get('title') or 'Twitch-Clip',
        'channel': clip.get('broadcaster_display_name') or clip.get('broadcaster_name', ''),
        'created_at': clip.get('created_at'),
        'duration': clip.get('duration'),
        'thumbnail': thumbnail if allowed_media(thumbnail) else '',
        'url': 'https://clips.twitch.tv/' + ident,
        'known': service.store.get(ident) is not None,
        'category': category,
    }


def prepare(service, url, *, enqueue=False):
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError('Bitte einen gültigen Twitch-Clip-Link eingeben.')
    resolved = inspect_link(url)
    clip = resolved['clip']
    ident = clip['id']
    category = resolved['category']
    if not enqueue:
        return preview(service, clip, resolved['thumbnail'], category)
    with service.guard:
        if service.stop.is_set():
            raise ValueError('Clip2Short wird gerade beendet. Bitte erneut versuchen.')
        if service.store.get(ident) or ident in service.resolving:
            raise ValueError('Dieser Twitch-Clip wurde bereits erfasst oder entfernt.')
        service.store.put(ident, 'queued', clip=clip, category=category, twitch_import=True)
        service.work.put(ident)
    return {'id': ident}


def channel_clips(service, page=None):
    credentials = service.credentials
    channel = service.cfg['channel']
    if not (channel and credentials.get('twitch_client_id') and credentials.get('twitch_client_secret')):
        raise ValueError('Für die Kanalliste müssen Twitch-App-Zugangsdaten hinterlegt sein. Einen Clip-Link kannst du direkt eingeben.')
    client = Twitch(credentials['twitch_client_id'], credentials['twitch_client_secret'])
    current_minute = instant(now()).replace(second=0, microsecond=0)
    earliest = instant('2016-01-01T00:00:00Z')
    try:
        if page is None:
            users = client.get('users', {'login': channel})['data']
            if not users:
                raise ValueError('Twitch-Kanal wurde nicht gefunden.')
            profile = users[0]
            broadcaster = str(profile['id'])
            floor = max(earliest, instant(profile['created_at']).replace(second=0, microsecond=0))
            end = current_minute + timedelta(minutes=1)
            start = max(floor, end-timedelta(days=7))
            cursor, count = '', 0
        else:
            broadcaster = str(service.cfg.get('broadcaster_id') or client.broadcaster(channel))
            if page['broadcaster'] != broadcaster:
                raise ValueError('Die Kanalliste wurde gewechselt. Bitte erneut laden.')
            floor, start, end = (instant(page[key]) for key in ('floor', 'start', 'end'))
            cursor, count = page['cursor'], page['count']
            if not (earliest <= floor <= start < end <= current_minute+timedelta(minutes=1)
                    and isinstance(cursor, str) and len(cursor) <= 2048
                    and type(count) is int and 0 <= count <= 2000):
                raise ValueError('Ungültige Fortsetzung der Kanalliste. Bitte erneut laden.')

        interval = timedelta(days=30)
        while floor < end:
            params = {'broadcaster_id': broadcaster, 'first': 50,
                      'started_at': start.isoformat(), 'ended_at': end.isoformat()}
            if cursor:
                params['after'] = cursor
            result = client.get('clips', params)
            clips = result['data']
            following = result.get('pagination', {}).get('cursor') or ''
            count += len(clips)
            if following and following == cursor:
                raise RuntimeError('Twitch hat dieselbe Ergebnisseite erneut geliefert.')
            if count >= 900 and end-start > timedelta(minutes=1):
                # Twitch caps pagination per query. Split dense windows before the cap.
                start = (start+(end-start)/2).replace(second=0, microsecond=0)
                following, count = '', 0
            elif not following:
                end = start
                start = max(floor, end-interval)
                count = 0
                interval = min(interval*2, timedelta(days=365))
            cursor = following
            if clips:
                next_page = None if end <= floor else {
                    'broadcaster': broadcaster, 'floor': floor.isoformat(),
                    'start': start.isoformat(), 'end': end.isoformat(),
                    'cursor': cursor, 'count': count,
                }
                return {'clips': [preview(service, clip, clip.get('thumbnail_url') or '')
                                  for clip in sorted(clips, key=lambda item: item['created_at'], reverse=True)
                                  if str(clip.get('broadcaster_id')) == broadcaster
                                  and re.fullmatch('[A-Za-z0-9_-]{8,200}', clip['id'])],
                        'next': next_page}
        return {'clips': [], 'next': None}
    except ValueError:
        raise
    except Exception:
        raise RuntimeError('Twitch konnte die Kanalliste gerade nicht laden. Bitte Verbindung und Zugangsdaten prüfen.') from None
