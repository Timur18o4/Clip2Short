"""Sampled scene decisions: fixed crop profiles plus face and image evidence."""
import math
import statistics
from functools import lru_cache
from clip_engine.media import extract_frame


class NeedsLayoutReview(RuntimeError): pass


@lru_cache(maxsize=1)
def face_detector():
    import cv2
    model=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    if model.empty(): raise RuntimeError('Gesichtserkennung konnte nicht geladen werden.')
    return model


def faces(image):
    import cv2,numpy as np
    gray=cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2GRAY)
    found=face_detector().detectMultiScale(gray,scaleFactor=1.1,minNeighbors=6,minSize=(30,30))
    return [{'x':float(x)/image.width,'y':float(y)/image.height,'width':float(w)/image.width,'height':float(h)/image.height} for x,y,w,h in found]


@lru_cache(maxsize=1)
def vision_model():
    from transformers import CLIPModel,CLIPProcessor
    name='openai/clip-vit-base-patch32'
    return CLIPModel.from_pretrained(name),CLIPProcessor.from_pretrained(name)


def image_kind(image):
    import torch
    labels=['a screenshot of a video game with a small facecam overlay',
            'a computer desktop or web browser with a small webcam overlay',
            'a video reaction showing a movie or another video and a small webcam overlay',
            'a close up webcam video of a streamer talking in a room']
    model,processor=vision_model()
    inputs=processor(text=labels,images=image,return_tensors='pt',padding=True)
    with torch.inference_mode(): scores=model(**inputs).logits_per_image.softmax(dim=1)[0].tolist()
    order=sorted(range(4),key=lambda i:scores[i],reverse=True)
    return (['gameplay','reaction','reaction','camera'][order[0]],scores[order[0]]-scores[order[1]])


def classify(found,kind,margin,category,cfg):
    large=[f for f in found if f['width']>=.125 and .2<f['x']+f['width']/2<.8]
    small=[f for f in found if f['x']+f['width']/2>=.73 and f['width']<.18]
    # Small false positives in logos/backgrounds must not override a clearly
    # recognised full camera containing a large central face.
    if large and (not small or (cfg.get('vision',True) and kind=='camera' and margin>=.08)):
        # A character or a face in a reaction video is not proof of the streamer's full camera.
        if cfg.get('vision',True) and margin>=.08 and kind in ('gameplay','reaction'): return None
        return 'camera'
    if small:
        if margin>=.08 and kind in ('gameplay','reaction'): return kind
        # Uncertain content keeps the complete desktop/game frame visible.
        return 'reaction'
    if cfg.get('require_face',True): return None
    return 'camera' if category.casefold()=='just chatting' else 'reaction'


def pixel_crop(rect,w,h):
    x=max(0,min(w-2,round(rect['x']*w))); y=max(0,min(h-2,round(rect['y']*h)))
    return {'x':x,'y':y,'width':max(2,min(w-x,round(rect['width']*w))),
            'height':max(2,min(h-y,round(rect['height']*h)))}


def detect_scenes(source,metadata,category,cfg,progress=lambda *_:None,cancel=None):
    duration=metadata['duration']; step=max(2,duration/18); decisions=[]
    for position in [min(duration-.02,.5+i*step) for i in range(max(1,math.ceil(duration/step)))]:
        if cancel and cancel.is_set(): raise RuntimeError('Abgebrochen.')
        progress('Kamera und Szenen werden geprüft …',None)
        image=extract_frame(source,position,width=960)
        detected=faces(image)
        kind,margin=image_kind(image) if cfg.get('vision',True) else ('',0)
        name=classify(detected,kind,margin,category,cfg)
        decisions.append({'time':position,'name':name,'faces':detected,'kind':kind,'margin':margin})
    known=[d['name'] for d in decisions if d['name']]
    if not known or len(known)/len(decisions)<.5: raise NeedsLayoutReview('Webcam nicht verlässlich erkannt. Bildprofil einmal prüfen; kein automatischer Upload.')
    last=known[0]
    for d in decisions:
        if not d['name']: d['name']=last
        last=d['name']
    # Suppress isolated false detections between two equal neighbours.
    for i in range(1,len(decisions)-1):
        if decisions[i-1]['name']==decisions[i+1]['name']: decisions[i]['name']=decisions[i-1]['name']
    spans=[]
    for index,d in enumerate(decisions):
        start=0 if index==0 else (decisions[index-1]['time']+d['time'])/2
        end=duration if index==len(decisions)-1 else (d['time']+decisions[index+1]['time'])/2
        if spans and spans[-1]['name']==d['name']: spans[-1]['end']=end
        else: spans.append({'start':start,'end':end,'name':d['name']})
    for span in spans:
        profile=cfg['profiles'][span['name']]
        span['crops']={k:pixel_crop(v,metadata['width'],metadata['height']) for k,v in profile.items()}
        # The face must actually lie inside the configured camera rectangle.
        key='main' if span['name']=='camera' else 'facecam'; rect=profile[key]
        evidence=[d for d in decisions if span['start']<=d['time']<=span['end'] and d['faces']]
        def covered(f):
            width=max(0,min(rect['x']+rect['width'],f['x']+f['width'])-max(rect['x'],f['x']))
            height=max(0,min(rect['y']+rect['height'],f['y']+f['height'])-max(rect['y'],f['y']))
            return width*height/(f['width']*f['height'])>=.9
        if not evidence or sum(any(covered(f) for f in d['faces']) for d in evidence)/len(evidence)<.6:
            raise NeedsLayoutReview('Erkanntes Gesicht liegt außerhalb des Kameraprofils oder wird abgeschnitten. Ausschnitt prüfen; kein automatischer Upload.')
    return spans,decisions
