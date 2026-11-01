import unittest
from cng_clip_service.editorial import validate,messages,instruction
from clip_engine.artwork import build_layout


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.context={'pages':[{'start':12,'end':15,'text':'hier ist doch aber kein Feiertag'}],
                      'candidates':[{'id':'observed','text':'Halloween ist doch aber kein Feiertag?','confidence':.995,'seen':3,'first_time':12,'last_time':20}]}

    def test_quote_is_selected_from_observed_original(self):
        result=validate({'title':'Feiertag? Jetzt bin ich raus','chat_id':'observed','reply_excerpt':'hier ist doch aber kein Feiertag'},self.context)
        self.assertEqual(result['chat_quote'],self.context['candidates'][0]['text'])

    def test_fabricated_quote_or_missing_reply_is_rejected(self):
        for selection,excerpt in [('invented','hier ist doch aber kein Feiertag'),('observed','Das habe ich nie gesagt')]:
            with self.assertRaises(ValueError):validate({'title':'Feiertag? Jetzt bin ich raus','chat_id':selection,'reply_excerpt':excerpt},self.context)

    def test_no_chat_relation_produces_no_quote(self):
        result=validate({'title':'Feiertag? Jetzt bin ich raus','chat_id':None,'reply_excerpt':''},self.context)
        self.assertEqual(result['chat_quote'],'')

    def test_lumia_plain_text_protocol_preserves_observed_quote(self):
        result=validate('TITLE=Feiertag? Jetzt bin ich raus\nCHAT_ID=observed\nREPLY_EXCERPT=hier ist doch aber kein Feiertag',self.context)
        self.assertEqual(result['chat_quote'],'Halloween ist doch aber kein Feiertag?')

    def test_single_frame_or_uncertain_ocr_is_not_quoted(self):
        self.context['candidates'][0]['seen']=1
        with self.assertRaises(ValueError):validate({'title':'Feiertag? Jetzt bin ich raus','chat_id':'observed','reply_excerpt':'hier ist doch aber kein Feiertag'},self.context)

    def test_twitch_placeholder_is_not_an_ai_title(self):
        with self.assertRaises(ValueError):validate({'title':'testclip','chat_id':None,'reply_excerpt':''},self.context)

    def test_only_text_under_a_chat_header_is_a_candidate(self):
        def line(text,y,score=.99):return {'text':text,'top':y,'bottom':y+20,'left':10,'score':score}
        result=messages([line('GAME SCORE 25',0),line('TWITCH DemoChatUser',100),line('Halloween ist doch aber kein Feiertag?',125),line('TIKTOK Zuschauer',180),line('Zuschauer hat 15 Likes gesendet!',205)])
        self.assertEqual([x['text'] for x in result],['Halloween ist doch aber kein Feiertag?'])

    def test_moderator_badge_on_header_row_is_not_part_of_message(self):
        result=messages([{'text':'TWITCH DemoChatUser','top':625,'bottom':652,'left':118,'score':.99},
                         {'text':'MOD FLAMEBORN-SIGIL','top':627,'bottom':650,'left':312,'score':.99},
                         {'text':'Halloween ist doch aber kein Feiertag?','top':658,'bottom':688,'left':116,'score':.99}])
        self.assertEqual(result[0]['text'],'Halloween ist doch aber kein Feiertag?')

    def test_quote_box_stays_above_captions_and_outside_webcam(self):
        for mode in ('gameplay','just_chatting'):
            layout=build_layout({'mode':mode,'chat_quote':'Nachricht aus dem Chat'}, {'width':1920,'height':1080})
            x,y,w,h=layout['quote_box'];cx,cy,cw,ch=layout['caption_box']
            self.assertLessEqual(y+h,cy);self.assertLessEqual(cy+ch,660)
            if mode=='gameplay':self.assertLessEqual(x+w,layout['facecam']['x'])


if __name__=='__main__':unittest.main()
