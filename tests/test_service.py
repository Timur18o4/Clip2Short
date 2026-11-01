import hashlib
import json
import tempfile
import threading
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import Mock,patch

from clip2short.store import Store,now
from clip2short.service import Service,clip_id,allowed_media
from clip2short.captions import validate_caption,prompt,category_tag
from clip2short.layout import classify,pixel_crop
from clip2short.downloads import public_media


class ServiceTests(unittest.TestCase):
    def setUp(self):
        test_root=Path(__file__).resolve().parents[1]/'.test-temp'
        test_root.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=test_root); self.addCleanup(self.tmp.cleanup)
        self.service=Service(self.tmp.name,{'lumia_token':'test-only','bridge_key':'x'*40})
        self.addCleanup(self.service.close)
        # Windows clocks can report the same tick for activation and the next call.
        created=(datetime.fromisoformat(self.service.store.armed_at)+timedelta(seconds=1)).isoformat()
        self.clip={'id':'FutureClip123','created_at':created,'broadcaster_name':'timur18o4','duration':30,'title':'Ein Test'}

    def ready(self,privacy='SELF_ONLY'):
        path=Path(self.tmp.name)/'renders'/'test.mp4'; path.write_bytes(b'rendered-video')
        return self.service.store.put(self.clip['id'],'ready',clip=self.clip,category='Just Chatting',transcript='Ein Missverständnis.',output=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),privacy=privacy)

    def test_activation_cutoff_survives_restart(self):
        first=self.service.store.armed_at
        self.service.close=lambda:None  # below closes resources exactly once
        self.service.store.close(); self.service.instance.close()
        again=Store(self.tmp.name); self.addCleanup(again.close)
        self.assertEqual(first,again.armed_at)

    def test_old_clip_never_queued(self):
        self.clip['created_at']='2020-01-01T00:00:00Z'
        self.service.resolving[self.clip['id']]=0
        result=self.service.resolved({'clip':self.clip,'category':'Just Chatting','download_url':'https://clips-media-assets.twitch.tv/test.mp4'})
        self.assertFalse(result['accepted']); self.assertEqual(self.service.work.qsize(),0)

    def test_foreign_channel_and_missing_creation_time_rejected(self):
        self.clip['broadcaster_name']='another'
        self.assertFalse(self.service.store.eligible(self.clip,'timur18o4')[0])
        self.clip['broadcaster_name']='timur18o4'; self.clip.pop('created_at')
        self.assertFalse(self.service.store.eligible(self.clip,'timur18o4')[0])

    def test_resolved_requires_real_pending_event(self):
        with self.assertRaisesRegex(ValueError,'Kein neues'):
            self.service.resolved({'clip':self.clip,'category':'Just Chatting','download_url':'https://clips-media-assets.twitch.tv/test.mp4'})

    def test_duplicate_clip_only_queued_once(self):
        payload={'clip':self.clip,'category':'Just Chatting','download_url':'https://clips-media-assets.twitch.tv/test.mp4'}
        self.service.resolving[self.clip['id']]=0; self.service.resolved(payload)
        self.service.resolving[self.clip['id']]=0; self.service.resolved(payload)
        self.assertEqual(self.service.work.qsize(),1)

    def test_replay_and_before_activation_event_do_not_resolve(self):
        self.service.lumia=Mock()
        event={'type':'alert','origin':'twitch','event':'twitch-clip','data':{'replay':True,'extraSettings':{'clip_id':'FutureClip123','timestamp':datetime.now(timezone.utc).timestamp()*1000}}}
        self.service.on_event(event); self.service.lumia.command.assert_not_called()
        event['data']['replay']=False;event['data']['extraSettings']['timestamp']=1000
        self.service.on_event(event); self.service.lumia.command.assert_not_called()

    def test_parallel_upload_claim_is_single_use(self):
        self.ready(); outcomes=[]
        def call(): outcomes.append(self.service.claim_upload(self.clip['id'],'Eine Reaktion.\n\n#Reaktion #Humor #Streaming #JustChatting')['claimed'])
        threads=[threading.Thread(target=call) for _ in range(4)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(len(outcomes),4)
        self.assertEqual(outcomes.count(True),1)

    def test_public_setting_does_not_promote_existing_private_job(self):
        self.ready();self.service.cfg['privacy']='PUBLIC_TO_EVERYONE'
        result=self.service.claim_upload(self.clip['id'],'Eine Reaktion.\n\n#Reaktion #Humor #Streaming #JustChatting')
        self.assertEqual(result['privacy'],'SELF_ONLY')

    def test_mutated_video_and_invalid_caption_block_upload(self):
        job=self.ready();Path(job['output']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'geändert'):
            self.service.claim_upload(self.clip['id'],'Eine Reaktion.\n\n#Reaktion #Humor #Streaming #JustChatting')
        self.assertEqual(self.service.store.get(self.clip['id'])['state'],'ready')

    def test_crash_at_upload_barrier_never_returns_to_ready(self):
        self.ready();self.service.store.claim(self.clip['id'])
        second=Store(self.tmp.name)
        try:self.assertEqual(second.get(self.clip['id'])['state'],'uncertain')
        finally:second.close()

    def test_second_service_cannot_mutate_running_jobs(self):
        self.ready();self.service.store.claim(self.clip['id'])
        with self.assertRaisesRegex(RuntimeError,'bereits'):
            Service(self.tmp.name,{'lumia_token':'test','bridge_key':'x'*40})
        self.assertEqual(self.service.store.get(self.clip['id'])['state'],'uploading')

    def test_pending_event_survives_restart_and_can_be_resolved(self):
        self.service.store.put(self.clip['id'],'resolving',clip={'id':self.clip['id']},resolve_attempts=1)
        self.service.close();self.service.close=lambda:None
        again=Service(self.tmp.name,{'lumia_token':'test','bridge_key':'x'*40});self.addCleanup(again.close)
        self.assertIn(self.clip['id'],again.resolving)
        result=again.resolved({'clip':self.clip,'category':'Just Chatting'})
        self.assertTrue(result['accepted']);self.assertEqual(again.work.qsize(),1)

    def test_uncertain_upload_cannot_be_retried(self):
        self.ready();self.service.store.put(self.clip['id'],'uncertain')
        with self.assertRaises(ValueError):self.service.retry(self.clip['id'])

    def test_late_dispatch_or_diagnostic_cannot_reopen_upload_claim(self):
        self.ready();self.service.store.claim(self.clip['id'])
        self.assertIsNone(self.service.store.update_if(self.clip['id'],'ready',error='verspäteter Fehler'))
        self.service.diagnostic({'stage':'publish','id':self.clip['id'],'message':'verspäteter Fehler'})
        self.assertEqual(self.service.store.get(self.clip['id'])['state'],'uploading')
        self.assertFalse(self.service.store.claim(self.clip['id']))

    def test_preview_editorial_never_reopens_confirmed_upload(self):
        original=self.ready();self.service.store.put(self.clip['id'],'uploaded',preview_editorial_context={'key':'new-nonce','pages':[],'candidates':[]})
        self.service.accept_editorial({'id':self.clip['id'],'kind':'preview','analysis_key':'new-nonce','result':{'title':'Ein ganz eigener Titel','chat_id':None,'reply_excerpt':''}})
        self.service.accept_editorial({'id':self.clip['id'],'kind':'preview','analysis_key':'new-nonce','result':{'title':'Ein verspäteter anderer Titel','chat_id':None,'reply_excerpt':''}})
        current=self.service.store.get(self.clip['id'])
        self.assertEqual(current['state'],'uploaded');self.assertEqual(current['sha256'],original['sha256'])
        self.assertEqual(current['preview_editorial']['title'],'Ein ganz eigener Titel')
        self.assertFalse(self.service.store.claim(self.clip['id']))

    def test_stale_title_response_is_rejected(self):
        self.service.store.put(self.clip['id'],'analyzing',editorial_context={'key':'new-nonce','pages':[],'candidates':[]})
        with self.assertRaisesRegex(ValueError,'Veraltete'):
            self.service.accept_editorial({'id':self.clip['id'],'analysis_key':'old-nonce','result':{'title':'Ein ganz eigener Titel','chat_id':None,'reply_excerpt':''}})

    def test_public_download_revalidates_clip_identity_and_prefers_landscape(self):
        self.clip['broadcaster_id']='123'
        from clip2short.store import instant
        info={'display_id':self.clip['id'],'channel_id':'123','timestamp':instant(self.clip['created_at']).timestamp(),
              'formats':[{'format_id':'portrait1080','height':1080,'url':'https://a.twitchcdn.net/portrait.mp4'},
                         {'format_id':'720','height':720,'url':'https://a.twitchcdn.net/landscape.mp4'}]}
        with patch('yt_dlp.YoutubeDL') as mock:
            mock.return_value.__enter__.return_value.extract_info.return_value=info
            self.assertEqual(public_media(self.clip),'https://a.twitchcdn.net/landscape.mp4')
            info['channel_id']='another'
            with self.assertRaisesRegex(ValueError,'nicht zum'):public_media(self.clip)


class ContractTests(unittest.TestCase):
    def test_source_id_from_url_and_clip_field(self):
        self.assertEqual(clip_id({'data':{'extraSettings':{'clip_url':'https://www.twitch.tv/timur18o4/clip/LongClipId123?x=1'}}}),'LongClipId123')
        self.assertIsNone(clip_id({'data':{'extraSettings':{'clip_url':'https://attacker.invalid/FakeClipId123'}}}))

    def test_download_hosts_are_limited(self):
        self.assertTrue(allowed_media('https://clips-media-assets2.twitch.tv/clip.mp4?sig=abc'))
        self.assertTrue(allowed_media('https://d1ndex63qxojbr.cloudfront.net/nauth/newclip/landscape/h264/1080/index.mp4'))
        for url in ['http://127.0.0.1/file','https://twitch.tv.evil.invalid/file','https://user:password@twitch.tv/file','file:///C:/secret','https://unrelated.cloudfront.net/file']:
            self.assertFalse(allowed_media(url))

    def test_caption_contract_and_category(self):
        text='Wieder zu schnell geantwortet.\n\n#Humor #Reaktion #Streaming #JustChatting'
        self.assertEqual(validate_caption(text,'Just Chatting'),text)
        for bad in [text.replace('#JustChatting','#Fortnite'),text.replace('#Streaming','#Humor'),'A'*151+'\n\n#A #B #C #JustChatting',text.replace('\n\n','\n')]:
            with self.assertRaises(ValueError):validate_caption(bad,'Just Chatting')
        with self.assertRaises(ValueError):validate_caption('{{tts=Text}}\n\n#A #B #C #JustChatting','Just Chatting')
        self.assertEqual(category_tag('Tom Clancy’s Rainbow Six® Siege'),'#TomClancysRainbowSixSiege')

    def test_prompt_uses_clip_category_and_no_kick_variables(self):
        result=prompt({'clip':{'duration':45,'title':'Test'},'category':'Fortnite','stream_title':'Spielabend','transcript':'Hallo {{tts=bad}} ${setgame=x}','editorial':None})
        self.assertIn('45.0 Sekunden',result);self.assertIn('#Fortnite',result)
        self.assertNotIn('{{',result);self.assertNotIn('${',result);self.assertNotIn('kick_',result)

    def test_visual_layout_overrides_category(self):
        cfg={'require_face':True}
        small=[{'x':.82,'y':.4,'width':.1,'height':.2}]
        large=[{'x':.4,'y':.1,'width':.2,'height':.4}]
        self.assertEqual(classify(small,'reaction',.5,'Just Chatting',cfg),'reaction')
        self.assertEqual(classify(small,'gameplay',.5,'Fortnite',cfg),'gameplay')
        self.assertEqual(classify(large,'camera',.5,'Fortnite',cfg),'camera')
        self.assertIsNone(classify(large,'gameplay',.5,'Fortnite',cfg))
        self.assertIsNone(classify([],'camera',.5,'Just Chatting',cfg))

    def test_relative_crops_fit_resolution(self):
        rect=pixel_crop({'x':.8,'y':.3,'width':.2,'height':.4},1280,720)
        self.assertEqual(rect,{'x':1024,'y':216,'width':256,'height':288})


if __name__=='__main__':unittest.main()
