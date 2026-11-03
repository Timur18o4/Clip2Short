"""Local-only source/crop/design tools. References never enter the clip queue."""
import base64
import copy
import io
import json
import re
import subprocess
import uuid
from pathlib import Path
from urllib.parse import unquote
from PIL import Image,ImageOps
from .design import PRESETS,validate,rect,render_design
from .config import save_config


def state(service):
    sources=[
        {'id':'job:'+j['id'],'title':(j.get('editorial') or {}).get('title') or j.get('clip',{}).get('title') or j['id']}
        for j in service.store.list() if (service.root/'clips'/(j['id']+'.mp4')).is_file()]
    for path in sorted((service.root/'references').glob('*.mp4'),key=lambda p:p.stat().st_mtime,reverse=True):
        title='Eigenes Beispiel · '+path.stem[:6]
        if path.with_suffix('.json').exists():title=json.loads(path.with_suffix('.json').read_text(encoding='utf-8')).get('title',title)
        sources.append({'id':'reference:'+path.stem,'title':title})
    return {'config':service.cfg,'presets':PRESETS,'sources':sources}


def source_path(service,value):
    value=str(value)
    if value.startswith('job:'):
        ident=value[4:]
        if not re.fullmatch('[A-Za-z0-9_-]{8,200}',ident) or not service.store.get(ident):raise ValueError('Clip nicht gefunden.')
        path=service.root/'clips'/(ident+'.mp4')
    elif value.startswith('reference:') and re.fullmatch('[a-f0-9]{32}',value[10:]):
        path=service.root/'references'/(value[10:]+'.mp4')
    else:raise ValueError('Bitte einen Beispielclip auswählen.')
    if not path.is_file():raise ValueError('Beispielclip fehlt.')
    return path


def frame(service,value,at):
    from clip_engine.media import probe_media,find_binary,_creation_flags
    path=source_path(service,value);metadata=probe_media(path);at=float(at)
    if not 0<=at<metadata['duration']:raise ValueError('Zeitpunkt liegt außerhalb des Videos.')
    result=subprocess.run([find_binary('ffmpeg'),'-v','error','-nostdin','-ss',str(at),'-i',str(path),'-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'],capture_output=True,timeout=30,creationflags=_creation_flags())
    if result.returncode:raise ValueError('Standbild konnte nicht gelesen werden.')
    return {'image':'data:image/png;base64,'+base64.b64encode(result.stdout).decode(),'metadata':{k:metadata[k] for k in ('width','height','duration')}}


def background(service,raw):
    with Image.open(io.BytesIO(raw)) as image:
        if image.width*image.height>24_000_000:raise ValueError('Hintergrundbild ist zu groß (höchstens 24 Megapixel).')
        image=ImageOps.exif_transpose(image).convert('RGB')
        folder=service.root/'assets';folder.mkdir(exist_ok=True)
        name=uuid.uuid4().hex+'.png';image.save(folder/name)
    return {'asset':name}


def upload_reference(service,reader,length,name=''):
    from clip_engine.media import probe_media
    folder=service.root/'references';folder.mkdir(exist_ok=True);ident=uuid.uuid4().hex;path=folder/(ident+'.mp4')
    try:
        with path.open('wb') as out:
            remaining=length
            while remaining:
                chunk=reader.read(min(1024*1024,remaining))
                if not chunk:raise ValueError('Videoübertragung wurde unterbrochen.')
                out.write(chunk);remaining-=len(chunk)
        metadata=probe_media(path)
        if metadata['duration']>600:raise ValueError('Der Beispielclip darf höchstens zehn Minuten lang sein.')
        path.with_suffix('.json').write_text(json.dumps({'title':unquote(str(name))[:200] or 'Eigenes Beispiel'},ensure_ascii=False),encoding='utf-8')
        return {'id':'reference:'+ident,'metadata':{k:metadata[k] for k in ('width','height','duration')}}
    except Exception:
        path.unlink(missing_ok=True);raise


def profiles(value,existing):
    if not isinstance(value,dict) or set(value)!=set(existing):raise ValueError('Alle drei Bildprofile müssen erhalten bleiben.')
    result={}
    for mode,parts in value.items():
        if not isinstance(parts,dict) or set(parts)!=set(existing[mode]):raise ValueError('Webcam oder Hauptbild fehlt im Profil.')
        result[mode]={part:rect(r) for part,r in parts.items()}
    return result


def save(service,data):
    cfg=copy.deepcopy(service.cfg)
    cfg['profiles']=profiles(data['profiles'],cfg['profiles']);cfg['design']=validate(data['design'])
    cfg['brand']=str(data.get('brand',cfg['brand'])).strip()[:100]
    render_design(cfg,service.root) # Check referenced asset before saving anything.
    save_config(cfg,service.root);service.cfg.update(cfg)
    return {'ok':True,'message':'Bildprofile und Gestaltung gespeichert. Vorhandene Videos wurden nicht verändert.'}


def preview(service,data):
    from clip_engine.media import probe_media
    from clip_engine.render import preview_project
    from .layout import pixel_crop
    path=source_path(service,data['source']);metadata=probe_media(path)
    mode=data['mode']
    if mode not in service.cfg['profiles']:raise ValueError('Unbekannte Ansicht.')
    checked=profiles(data['profiles'],service.cfg['profiles']);design=validate(data['design'])
    project={'source':str(path),'mode':'just_chatting' if mode=='camera' else 'gameplay','scene_name':mode,
        'crops':{part:pixel_crop(r,metadata['width'],metadata['height']) for part,r in checked[mode].items()},
        'design':render_design({'design':design},service.root),'title':str(data.get('title') or 'Dein Moment. Dein Design.')[:75],
        'chat_quote':str(data.get('quote') or '')[:140],'label':{'camera':'JUST CHATTING','gameplay':'GAMEPLAY','reaction':'DESKTOP / REACTION'}[mode],
        'brand':str(data.get('brand',service.cfg['brand']))[:100],'channel':service.cfg['channel'].upper(),
        'captions':[{'start':0,'end':metadata['duration'],'text':'Hier stehen deine Untertitel.'}]}
    image=preview_project(project,float(data.get('at',0)))
    buffer=io.BytesIO();image.save(buffer,format='PNG')
    return {'image':'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()}
