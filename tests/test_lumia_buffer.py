import json
import unittest
from unittest.mock import Mock
import requests
from clip2short.lumia import Lumia


class LumiaBufferTests(unittest.TestCase):
    def test_reads_sse_event_buffer_without_token_in_url(self):
        event={'origin':'twitch','type':'alert','event':'twitch-clip','data':{'extraSettings':{'clip_id':'NewClip123'}}}
        result={'result':{'content':[{'type':'text','text':json.dumps({'events':[event]})}]}}
        response=Mock();response.headers={'Content-Type':'text/event-stream'};response.text='event: message\ndata: '+json.dumps(result)+'\n\n'
        lumia=Lumia({'lumia_url':'http://127.0.0.1:39231/api'},{'lumia_token':'fixture-secret'})
        lumia.session=Mock();lumia.session.post.return_value=response
        self.assertEqual(lumia.recent_clip_events(),[event])
        call=lumia.session.post.call_args
        self.assertEqual(call.args[0],'http://127.0.0.1:39231/api/mcp')
        self.assertNotIn('fixture-secret',call.args[0])
        self.assertEqual(call.kwargs['json']['params']['arguments']['origin'],'twitch')

    def test_network_error_never_echoes_authentication(self):
        lumia=Lumia({'lumia_url':'http://127.0.0.1:39231/api'},{'lumia_token':'fixture-secret'})
        lumia.session=Mock();lumia.session.post.side_effect=requests.ConnectionError('fixture-secret')
        with self.assertRaises(RuntimeError) as result:lumia.recent_clip_events()
        self.assertNotIn('fixture-secret',str(result.exception))
