import json
import re
from urllib.parse import urlparse,quote
import requests


class Lumia:
    def __init__(self,cfg,credentials):
        self.cfg=cfg; self.credentials=credentials
        self.session=requests.Session(); self.session.trust_env=False

    def call(self,kind,params=None,timeout=20):
        url=self.cfg['lumia_url'].rstrip('/')+'/send'
        try:
            response=self.session.post(url,params={'token':self.credentials['lumia_token'],'name':'CNG Clip Dienst'},json={'type':kind,'params':params or {}},timeout=timeout)
            data=response.json()
        except requests.RequestException as exc:
            # Never echo requests' URL/exception: it contains the API token.
            raise RuntimeError('Lumia ist nicht erreichbar oder hat nicht rechtzeitig geantwortet.') from None
        if response.status_code>=400 or int(data.get('status',200))>=400:
            raise RuntimeError('Lumia hat die Anfrage abgelehnt (Status '+str(data.get('status',response.status_code))+').')
        return data

    def variable(self,name): return self.call('get-variable-value',{'name':name}).get('message','')

    def command(self,stage,ident,**extra):
        return self.call('chat-command',{'value':self.cfg['command'],'extraSettings':{
            'cng_stage':stage,'cng_clip_id':ident,'cng_bridge_key':self.credentials['bridge_key'],
            'cng_service_url':f"http://127.0.0.1:{self.cfg['port']}",**extra}},timeout=30)

    def recent_clip_events(self):
        try:
            response=self.session.post(self.cfg['lumia_url'].rstrip('/')+'/mcp',
                headers={'Authorization':'Bearer '+self.credentials['lumia_token'],'Accept':'application/json, text/event-stream'},
                json={'jsonrpc':'2.0','id':'cng-clips','method':'tools/call','params':{'name':'get_recent_events','arguments':{'type':'clip','origin':'twitch','limit':200}}},timeout=12)
            response.raise_for_status()
            if response.headers.get('Content-Type','').startswith('text/event-stream'):
                messages=[json.loads(line[5:].strip()) for line in response.text.splitlines() if line.startswith('data:')]
                payload=messages[-1]
            else: payload=response.json()
            content=payload['result']['content']
            result=json.loads(next(item['text'] for item in content if item.get('type')=='text'))
            return result.get('events',[])
        except Exception: raise RuntimeError('Lumias Clip-Ereignispuffer ist momentan nicht erreichbar.') from None

    def events(self,stop,on_event,on_status):
        import websocket
        parsed=urlparse(self.cfg['lumia_url']); scheme='wss' if parsed.scheme=='https' else 'ws'
        url=f"{scheme}://{parsed.netloc}{parsed.path}?token={quote(self.credentials['lumia_token'])}&name=CNG%20Clip%20Dienst"
        backoff=2
        while not stop.is_set():
            socket=None
            try:
                socket=websocket.create_connection(url,timeout=3,http_proxy_host=None)
                socket.send(json.dumps({'subscribe':['alert']})); on_status('Lumia verbunden · wartet auf neue Twitch-Clips'); backoff=2
                # Recover buffered events once on (re)connection; keep the websocket open thereafter.
                try:
                    for event in self.recent_clip_events():
                        if event.get('type')=='alert' and event.get('origin')=='twitch' and event.get('event')=='twitch-clip': on_event(event)
                except Exception: pass
                while not stop.is_set():
                    try: raw=socket.recv()
                    except websocket.WebSocketTimeoutException: continue
                    if not raw: break
                    data=json.loads(raw)
                    if data.get('type')=='alert' and data.get('origin')=='twitch' and data.get('event')=='twitch-clip': on_event(data)
            except Exception:
                on_status('Lumia-Verbindung unterbrochen · erneuter Versuch folgt')
            finally:
                if socket:
                    try: socket.close()
                    except Exception: pass
            stop.wait(backoff); backoff=min(60,backoff*2)
