import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
from clip2short.config import save_config,load_config,load_secrets
from clip2short.design import validate,render_design
from clip2short.studio import background,save,source_path
from clip2short.wizard import SetupSession,action
from clip_engine.artwork import build_layout,build_artwork,caption_artwork


class StudioTests(unittest.TestCase):
    def setUp(self):
        parent=Path(__file__).resolve().parents[1]/'.test-temp';parent.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.session=SetupSession(self.root);self.session.program_root=self.root

    def test_first_run_does_not_arm_queue_or_copy_personal_branding(self):
        self.assertFalse((self.root/'jobs.sqlite3').exists())
        self.assertFalse(self.session.cfg['auto_upload']);self.assertEqual(self.session.cfg['brand'],'')

    def test_connection_failure_keeps_credentials_and_config_untouched(self):
        with patch('clip2short.wizard.Lumia') as factory:
            factory.return_value.probe_native.side_effect=RuntimeError('Verbindung fehlt')
            with self.assertRaises(RuntimeError):action(self.session,'/api/setup/connect',{'token':'test','url':'http://127.0.0.1:39231/api'})
        self.assertFalse((self.root/'credentials.dpapi').exists());self.assertFalse((self.root/'config.json').exists())

    def test_setup_preserves_key_and_does_not_create_any_lumia_command(self):
        key=self.session.credentials['bridge_key']
        with patch('clip2short.wizard.Lumia') as factory:
            factory.return_value.probe_native.return_value={'channel':'example','native':True}
            factory.return_value.evaluate.return_value='CLIP2SHORT_OK'
            action(self.session,'/api/setup/connect',{'token':'test','url':'http://127.0.0.1:39231/api'})
            self.session.http=Mock()
            result=action(self.session,'/api/setup/finish',{'ai_provider':'lumia','auto_upload':False,'privacy':'SELF_ONLY','autostart':False})
            factory.return_value.command.assert_not_called()
        self.assertTrue(result['ok']);self.assertEqual(load_secrets(self.root)['bridge_key'],key)
        self.assertEqual(load_config(self.root)['channel'],'example');self.assertEqual(load_config(self.root)['transport'],'native')
        self.assertFalse((self.root/'jobs.sqlite3').exists())

    def test_unavailable_lumia_ai_is_caught_before_first_setup_is_saved(self):
        with patch('clip2short.wizard.Lumia') as factory:
            factory.return_value.probe_native.return_value={'channel':'example','native':True}
            factory.return_value.evaluate.return_value=''
            action(self.session,'/api/setup/connect',{'token':'test','url':'http://127.0.0.1:39231/api'})
            with self.assertRaisesRegex(ValueError,'Text-KI'):
                action(self.session,'/api/setup/finish',{'ai_provider':'lumia','auto_upload':False,'privacy':'SELF_ONLY'})
        self.assertFalse((self.root/'credentials.dpapi').exists())

    def test_background_is_a_managed_copy_and_path_escape_is_rejected(self):
        raw=io.BytesIO();Image.new('RGB',(40,60),'#ab1234').save(raw,format='PNG')
        asset=background(self.session,raw.getvalue())['asset']
        design=validate({'preset':'minimal','background_image':asset})
        self.assertEqual(Path(render_design({'design':design},self.root)['background_path']).parent,self.root/'assets')
        for bad in ['../photo.png','C:/private.png','file:///test.png']:
            with self.assertRaises(ValueError):validate({'background_image':bad})

    def test_preview_reference_cannot_escape_to_arbitrary_files_or_jobs(self):
        for bad in ['reference:../test','job:../../test','C:/test.mp4']:
            with self.assertRaises(ValueError):source_path(self.session,bad)

    def test_invalid_design_save_is_atomic(self):
        before=copy.deepcopy(self.session.cfg)
        with self.assertRaises(ValueError):save(self.session,{'profiles':before['profiles'],'design':{'accent':'not-a-color'}})
        self.assertEqual(self.session.cfg,before);self.assertFalse((self.root/'config.json').exists())

    def test_custom_slots_and_colors_are_used_by_the_export_artwork(self):
        design=validate({'preset':'minimal','targets':{'camera':{'main':{'x':.1,'y':.4,'width':.8,'height':.4},'caption':{'x':.1,'y':.2,'width':.8,'height':.1}}}})
        project={'mode':'just_chatting','scene_name':'camera','design':design,'brand':'','channel':'EXAMPLE','title':'Eigener Titel'}
        layout=build_layout(project,{'width':1920,'height':1080})
        self.assertGreaterEqual(layout['main']['x'],108);self.assertEqual(layout['caption_box'],(108,384,864,192))
        back,front=build_artwork(project,layout)
        self.assertEqual(back.getpixel((10,10)),(238,238,243));self.assertEqual(front.size,(1080,1920))
        self.assertIsNotNone(caption_artwork(project,layout,'Ein Untertitel').getbbox())

    def test_subtitle_overlap_with_video_is_rejected_in_preview_and_export(self):
        design=validate({'targets':{'camera':{'caption':{'x':.1,'y':.5,'width':.8,'height':.1}}}})
        with self.assertRaisesRegex(ValueError,'überlappt'):
            build_layout({'mode':'just_chatting','design':design},{'width':1920,'height':1080})

    def test_unusable_text_boxes_are_rejected_before_rendering(self):
        with self.assertRaises(ValueError):validate({'targets':{'camera':{'caption':{'x':0,'y':0,'width':.01,'height':.01}}}})


if __name__=='__main__':unittest.main()
