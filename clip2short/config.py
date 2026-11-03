"""Local settings and Windows-user-bound DPAPI credentials."""
import base64
import ctypes
import json
import os
import re
import secrets
from pathlib import Path


def data_dir():
    override=os.environ.get('CLIP2SHORT_CLIP_DATA')
    marker=Path(__file__).resolve().parents[1]/'installation.json'
    if not override and marker.exists(): override=json.loads(marker.read_text(encoding='utf-8'))['data_dir']
    return Path(override or str(Path(os.environ.get('LOCALAPPDATA',Path.home()))/'Clip2Short')).resolve()


def defaults():
    return {'version':2,'channel':'','port':39242,'lumia_url':'http://127.0.0.1:39231/api',
            'command':'clip2short','privacy':'SELF_ONLY','enabled':True,'model':'medium',
            'fps':60,'auto_upload':True,'require_face':True,'vision':True,'brand':'',
            'transport':'native','ai_provider':'lumia','ollama_url':'http://127.0.0.1:11434','ollama_model':'',
            'profiles':{'camera':{'main':{'x':.234375,'y':0,'width':.5489583,'height':1}},
                        'gameplay':{'main':{'x':.234375,'y':0,'width':.5270833,'height':1},
                                    'facecam':{'x':.7958333,'y':.3240741,'width':.1807292,'height':.3777778}},
                        'reaction':{'main':{'x':0,'y':0,'width':1,'height':1},
                                    'facecam':{'x':.7958333,'y':.3240741,'width':.1807292,'height':.3777778}}}}


def channel_name(value):
    name=str(value).strip().removeprefix('@').casefold()
    if not re.fullmatch(r'[a-z0-9_]{1,25}',name):raise ValueError('Twitch-Kanal als Namen ohne URL eingeben (Buchstaben, Ziffern, Unterstrich).')
    return name


def load_config(root=None):
    root=Path(root or data_dir()); root.mkdir(parents=True,exist_ok=True)
    path=root/'config.json'; cfg=defaults()
    if path.exists():
        saved=json.loads(path.read_text(encoding='utf-8'));cfg.update(saved)
        # Existing installations stay on their tested bridge until explicitly migrated.
        if 'transport' not in saved:cfg['transport']='command'
    if cfg['privacy'] not in ('SELF_ONLY','PUBLIC_TO_EVERYONE'): raise ValueError('Ungültige TikTok-Sichtbarkeit.')
    return cfg


def save_config(cfg,root=None):
    root=Path(root or data_dir()); root.mkdir(parents=True,exist_ok=True)
    temp=root/'config.tmp'; temp.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8'); temp.replace(root/'config.json')


class Blob(ctypes.Structure):
    _fields_=[('size',ctypes.c_ulong),('data',ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(raw,decrypt=False):
    if os.name!='nt': raise RuntimeError('Gespeicherte Zugangsdaten benötigen Windows-DPAPI.')
    buf=ctypes.create_string_buffer(raw); inp=Blob(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte))); out=Blob()
    api=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not api(ctypes.byref(inp),None,None,None,None,1,ctypes.byref(out)): raise ctypes.WinError()
    try: return ctypes.string_at(out.data,out.size)
    finally: ctypes.windll.kernel32.LocalFree(out.data)


def save_secrets(token,root=None,bridge_key=None):
    root=Path(root or data_dir()); root.mkdir(parents=True,exist_ok=True)
    value={'lumia_token':token.strip(),'bridge_key':bridge_key or secrets.token_urlsafe(32)}
    (root/'credentials.dpapi').write_bytes(_dpapi(json.dumps(value).encode()))
    return value


def load_secrets(root=None):
    return json.loads(_dpapi((Path(root or data_dir())/'credentials.dpapi').read_bytes(),True))
