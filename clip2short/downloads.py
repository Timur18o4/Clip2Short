"""Resolve the exact public Twitch clip without borrowing a user's OAuth token."""
from .store import instant


class QuietLogger:
    def debug(self,*args): pass
    def warning(self,*args): pass
    def error(self,*args): pass


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
