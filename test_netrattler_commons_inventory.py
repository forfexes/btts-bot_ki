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


if __name__=="__main__":
    unittest.main()
