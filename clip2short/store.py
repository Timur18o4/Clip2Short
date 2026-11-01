"""Durable clip identity, activation cutoff and upload claim barrier."""
import json
import sqlite3
import threading
from datetime import datetime,timezone
from pathlib import Path


def now(): return datetime.now(timezone.utc).isoformat()


def instant(value):
    if isinstance(value,(int,float)): return datetime.fromtimestamp(value/1000 if value>1e11 else value,timezone.utc)
    result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if result.tzinfo is None: raise ValueError('Zeitangabe benötigt eine Zeitzone.')
    return result.astimezone(timezone.utc)


class Store:
    def __init__(self,root):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock(); self.db=sqlite3.connect(self.root/'jobs.sqlite3',check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL'); self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,state TEXT NOT NULL,data TEXT NOT NULL,updated TEXT NOT NULL);')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)',('armed_at',now()))
            # A crash at this boundary can have left a real TikTok post.
            self.db.execute("UPDATE jobs SET state='uncertain',updated=? WHERE state IN ('uploading','dispatching')",(now(),))
            self.db.execute("UPDATE jobs SET state='queued',updated=? WHERE state IN ('downloading','transcribing','analyzing','rendering')",(now(),))
            for ident,raw in self.db.execute('SELECT id,data FROM jobs').fetchall():
                data=json.loads(raw)
                if data.get('preview_rendering'):
                    data.update(preview_rendering=False,preview_error='Vorschau wurde durch den Neustart unterbrochen. Sie kann erneut erstellt werden.')
                    self.db.execute('UPDATE jobs SET data=? WHERE id=?',(json.dumps(data,ensure_ascii=False),ident))

    @property
    def armed_at(self):
        with self.lock: return self.db.execute("SELECT value FROM meta WHERE key='armed_at'").fetchone()[0]

    def eligible(self,clip,channel):
        if str(clip.get('broadcaster_name','')).casefold()!=channel.casefold(): return False,'anderer Kanal'
        try:
            created=instant(clip['created_at'])
            if created<=instant(self.armed_at): return False,'vor Aktivierung erstellt'
            if (created-instant(now())).total_seconds()>120: return False,'Erstellungsdatum liegt in der Zukunft'
        except (ValueError,KeyError,TypeError): return False,'Erstellungsdatum fehlt oder ist ungültig'
        return True,''

    def get(self,ident):
        with self.lock:
            row=self.db.execute('SELECT state,data,updated FROM jobs WHERE id=?',(ident,)).fetchone()
        return {'id':ident,'state':row[0],**json.loads(row[1]),'updated':row[2]} if row else None

    def put(self,ident,state,**fields):
        with self.lock,self.db:
            old=self.get(ident) or {}; old.update(fields)
            for key in ('id','state','updated'): old.pop(key,None)
            self.db.execute('INSERT INTO jobs VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,data=excluded.data,updated=excluded.updated',(ident,state,json.dumps(old,ensure_ascii=False),now()))
        return self.get(ident)

    def create(self,clip,channel,**fields):
        ok,reason=self.eligible(clip,channel)
        if not ok: return None,reason
        ident=clip['id']
        with self.lock,self.db:
            existing=self.get(ident)
            if existing and existing['state']!='resolving': return existing,'bereits bekannt'
            return self.put(ident,'queued',clip=clip,**fields),''

    def list(self,limit=100):
        with self.lock: ids=[r[0] for r in self.db.execute('SELECT id FROM jobs ORDER BY updated DESC LIMIT ?',(limit,))]
        return [self.get(i) for i in ids]

    def update_if(self,ident,expected,state=None,**fields):
        with self.lock,self.db:
            job=self.get(ident)
            if not job or job['state']!=expected: return None
            return self.put(ident,state or expected,**fields)

    def update_fields(self,ident,**fields):
        with self.lock,self.db:
            job=self.get(ident)
            return self.put(ident,job['state'],**fields) if job else None

    def claim(self,ident):
        with self.lock,self.db:
            result=self.db.execute("UPDATE jobs SET state='uploading',updated=? WHERE id=? AND state='ready'",(now(),ident))
            return result.rowcount==1

    def close(self): self.db.close()
