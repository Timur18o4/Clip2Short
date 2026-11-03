import hashlib
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import Mock,patch
from clip2short.service import Service
from clip2short.lumia import Lumia
from clip2short.downloads import resolve_public
from clip2short.ai import generate,local_url


class NativeTests(unittest.TestCase):
    def test_native_probe_needs_no_chat_command(self):
        lumia=Lumia({'lumia_url':'http://127.0.0.1:39231/api'},{'lumia_token':'fixture'})
        lumia.call=Mock(return_value={'status':200});lumia.variable=Mock(side_effect=['42','example','example','123'])
        result=lumia.probe_native()
        self.assertEqual(result['channel'],'example')
        self.assertTrue(all(c.args[0]=='run-actions' for c in lumia.call.call_args_list))
        self.assertEqual(lumia.call.call_args_list[-1].args[1]['actions'][0]['value']['message'],'')

    def test_template_call_uses_unique_variables_and_cleans_after_failure(self):
        lumia=Lumia({},{});lumia.run_actions=Mock(side_effect=[TimeoutError(),None])
        with self.assertRaises(TimeoutError):lumia.evaluate('test')
        first,last=lumia.run_actions.call_args_list
        self.assertEqual(first.args[0][0]['value']['value'],last.args[0][0]['value']['value'])
        self.assertEqual(last.args[0][0]['value']['message'],'')

    def test_transcript_cannot_inject_lumia_functions(self):
        lumia=Mock();generate({'ai_provider':'lumia'},lumia,'Chat: {{writeToFile=bad}}')
        template=lumia.evaluate.call_args.args[0]
        self.assertEqual(template.count('{{'),1);self.assertEqual(template.count('}}'),1)

    def test_local_ai_rejects_remote_addresses_and_cloud_models(self):
        for url in ['https://example.org','http://user@localhost:11434','http://127.0.0.1:11434/path']:
            with self.assertRaises(ValueError):local_url(url)
        with self.assertRaises(ValueError):generate({'ai_provider':'ollama','ollama_model':'test-cloud'},Mock(),'test')

    def test_local_structured_output_keeps_chat_ids_and_category_controlled(self):
        from clip2short.ai import editorial,caption
        cfg={'ai_provider':'ollama'};job={'category':'Just Chatting','clip':{'duration':30,'title':'Test'}}
        context={'pages':[],'candidates':[{'id':'chat1','text':'Frage'}]}
        with patch('clip2short.ai.generate',return_value='{"title":"Ein eigener Titel","chat_id":null,"reply_excerpt":""}') as call:
            editorial(cfg,None,job,context)
            self.assertEqual(call.call_args.args[3]['properties']['chat_id']['enum'],[None,'chat1'])
        with patch('clip2short.ai.generate',return_value='{"description":"Eine Reaktion.","tag1":"#Humor","tag2":"#Reaktion","tag3":"#Streaming"}'):
            self.assertTrue(caption(cfg,None,job).endswith('#JustChatting'))

    def test_native_metadata_requires_exact_new_clip_and_category(self):
        now=datetime.now(timezone.utc)
        info={'display_id':'NewClip123','channel':'example','channel_id':'123','timestamp':now.timestamp(),'title':'Reaktion','duration':30,'categories':['Just Chatting']}
        with patch('yt_dlp.YoutubeDL') as factory:
            factory.return_value.__enter__.return_value.extract_info.return_value=info
            self.assertEqual(resolve_public('NewClip123','example',(now-timedelta(minutes=1)).isoformat())['category'],'Just Chatting')
            with self.assertRaises(ValueError):resolve_public('NewClip123','other',(now-timedelta(minutes=1)).isoformat())
            with self.assertRaises(ValueError):resolve_public('NewClip123','example',(now+timedelta(seconds=1)).isoformat())
            info['channel']='Nichtlateinischer Anzeigename'
            result=resolve_public('NewClip123','example',(now-timedelta(minutes=1)).isoformat(),'123')
            self.assertEqual(result['clip']['broadcaster_name'],'example')
            with self.assertRaises(ValueError):resolve_public('NewClip123','example',(now-timedelta(minutes=1)).isoformat(),'456')

    def test_native_upload_claim_is_never_reopened_after_timeout(self):
        parent=Path(__file__).resolve().parents[1]/'.test-temp';parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            service=Service(folder,{'lumia_token':'fixture','bridge_key':'x'*40})
            service.cfg['channel']='timur18o4'
            try:
                created=(datetime.fromisoformat(service.store.armed_at)+timedelta(seconds=1)).isoformat()
                clip={'id':'NewClip123','created_at':created,'broadcaster_name':'timur18o4'}
                out=Path(folder)/'renders/test.mp4';out.write_bytes(b'fixture')
                service.store.put(clip['id'],'ready',clip=clip,category='Just Chatting',output=str(out),privacy='SELF_ONLY',sha256=hashlib.sha256(b'fixture').hexdigest())
                service.lumia=Mock();service.lumia.run_actions.side_effect=TimeoutError()
                with patch('clip2short.ai.generate',return_value='Eine Reaktion.\n\n#Humor #Reaktion #Streaming #JustChatting'):
                    with self.assertRaises(TimeoutError):service.publish_native(clip['id'])
                self.assertEqual(service.store.get(clip['id'])['state'],'uncertain')
                self.assertFalse(service.store.claim(clip['id']))
                self.assertEqual(service.lumia.run_actions.call_count,1)
            finally:service.close()


if __name__=='__main__':unittest.main()
