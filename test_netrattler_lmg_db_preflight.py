"""Offline preflight: quota restrictions stop live scanning safely."""
import unittest
from unittest.mock import Mock, patch
import netrattler_lmg_db_preflight as gate


class DbPreflightTests(unittest.TestCase):
    def setUp(self):
        self.env={
            "SUPABASE_URL":"https://sugycqnjncgfheueqaee.supabase.co",
            "SUPABASE_KEY":"dummy",
            "SUPABASE_SERVICE_ROLE_KEY":""
        }

    def test_success(self):
        with patch.dict("os.environ",self.env):
            response=Mock(status_code=200)
            fn=Mock(return_value=response)
            self.assertEqual(gate.preflight(fn),"ready")
            self.assertEqual(fn.call_count,1)
            self.assertIn("limit",fn.call_args.kwargs["params"])

    def test_egress_402_stops_before_telegram(self):
        response=Mock(status_code=402)
        response.json.return_value={"message":"Project exceeded egress quota"}
        with patch.dict("os.environ",self.env):
            self.assertEqual(gate.preflight(Mock(return_value=response)),
                             "blocked_egress_quota")
            with patch.object(gate,"preflight",return_value="blocked_egress_quota"):
                with self.assertRaises(SystemExit):
                    gate.main()

    def test_other_quota_402(self):
        response=Mock(status_code=402)
        response.json.return_value={"message":"restricted"}
        with patch.dict("os.environ",self.env):
            self.assertEqual(gate.preflight(Mock(return_value=response)),
                             "blocked_api_quota")

    def test_wrong_project_never_called(self):
        with patch.dict("os.environ",{**self.env,
                                     "SUPABASE_URL":"https://other.supabase.co"}):
            self.assertEqual(gate.preflight(Mock(side_effect=AssertionError("network"))),
                             "wrong_supabase_project")

    def test_missing_secret_never_called(self):
        with patch.dict("os.environ",{
             "SUPABASE_URL":"https://sugycqnjncgfheueqaee.supabase.co",
             "SUPABASE_KEY":"","SUPABASE_SERVICE_ROLE_KEY":""}):
            self.assertEqual(gate.preflight(Mock(side_effect=AssertionError("network"))),
                             "missing_credentials")

    def test_auth_error(self):
        with patch.dict("os.environ",self.env):
            self.assertEqual(gate.preflight(Mock(return_value=Mock(status_code=403))),
                             "credentials_rejected")


if __name__=="__main__":
    unittest.main()
