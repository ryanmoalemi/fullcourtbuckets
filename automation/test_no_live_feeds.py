"""ESPN and the stats feed stay mocked. These checks do not open a socket."""
import unittest
import urllib.request

import offline_tests
import game_stats
import wnba_sync

offline_tests.install()


class NoLiveFeedTests(unittest.TestCase):
    def test_guard_is_installed(self):
        self.assertIsNot(urllib.request.urlopen, offline_tests._real_urlopen)
        self.assertTrue(offline_tests.blocked_feed('https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard'))
        self.assertTrue(offline_tests.blocked_feed('https://api.balldontlie.io/wnba/v1/games'))
        self.assertFalse(offline_tests.blocked_feed('http://127.0.0.1:8765/'))

    def test_espn_and_the_stats_feed_are_refused_without_a_socket(self):
        urls = (
            'https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates=20261004',
            'https://site.web.api.espn.com/apis/site/v2/sports/basketball/wnba/summary?event=401918295',
            'https://www.espn.com/wnba/scoreboard',
            'https://api.balldontlie.io/wnba/v1/games',
        )
        for url in urls:
            with self.assertRaises(offline_tests.OfflineFeedError):
                urllib.request.urlopen(url, timeout=1)
        request = urllib.request.Request('https://api.balldontlie.io/wnba/v1/teams')
        opener = urllib.request.build_opener(wnba_sync.NoRedirect())
        with self.assertRaises(offline_tests.OfflineFeedError):
            opener.open(request, timeout=1)
        with self.assertRaises(offline_tests.OfflineFeedError):
            game_stats.get_json('https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard')
