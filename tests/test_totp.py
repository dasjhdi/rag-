"""TOTP / 恢复码 / secret 加密的单元测试（不依赖数据库）。"""

import base64
import unittest

from app.security import totp
from app.security.secret_box import decrypt_secret, encrypt_secret


class HotpTest(unittest.TestCase):
    def setUp(self):
        # RFC 6238 附录 B 的种子（ASCII "12345678901234567890"）
        self.secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")

    def test_rfc6238_vectors(self):
        # (时间戳, 8 位结果) 来自 RFC 6238 SHA1 向量
        vectors = [
            (59, "94287082"),
            (1111111109, "07081804"),
            (1111111111, "14050471"),
            (1234567890, "89005924"),
            (2000000000, "69279037"),
        ]
        for at, expected in vectors:
            counter = int(at // 30)
            self.assertEqual(totp.hotp(self.secret, counter, digits=8), expected)

    def test_verify_accepts_current_window(self):
        now = 1_700_000_000
        code = totp.hotp(self.secret, totp.time_counter(now))
        ok, counter = totp.verify_code(self.secret, code, at=now)
        self.assertTrue(ok)
        self.assertEqual(counter, totp.time_counter(now))

    def test_verify_rejects_wrong_code(self):
        ok, _ = totp.verify_code(self.secret, "000000", at=1_700_000_000)
        self.assertFalse(ok)

    def test_replay_is_rejected(self):
        now = 1_700_000_000
        code = totp.hotp(self.secret, totp.time_counter(now))
        first_ok, counter = totp.verify_code(self.secret, code, at=now)
        self.assertTrue(first_ok)
        second_ok, _ = totp.verify_code(
            self.secret, code, at=now, last_counter=counter
        )
        self.assertFalse(second_ok)

    def test_provisioning_uri_contains_params(self):
        uri = totp.provisioning_uri(self.secret, "admin", "CookHero")
        self.assertTrue(uri.startswith("otpauth://totp/"))
        self.assertIn(f"secret={self.secret}", uri)
        self.assertIn("issuer=CookHero", uri)


class RecoveryCodeTest(unittest.TestCase):
    def test_generate_and_consume_once(self):
        codes = totp.generate_recovery_codes(3)
        self.assertEqual(len(codes), 3)
        stored = totp.build_recovery_payload(codes)

        ok, updated = totp.consume_recovery_code(stored, codes[0])
        self.assertTrue(ok)
        self.assertEqual(totp.count_unused_recovery_codes(updated), 2)

        again, _ = totp.consume_recovery_code(updated, codes[0])
        self.assertFalse(again)

    def test_unknown_code_rejected(self):
        stored = totp.build_recovery_payload(totp.generate_recovery_codes(2))
        ok, _ = totp.consume_recovery_code(stored, "aaaaa-bbbbb")
        self.assertFalse(ok)


class SecretBoxTest(unittest.TestCase):
    def test_roundtrip(self):
        cipher = encrypt_secret("JBSWY3DPEHPK3PXP")
        self.assertTrue(cipher.startswith("v1:"))
        self.assertNotIn("JBSWY3DP", cipher)
        self.assertEqual(decrypt_secret(cipher), "JBSWY3DPEHPK3PXP")

    def test_plaintext_passthrough(self):
        self.assertEqual(decrypt_secret("LEGACY"), "LEGACY")

    def test_tampered_payload_returns_empty(self):
        cipher = encrypt_secret("SECRET")
        raw = bytearray(base64.b64decode(cipher[3:]))
        raw[-1] ^= 0xFF
        broken = "v1:" + base64.b64encode(bytes(raw)).decode()
        self.assertEqual(decrypt_secret(broken), "")


if __name__ == "__main__":
    unittest.main()
