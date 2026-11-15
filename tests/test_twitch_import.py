from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from clip2short import twitch_import
from clip2short.downloads import clip_slug
from clip2short.service import Service


class TwitchImportTests(TestCase):
    def test_channel_list_follows_cursor_then_skips_empty_older_ranges(self):
        service = SimpleNamespace(cfg={'channel':'example','broadcaster_id':'42'},
                                  credentials={'twitch_client_id':'id','twitch_client_secret':'secret'},
                                  store=Mock())
        def clip(ident, date):
            return {'id':ident,'broadcaster_id':'42','created_at':date}

        with patch.object(twitch_import,'now',return_value='2026-11-15T12:00:00Z'), patch.object(twitch_import,'Twitch') as factory:
            get = factory.return_value.get
            get.side_effect = [
                {'data':[{'id':'42','created_at':'2026-08-01T00:00:00Z'}]},
                {'data':[clip('RecentClip123','2026-11-13T00:00:00Z')],'pagination':{'cursor':'next'}},
                {'data':[clip('RecentClip456','2026-11-10T00:00:00Z')]},
                {'data':[]},
                {'data':[clip('OlderClip123','2026-09-20T00:00:00Z')]},
                {'data':[]},
            ]
            first = twitch_import.channel_clips(service)
            second = twitch_import.channel_clips(service,first['next'])
            self.assertEqual(get.call_args.args[1]['after'],'next')
            older = twitch_import.channel_clips(service,second['next'])
            self.assertTrue(older['clips'][0]['url'].endswith('/OlderClip123'))
            self.assertEqual(twitch_import.channel_clips(service,older['next']),{'clips':[],'next':None})

    def test_link_parser_checks_host_and_clip_path(self):
        ident = 'ExampleClip123'
        self.assertEqual(clip_slug(f'https://clips.twitch.tv/{ident}?tt_content=clip'), ident)
        self.assertEqual(clip_slug(f'https://www.twitch.tv/example/clip/{ident}'), ident)
        for url in (
            f'https://clips.twitch.tv.example.org/{ident}',
            f'https://clips.twitch.tv@localhost/{ident}',
            f'https://www.twitch.tv/videos/{ident}',
        ):
            with self.assertRaises(ValueError):
                clip_slug(url)

    def test_explicit_link_import_can_queue_old_clips_once_without_upload(self):
        ident = 'ExampleClip123'
        url = f'https://clips.twitch.tv/{ident}'
        payload = {
            'clip':{'id':ident,'title':'Example','broadcaster_name':'example','created_at':'2024-01-01T00:00:00Z'},
            'thumbnail':'https://static-cdn.jtvnw.net/fixture.jpg','category':'Fortnite',
        }
        with TemporaryDirectory() as folder:
            service = Service(Path(folder), {'lumia_token':'fixture','bridge_key':'fixture'})
            try:
                with patch.object(twitch_import, 'inspect_link', return_value=payload):
                    self.assertFalse(twitch_import.prepare(service,url)['known'])
                    self.assertIsNone(service.store.get(ident))
                    twitch_import.prepare(service,url,enqueue=True)
                    self.assertEqual(service.work.get_nowait(),ident)
                    self.assertTrue(service.store.get(ident)['twitch_import'])
                    with self.assertRaises(ValueError):
                        twitch_import.prepare(service,url,enqueue=True)
                service.store.update_if(ident,'queued','ready')
                with patch.object(service,'publish_native') as publish:
                    service.dispatch(ident)
                publish.assert_not_called()
                with self.assertRaises(ValueError):
                    service.claim_upload(ident,'test')
            finally:
                service.close()
