import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
import requests
from cng_clip_service.service import Service
from cng_clip_service.server import serve


class HttpTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[1]/'.test-temp';root.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=root)
        self.service=Service(self.tmp.name,{'lumia_token':'test','bridge_key':'x'*40});self.service.cfg['port']=0
        self.thread=threading.Thread(target=serve,args=(self.service,),daemon=True);self.thread.start()
        for _ in range(100):
            if hasattr(self.service,'http'):break
            time.sleep(.01)
        self.url='http://127.0.0.1:'+str(self.service.http.server_address[1]);self.session=requests.Session();self.session.trust_env=False
        self.auth={'Authorization':'Bearer '+'x'*40}

    def tearDown(self):
        self.service.http.shutdown();self.thread.join(3);self.service.close();self.session.close();self.tmp.cleanup()

    def test_private_routes_require_token_and_local_host(self):
        self.assertEqual(self.session.get(self.url+'/health').status_code,200)
        self.assertEqual(self.session.get(self.url+'/api/status').status_code,401)
        self.assertEqual(self.session.post(self.url+'/api/settings',json={'enabled':False}).status_code,401)
        self.assertEqual(self.session.get(self.url+'/',headers={'Host':'evil.invalid'}).status_code,403)
        result=self.session.get(self.url+'/api/status',headers=self.auth)
        self.assertEqual(result.status_code,200);self.assertNotIn('bridge_key',result.text);self.assertNotIn('lumia_token',result.text)

    def test_invalid_profile_does_not_partially_change_settings(self):
        response=self.session.post(self.url+'/api/settings',headers=self.auth,json={'enabled':False,'profiles':{'camera':{'main':{'x':-1,'y':0,'width':1,'height':1}}}})
        self.assertEqual(response.status_code,400);self.assertTrue(self.service.cfg['enabled'])
        response=self.session.post(self.url+'/api/settings',headers=self.auth,json={'profiles':{'camera':{}}})
        self.assertEqual(response.status_code,400)

    def test_settings_persist_and_no_cross_origin_permission_is_added(self):
        response=self.session.post(self.url+'/api/settings',headers=self.auth,json={'enabled':False})
        self.assertEqual(response.status_code,200)
        saved=json.loads((Path(self.tmp.name)/'config.json').read_text(encoding='utf8'));self.assertFalse(saved['enabled'])
        self.assertNotIn('Access-Control-Allow-Origin',response.headers)


if __name__=='__main__':unittest.main()
