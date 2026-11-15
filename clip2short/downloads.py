"""Resolve the exact public Twitch clip without borrowing a user's OAuth token."""
from .store import instant
from datetime import datetime,timezone
import re
from urllib.parse import urlsplit


class QuietLogger:
    def debug(self,*args): pass
    def warning(self,*args): pass
    def error(self,*args): pass


def clip_slug(url):
    parsed = urlsplit(url.strip())
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port is not None:
        raise ValueError('Bitte einen HTTPS-Clip-Link von Twitch eingeben.')
    parts = parsed.path.strip('/').split('/')
    if parsed.hostname == 'clips.twitch.tv' and len(parts) == 1:
        ident = parts[0]
    elif parsed.hostname in ('www.twitch.tv','twitch.tv','m.twitch.tv') and (
        len(parts) in (2, 3) and parts[-2] == 'clip'
    ):
        ident = parts[-1]
    else:
        raise ValueError('Bitte den Link zu einem Twitch-Clip eingeben.')
    if not re.fullmatch('[A-Za-z0-9_-]{8,200}', ident):
        raise ValueError('Ungültige Clip-ID.')
    return ident


def extract_clip(ident):
    import yt_dlp
    if not re.fullmatch('[A-Za-z0-9_-]{8,200}',ident):raise ValueError('Ungültige Clip-ID.')
    options={'quiet':True,'no_warnings':True,'noplaylist':True,'skip_download':True,'cachedir':False,
             'socket_timeout':15,'retries':2,'extractor_retries':2,'proxy':'','logger':QuietLogger()}
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            return downloader.extract_info('https://clips.twitch.tv/'+ident,download=False)
    except Exception:
        raise RuntimeError('Der öffentliche Twitch-Clip konnte nicht abgerufen werden.') from None


def resolve_public(ident,channel,armed_at,broadcaster_id=None):
    """Resolve exactly one event ID; no channel search or historical fallback."""
    info = extract_clip(ident)
    same_channel=str(info.get('channel_id'))==str(broadcaster_id) if broadcaster_id else str(info.get('channel','')).casefold()==channel.casefold()
    if info.get('display_id')!=ident or not same_channel:
        raise ValueError('Clip-ID oder Twitch-Kanal passt nicht zum Ereignis.')
    created=instant(info.get('timestamp'))
    if created<=instant(armed_at) or (created-datetime.now(timezone.utc)).total_seconds()>120:
        raise ValueError('Clip wurde vor der Aktivierung erstellt oder hat ein ungültiges Datum.')
    return clip_metadata(ident, info, created, channel)


def clip_metadata(ident, info, created, channel):
    if info.get('display_id') != ident or not info.get('channel_id'):
        raise ValueError('Identität des Twitch-Clips konnte nicht bestätigt werden.')
    categories=info.get('categories') or []
    if not categories:raise ValueError('Kategorie fehlt im Twitch-Clip.')
    duration=info.get('duration')
    if not isinstance(duration,(int,float)) or not 0<duration<=180:raise ValueError('Die Cliplänge fehlt oder ist nicht unterstützt.')
    clip={'id':ident,'title':str(info.get('title') or ''),'broadcaster_id':str(info['channel_id']),
          'broadcaster_name':channel,'broadcaster_display_name':str(info.get('channel','')),'created_at':created.isoformat(),'duration':info.get('duration')}
    return {'clip':clip,'category':str(categories[0]),'stream_title':''}


def inspect_link(url):
    from .service import allowed_media
    ident = clip_slug(url)
    info = extract_clip(ident)
    if not info.get('categories'):
        info = {**info, 'categories': ['Unbekannt']}
    result = clip_metadata(ident, info, instant(info.get('timestamp')), str(info.get('channel') or ''))
    thumbnail = info.get('thumbnail') or ''
    result['thumbnail'] = thumbnail if allowed_media(thumbnail) else ''
    return result


def public_media(clip):
    import yt_dlp
    from .service import allowed_media
    options={'quiet':True,'no_warnings':True,'noplaylist':True,'skip_download':True,
             'cachedir':False,'socket_timeout':15,'retries':2,'extractor_retries':2,
             'proxy':'','logger':QuietLogger()}
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info=downloader.extract_info('https://clips.twitch.tv/'+clip['id'],download=False)
    except Exception:
        raise RuntimeError('Der neue öffentliche Twitch-Clip ist noch nicht abrufbar. Kein anderer Clip wird ersatzweise geladen.') from None
    if info.get('display_id')!=clip['id'] or str(info.get('channel_id'))!=str(clip['broadcaster_id']):
        raise ValueError('Download-Metadaten passen nicht zum neu gemeldeten Clip.')
    if not info.get('timestamp') or abs(instant(info['timestamp']).timestamp()-instant(clip['created_at']).timestamp())>2:
        raise ValueError('Erstellungsdatum des Download-Clips stimmt nicht überein.')
    formats=[f for f in info.get('formats',[]) if 'portrait' not in str(f.get('format_id',''))
             and (f.get('aspect_ratio') or 16/9)>=1 and allowed_media(f.get('url',''))]
    if not formats: raise RuntimeError('Keine horizontale Twitch-Videodatei gefunden.')
    return max(formats,key=lambda f:(f.get('height') or 0,f.get('fps') or 0))['url']
