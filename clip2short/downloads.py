"""Resolve the exact public Twitch clip without borrowing a user's OAuth token."""
from .store import instant
from datetime import datetime,timezone


class QuietLogger:
    def debug(self,*args): pass
    def warning(self,*args): pass
    def error(self,*args): pass


def resolve_public(ident,channel,armed_at,broadcaster_id=None):
    """Resolve exactly one event ID; no channel search or historical fallback."""
    import re,yt_dlp
    if not re.fullmatch('[A-Za-z0-9_-]{8,200}',ident):raise ValueError('Ungültige Clip-ID.')
    options={'quiet':True,'no_warnings':True,'noplaylist':True,'skip_download':True,'cachedir':False,
             'socket_timeout':15,'retries':2,'extractor_retries':2,'proxy':'','logger':QuietLogger()}
    try:
        with yt_dlp.YoutubeDL(options) as downloader:info=downloader.extract_info('https://clips.twitch.tv/'+ident,download=False)
    except Exception:raise RuntimeError('Der gemeldete neue Twitch-Clip ist noch nicht abrufbar.') from None
    same_channel=str(info.get('channel_id'))==str(broadcaster_id) if broadcaster_id else str(info.get('channel','')).casefold()==channel.casefold()
    if info.get('display_id')!=ident or not same_channel:
        raise ValueError('Clip-ID oder Twitch-Kanal passt nicht zum Ereignis.')
    created=instant(info.get('timestamp'))
    if created<=instant(armed_at) or (created-datetime.now(timezone.utc)).total_seconds()>120:
        raise ValueError('Clip wurde vor der Aktivierung erstellt oder hat ein ungültiges Datum.')
    categories=info.get('categories') or []
    if not categories or not info.get('channel_id'):raise ValueError('Kategorie oder Kanal-ID fehlt im Twitch-Clip.')
    duration=info.get('duration')
    if not isinstance(duration,(int,float)) or not 0<duration<=180:raise ValueError('Die Cliplänge fehlt oder ist nicht unterstützt.')
    clip={'id':ident,'title':str(info.get('title') or ''),'broadcaster_id':str(info['channel_id']),
          'broadcaster_name':channel,'broadcaster_display_name':str(info.get('channel','')),'created_at':created.isoformat(),'duration':info.get('duration')}
    return {'clip':clip,'category':str(categories[0]),'stream_title':''}


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
