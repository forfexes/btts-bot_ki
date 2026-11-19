"""Quota safety for NETRATTLER L20 player history fetching."""
import unittest
from unittest.mock import Mock, patch

import netrattler_player_log as player


class PlayerLogQuotaTests(unittest.TestCase):
    def setUp(self):
        self.names=["TeamAlpha"+str(i)+" Football Club" for i in range(30)]

    def test_402_aborts_all_chunks_without_partial_l20(self):
        good=Mock(ok=True,status_code=200)
        good.json.return_value=[{
            "player_name":"Real Sample","team":"TeamAlpha0 Football Club",
            "match_date":"2026-11-17","event_id":1
        }]
        blocked=Mock(ok=False,status_code=402,text="quota exceeded")
        out=[]
        with patch.object(player,"PLAYERS_DB_URL","https://example.supabase.co"), \
             patch.object(player,"PLAYERS_DB_KEY","dummy"), \
             patch.object(player.requests,"get",side_effect=[good,blocked]) as get:
            result=player.fetch_l20_rows(self.names,log=out.append)
        self.assertEqual(result,[])
        self.assertEqual(get.call_count,2)
        self.assertTrue(any("quota" in msg.lower() for msg in out))
        self.assertFalse(any("Real Sample" in msg for msg in out))

    def test_one_402_never_retries_remaining_batches(self):
        blocked=Mock(ok=False,status_code=402,text="quota exceeded")
        with patch.object(player,"PLAYERS_DB_URL","https://example.supabase.co"), \
             patch.object(player,"PLAYERS_DB_KEY","dummy"), \
             patch.object(player.requests,"get",return_value=blocked) as get:
            self.assertEqual(player.fetch_l20_rows(self.names),[])
        get.assert_called_once()

    def test_successful_player_rows_remain_unchanged(self):
        good=Mock(ok=True,status_code=200)
        good.json.return_value=[{
            "player_name":"A","team":"Sevilla",
            "match_date":"2026-11-17","event_id":3
        }]
        with patch.object(player,"PLAYERS_DB_URL","https://example.supabase.co"), \
             patch.object(player,"PLAYERS_DB_KEY","dummy"), \
             patch.object(player.requests,"get",return_value=good) as get:
            result=player.fetch_l20_rows(["Sevilla"])
        self.assertEqual(result[0]["player_name"],"A")
        get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
