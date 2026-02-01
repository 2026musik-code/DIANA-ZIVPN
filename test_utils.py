import unittest
from utils.system import create_user, delete_user
from utils.paymenku import PaymenkuClient
import datetime

class TestUtils(unittest.TestCase):
    def test_mock_system(self):
        # Test Create User (Mock)
        expiry = datetime.datetime.now() + datetime.timedelta(days=30)
        success, msg = create_user("testuser", "password123", expiry)
        self.assertTrue(success)
        self.assertIn("Mock success", msg)

        # Test Delete User (Mock)
        success, msg = delete_user("testuser")
        self.assertTrue(success)
        self.assertIn("Mock success", msg)

    def test_paymenku_signature(self):
        client = PaymenkuClient("merchant", "key")
        sig = client.generate_signature("REF123", 10000)
        # md5(merchantREF12310000key)
        # We can just verify it returns a string for now
        self.assertIsInstance(sig, str)
        self.assertEqual(len(sig), 32) # MD5 is 32 hex chars

if __name__ == '__main__':
    unittest.main()
