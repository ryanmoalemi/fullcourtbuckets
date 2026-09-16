"""Synthetic queue tests. A manifest entry alone is not publication evidence."""
import unittest
from portrait_queue import plan

P = [{'id':1,'slug':'sue-bird','name':'Sue Bird','active_in_provider_feed':False},
     {'id':2,'slug':'aja-wilson','name':"A'ja Wilson",'active_in_provider_feed':True},
     {'id':3,'slug':'another-player','name':'Another Player','active_in_provider_feed':True}]

class PortraitQueueTests(unittest.TestCase):
    def test_active_before_archive(self):
        self.assertEqual([p['id'] for p in plan({'players':P},{},{})['next_batch']], [2,3,1])
    def test_approved_not_regenerated_but_not_counted_published(self):
        r=plan({'players':P},{'portraits':[{'player_id':2,'approved':True}]},{})
        self.assertEqual(r['verified_published'],0)
        self.assertEqual(r['awaiting_live_verification'][0]['id'],2)
        self.assertNotIn(2,[p['id'] for p in r['next_batch']])
    def test_resume_before_next_batch(self):
        r=plan({'players':P},{},{'current_batch':{'player_ids':[3]}})
        self.assertEqual([p['id'] for p in r['next_batch']],[3])
    def test_verified_complete(self):
        r=plan({'players':P},{},{'published':[{'player_id':p['id'],'live_verified':True} for p in P]})
        self.assertTrue(r['complete'])
        self.assertEqual(r['next_batch'],[])
    def test_does_not_call_blocked_complete(self):
        r=plan({'players':P},{},{'blocked':[{'player_id':2,'retryable':False}]})
        self.assertFalse(r['complete']); self.assertEqual(r['remaining'],3)
        self.assertNotIn(2,[p['id'] for p in r['next_batch']])
    def test_too_large_batch_rejected(self):
        with self.assertRaises(ValueError):plan({'players':P},{},{},11)

if __name__=='__main__':unittest.main()
