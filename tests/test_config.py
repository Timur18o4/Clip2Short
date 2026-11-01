import unittest
from clip2short.config import channel_name


class ChannelTests(unittest.TestCase):
    def test_channel_setup_accepts_name_without_changing_the_account(self):
        self.assertEqual(channel_name('  @Demo_Kanal12  '),'demo_kanal12')

    def test_channel_setup_rejects_urls_and_invalid_names(self):
        for value in ('','https://twitch.tv/demo','two names','name-with-dash','x'*26):
            with self.assertRaises(ValueError):channel_name(value)


if __name__=='__main__':unittest.main()
