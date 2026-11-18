"""Offline tests: Commons inventory records attribution but never grants publication rights."""
import unittest
import netrattler_commons_inventory as inv


class CommonsInventoryTests(unittest.TestCase):
    def test_metadata_fields(self):
        page={"title":"File:Lionel Messi match 2024.jpg","imageinfo":[{
            "thumburl":"https://upload.wikimedia.org/wikipedia/commons/thumb/a/b/messi.jpg/450px-messi.jpg",
            "extmetadata":{
                "LicenseShortName":{"value":"CC BY-SA 4.0"},
                "Artist":{"value":"<a href='https://example.com'>Steindy</a>"},
                "LicenseUrl":{"value":"https://creativecommons.org/licenses/by-sa/4.0/"}
            }}]}
        row=inv.candidate_row("Lionel Messi","Inter Miami",page)
        self.assertEqual(row["Fotograf"],"Steindy")
        self.assertEqual(row["Lizenz"],"CC BY-SA 4.0")
        self.assertIn("File:Lionel_Messi",row["Commons_Seite"])
        self.assertEqual(row["Pruefstatus"],"manuell_pruefen")

    def test_reject_wrong_person(self):
        page={"title":"File:Cristiano Ronaldo training.jpg","imageinfo":[{
            "url":"https://upload.wikimedia.org/wikipedia/commons/test.jpg"}]}
        self.assertIsNone(inv.candidate_row("Lionel Messi","Inter Miami",page))

    def test_missing_metadata_flag(self):
        page={"title":"File:Lionel Messi.jpg","imageinfo":[{
            "url":"https://upload.wikimedia.org/wikipedia/commons/test.jpg"}]}
        row=inv.candidate_row("Lionel Messi","Inter Miami",page)
        self.assertEqual(row["Pruefstatus"],"metadaten_unvollstaendig")


    def test_pagination_fetches_followup_without_duplicate_files(self):
        from unittest.mock import Mock
        item={"title":"File:Lionel Messi match 2024.jpg","imageinfo":[{
            "thumburl":"https://upload.wikimedia.org/wikipedia/commons/thumb/a/b/messi.jpg/450px-messi.jpg",
            "extmetadata":{"LicenseShortName":{"value":"CC BY 4.0"},
                           "Artist":{"value":"Example Photographer"}}}]}
        responses=[{"query":{"pages":[item]},"continue":{"continue":"-||","gsroffset":50}},
                   {"query":{"pages":[item]}}]
        session=Mock()
        session.get.side_effect=[Mock(**{"json.return_value":p,"raise_for_status.return_value":None}) for p in responses]
        rows=inv.search_commons(session,"Lionel Messi","Inter Miami",max_pages=3)
        self.assertEqual(len(rows),1)
        self.assertEqual(session.get.call_count,2)
        self.assertEqual(session.get.call_args.kwargs["params"]["gsroffset"],50)
        self.assertEqual(rows[0]["Pruefstatus"],"manuell_pruefen")

    def test_batch_offsets_and_resume_without_duplicate_player_rows(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"roster.csv"
            output=Path(d)/"result.csv"
            source.write_text("Player,Squad,Pos\nA Name,A Club,FW\nB Name,B Club,DF\nC Name,C Club,MF\n",encoding="utf-8")
            with patch.object(inv,"search_commons",return_value=[]) as search:
                self.assertEqual(inv.build(source,output,limit=2,start=1,pause=0),0)
                self.assertEqual(search.call_count,2)
                self.assertEqual(inv.build(source,output,limit=2,start=1,pause=0,resume=True),0)
                self.assertEqual(search.call_count,2)
            import csv
            with output.open(encoding="utf-8-sig",newline="") as handle:
                rows=list(csv.DictReader(handle))
            self.assertEqual([x["Spieler"] for x in rows],["B Name","C Name"])
            self.assertEqual(rows[0]["Position"],"DF")

if __name__=="__main__":
    unittest.main()
