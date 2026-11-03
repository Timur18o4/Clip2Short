from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from clip2short import twitch, wizard
from clip2short.config import load_config, load_secrets


class TwitchTests(TestCase):
    def test_poll_only_queues_new_unique_clips_for_configured_channel(self):
        cutoff = '2026-11-04T10:00:00+00:00'
        end = '2026-11-04T10:00:30+00:00'

        def clip(ident, date=end, channel='123'):
            return dict(id=ident, created_at=date, broadcaster_id=channel)

        store = Mock(armed_at=cutoff)
        store.get.side_effect = lambda ident: {'id': ident} if ident == 'KnownClip123' else None
        stop = Mock()
        stop.is_set.side_effect = lambda: stop.wait.called
        service = SimpleNamespace(
            cfg={'enabled': True, 'broadcaster_id': '123', 'twitch_started_at': cutoff},
            credentials={'twitch_client_id': 'fixture', 'twitch_client_secret': 'fixture'},
            stop=stop, store=store, log=Mock(), guard=RLock(), resolving={},
        )
        with patch.object(twitch, 'Twitch') as client, patch.object(twitch, 'now', return_value=end):
            client.return_value.clips.return_value = iter([
                clip('OldClip123', cutoff), clip('WrongClip123', channel='456'),
                clip('KnownClip123'), clip('FreshClip123'), clip('FreshClip123'),
            ])
            twitch.listen(service)
        self.assertEqual(store.put.call_count, 1)
        self.assertEqual(store.put.call_args.args[:2], ('FreshClip123', 'resolving'))
        stop.wait.assert_called_once_with(30)

    def test_first_setup_can_finish_without_lumia(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            setup = wizard.SetupSession(root)
            setup.program_root = root
            setup.http = Mock()
            with patch.object(twitch, 'Twitch') as client, patch.object(wizard.threading, 'Timer'):
                client.return_value.broadcaster.return_value = '123'
                result = wizard.action(setup, '/api/setup/finish', {
                    'clip_source': 'twitch', 'twitch_channel': 'example',
                    'twitch_client_id': 'fixture-id', 'twitch_client_secret': 'fixture-secret',
                    'ai_provider': 'none', 'privacy': 'SELF_ONLY',
                })
            self.assertTrue(result['first_run'])
            self.assertEqual(load_secrets(root)['lumia_token'], '')
            self.assertEqual(load_secrets(root)['twitch_client_secret'], 'fixture-secret')
            self.assertEqual(load_config(root)['clip_source'], 'twitch')
            self.assertFalse(load_config(root)['auto_upload'])
            self.assertNotIn('fixture-secret', (root/'config.json').read_text())
