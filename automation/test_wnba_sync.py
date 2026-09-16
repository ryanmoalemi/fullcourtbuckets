"""Offline contract tests; synthetic fixtures, not real player data."""
import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wnba_sync as s

P = {"id": 1, "first_name": "Example", "last_name": "Player", "team": {"id": 1, "full_name": "Example Team"}}
NOW = dt.datetime(2009, 7, 20, 12, tzinfo=dt.timezone.utc)
G = {"id": 10, "date": "2009-07-19", "season": 2009, "postseason": False,
     "status_state": "final", "home_team": {"id": 1}, "visitor_team": {"id": 2}, "home_score": 80, "away_score": 70}

def stat(year=2009, kind=2):
    return {"player": P, "team": {"id": 1}, "season": year, "season_type": kind,
            "games_played": 10, "pts": 12.3, "ast": 4, "reb": None, "fg_pct": 45}

class FakeClient:
    def __init__(self, fail=False): self.fail = fail
    def all(self, endpoint, params=None):
        if self.fail and endpoint == 'player_season_stats': raise s.SyncError('Synthetic outage')
        if endpoint == 'players': return [copy.deepcopy(P)]
        if endpoint == 'players/active': return [copy.deepcopy(P)]
        if endpoint == 'teams': return [{"id": 1, "full_name": "Example Team"}]
        if endpoint == 'games': return [copy.deepcopy(G)]
        if endpoint == 'player_stats': return [{"player": P, "team": {"id": 1}, "game": {"id": 10}, "min": "25", "pts": 12}]
        if endpoint == 'player_season_stats': return [stat(params['season'], params['season_type'])]
        raise AssertionError(endpoint)

class Tests(unittest.TestCase):
    def test_missing_key(self):
        with self.assertRaises(s.SyncError): s.Client('')
    def test_missing_is_not_zero(self): self.assertIsNone(s.number(None))
    def test_zero_is_preserved(self): self.assertEqual(s.number(0), 0)
    def test_nan_rejected(self):
        with self.assertRaises(s.SyncError): s.number(float('nan'))
    def test_percent_units(self): self.assertEqual(s.number(45, percentage=True), 45)
    def test_percent_range(self):
        with self.assertRaises(s.SyncError): s.number(101, percentage=True)
    def test_boolean_rejected(self):
        with self.assertRaises(s.SyncError): s.number(True)
    def test_final_only(self):
        self.assertTrue(s.is_final(G))
        self.assertFalse(s.is_final({'status_state':'unknown', 'status':'final'}))
        self.assertFalse(s.is_final({'status_state':'in_progress'}))
    def test_slug_stays_after_name_change(self):
        registry = {}
        self.assertEqual(s.stable_slug(1, 'Example Player', registry), 'example-player')
        self.assertEqual(s.stable_slug(1, 'New Name', registry), 'example-player')
    def test_same_names_not_merged(self):
        registry = {}
        self.assertNotEqual(s.stable_slug(1, 'Same Name', registry), s.stable_slug(2, 'Same Name', registry))
    def test_path_traversal_rejected(self):
        with self.assertRaises(s.SyncError): s.stable_slug(1, 'Name', {'1':'../../index'})
    def test_duplicate_rows_collapsed(self): self.assertEqual(len(s.season_rows([stat(), stat()], 2009)), 1)
    def test_conflicting_duplicate_rejected(self):
        other=stat(); other['pts']=99
        with self.assertRaises(s.SyncError): s.season_rows([stat(),other],2009)
    def test_team_stints_separate(self):
        other=stat(); other['team']={'id':2}
        self.assertEqual(len(s.season_rows([stat(),other],2009)),2)
    def test_wrong_season_rejected(self):
        with self.assertRaises(s.SyncError): s.season_rows([stat(2008)],2009)
    def test_preseason_rejected(self):
        with self.assertRaises(s.SyncError): s.season_rows([stat(kind=1)],2009)
    def test_weekly_after_seven_days(self):
        self.assertFalse(s.should_refresh('2009-07-18',dt.date(2009,7,20),False))
        self.assertTrue(s.should_refresh('2009-07-10',dt.date(2009,7,20),False))
    def test_daily_during_season(self):
        self.assertTrue(s.should_refresh('2009-07-19',dt.date(2009,7,20),True))
        self.assertFalse(s.should_refresh('2009-07-20',dt.date(2009,7,20),True))
    def test_midseason_pause(self):
        self.assertTrue(s.in_season([{'date':'2009-05-01'},{'date':'2009-10-01'}],dt.date(2009,9,1)))
    def test_missing_schedule_conservative(self): self.assertTrue(s.in_season([],dt.date(2009,1,1)))
    def test_offseason(self): self.assertFalse(s.in_season([G],dt.date(2009,12,1)))
    def test_shrink_guard(self):
        with self.assertRaises(s.SyncError): s.guard_shrink(list(range(20)),[1],'test')
    def test_pagination(self):
        client=s.Client('synthetic-key')
        with patch.object(client,'get',side_effect=[{'data':[{'id':1}],'meta':{'next_cursor':1}},{'data':[{'id':2}],'meta':{}}]):
            self.assertEqual(len(client.all('players')),2)
    def test_pagination_loop_rejected(self):
        client=s.Client('synthetic-key')
        with patch.object(client,'get',return_value={'data':[{'id':1}],'meta':{'next_cursor':1}}):
            with self.assertRaises(s.SyncError): client.all('players')
    def test_successful_full_import_and_id_mapping(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            self.assertTrue(s.run(root,FakeClient(),NOW))
            output=json.loads((root/'data/wnba/players/example-player.json').read_text())
            self.assertEqual(len(output['season_stats']),4)
            self.assertFalse(output['career_totals_complete'])
            self.assertIsNone(output['season_stats'][0]['reb'])
            self.assertEqual(len(output['recent_completed_games']),1)
            self.assertNotIn('synthetic-key',str(output))
    def test_outage_does_not_replace_successful_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); s.run(root,FakeClient(),NOW)
            before={str(p):p.read_bytes() for p in root.rglob('*.json')}
            with self.assertRaises(s.SyncError): s.run(root,FakeClient(fail=True),NOW,force=True)
            after={str(p):p.read_bytes() for p in root.rglob('*.json')}
            self.assertEqual(before,after)

if __name__=='__main__': unittest.main()
