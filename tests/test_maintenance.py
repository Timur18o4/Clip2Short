import hashlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
import zipfile

from clip2short import studio, updater, wizard
from clip2short.service import Service


class MaintenanceTests(unittest.TestCase):
    def test_removed_clip_stays_known_and_cannot_be_retried(self):
        with TemporaryDirectory() as folder:
            service = Service(folder, {'lumia_token':'fixture', 'bridge_key':'fixture'})
            try:
                ident = 'FixtureClip123'
                service.store.put(ident, 'queued')
                service.remove(ident)
                self.assertEqual(service.store.list(), [])
                self.assertEqual(service.store.get(ident)['state'], 'removed')
                with self.assertRaises(ValueError):
                    service.retry(ident)
                service.store.put('FixtureClip456', 'rendering')
                with self.assertRaises(ValueError):
                    service.remove('FixtureClip456')
            finally:
                service.close()

    def test_local_setup_and_import_require_no_twitch_or_lumia(self):
        with TemporaryDirectory() as folder:
            setup = wizard.SetupSession(folder)
            setup.program_root = Path(folder)
            setup.http = Mock()
            with patch.object(wizard.threading, 'Timer'):
                wizard.action(setup, '/api/setup/finish', {
                    'clip_source':'local', 'ai_provider':'none', 'privacy':'SELF_ONLY',
                })
            service = Service(folder)
            try:
                self.assertEqual(service.cfg['clip_source'], 'local')
                fixture = b'\x00\x00\x00\x18ftypisom'
                with patch('clip_engine.media.probe_media', return_value={'duration':4}):
                    result = studio.import_clip(service, io.BytesIO(fixture), len(fixture), 'test.mp4', 'Fortnite')
                ident = result['id']
                self.assertEqual(service.work.get_nowait(), ident)
                self.assertTrue(service.store.get(ident)['local_import'])
                service.store.update_if(ident, 'queued', 'ready')
                service.credentials['lumia_token'] = 'fixture'
                service.cfg['auto_upload'] = True
                with patch.object(service, 'publish_native') as publish:
                    service.dispatch(ident)
                publish.assert_not_called()
            finally:
                service.close()

    def test_update_package_cannot_escape_program_and_keeps_data_out(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'requirements.txt').write_text('same\n')
            files = {'VERSION':'1.1.1', 'requirements.txt':'same\n',
                     'clip2short/__main__.py':'', 'clip2short/server.py':'',
                     'Daten/config.json':'ignored'}
            for malicious in (False, True):
                with io.BytesIO() as buffer:
                    with zipfile.ZipFile(buffer, 'w') as bundle:
                        for name, content in files.items():
                            bundle.writestr('Clip2Short/'+name, content)
                        if malicious:
                            bundle.writestr('Clip2Short/../outside.txt', 'bad')
                    archive = buffer.getvalue()
                release = {'tag_name':'v1.1.1', 'assets':[{
                    'name':'Clip2Short_Windows_v1.1.1.zip',
                    'digest':'sha256:'+hashlib.sha256(archive).hexdigest(),
                }]}
                stage = root/str(malicious)
                with patch.object(updater, 'read_url', return_value=archive):
                    if malicious:
                        with self.assertRaises(ValueError):
                            updater.stage_release(release, '1.1.0', stage, root)
                    else:
                        self.assertEqual(updater.stage_release(release, '1.1.0', stage, root), '1.1.1')
                        self.assertFalse((stage/'Daten').exists())
                self.assertFalse((root/'outside.txt').exists())
