"""Validated design presets and relative output rectangles shared with the editor."""
import copy
import math
import re
from pathlib import Path

PRESETS={
 'classic':{'name':'Klassisch','background':'#101015','accent':'#ffd13f','title':'#ffffff','subtitle':'#ffffff','panel':'#0c0c10','quote':'#d4cfd4','footer':'#ffffff','font':'arial','radius':8},
 'minimal':{'name':'Hell und schlicht','background':'#eeeef3','accent':'#3157ce','title':'#172037','subtitle':'#ffffff','panel':'#172037','quote':'#35415a','footer':'#172037','font':'segoe','radius':14},
 'neon':{'name':'Neon','background':'#111025','accent':'#5df2d6','title':'#ffffff','subtitle':'#ffffff','panel':'#252045','quote':'#dfd5ff','footer':'#ffffff','font':'arial','radius':24},
}
PARTS={'main','facecam','title','caption','quote','category','footer'}


def rect(value):
    if not isinstance(value,dict) or set(value)!={'x','y','width','height'}:raise ValueError('Ein Ausschnitt benötigt Position, Breite und Höhe.')
    if any(isinstance(value[k],bool) or not isinstance(value[k],(int,float)) or not math.isfinite(value[k]) for k in value):raise ValueError('Ungültiger Bildausschnitt.')
    if min(value['x'],value['y'])<0 or min(value['width'],value['height'])<=0 or value['x']+value['width']>1.000001 or value['y']+value['height']>1.000001:raise ValueError('Der Ausschnitt muss innerhalb des Bilds liegen.')
    return {k:float(v) for k,v in value.items()}


def validate(value):
    if not isinstance(value,dict):raise ValueError('Ungültige Gestaltung.')
    preset=value.get('preset','classic')
    if preset not in PRESETS:raise ValueError('Unbekannte Designvorlage.')
    result={**PRESETS[preset],'preset':preset,'background_image':'','targets':{}}
    for key in ('background','accent','title','subtitle','panel','quote','footer'):
        color=value.get(key,result[key])
        if not isinstance(color,str) or not re.fullmatch('#[0-9a-fA-F]{6}',color):raise ValueError('Farben müssen im Format #RRGGBB vorliegen.')
        result[key]=color
    result['font']=value.get('font',result['font'])
    if result['font'] not in ('arial','segoe','impact'):raise ValueError('Unbekannte Schriftart.')
    radius=value.get('radius',result['radius'])
    if isinstance(radius,bool) or not isinstance(radius,(int,float)) or not math.isfinite(radius) or not 0<=radius<=60:raise ValueError('Eckenradius muss zwischen 0 und 60 liegen.')
    result['radius']=round(radius)
    asset=value.get('background_image','')
    if asset and not re.fullmatch('[a-f0-9]{32}\\.png',str(asset)):raise ValueError('Hintergrundbild muss über den Editor geladen werden.')
    result['background_image']=asset
    targets=value.get('targets',{})
    if not isinstance(targets,dict):raise ValueError('Ungültige Zielflächen.')
    for mode,parts in targets.items():
        if mode not in ('camera','gameplay','reaction') or not isinstance(parts,dict) or set(parts)-PARTS:raise ValueError('Unbekannte Bildfläche.')
        result['targets'][mode]={part:rect(r) for part,r in parts.items()}
        for part,r in result['targets'][mode].items():
            if part not in ('main','facecam') and (r['width']*1080<80 or r['height']*1920<48):raise ValueError('Textflächen benötigen mindestens 80 × 48 Bildpunkte.')
    return result


def render_design(cfg,root):
    if not cfg.get('design'):return {}
    value=validate(cfg['design'])
    if value['background_image']:
        asset=(Path(root)/'assets'/value['background_image']).resolve()
        if asset.parent!=(Path(root)/'assets').resolve() or not asset.is_file():raise ValueError('Gespeichertes Hintergrundbild fehlt.')
        value['background_path']=str(asset)
    return value
