import unittest
from unittest.mock import patch

from media_multipart import retry_delay


class RetryDelayTest(unittest.TestCase):
    def test_uses_retry_after_seconds(self) -> None:
        self.assertEqual(retry_delay("7", 0), 7.0)

    @patch("media_multipart.time.time", return_value=1_700_000_000)
    def test_uses_retry_after_date(self, _mock_time) -> None:
        self.assertEqual(
            retry_delay("Tue, 14 Nov 2023 22:13:25 GMT", 0),
            5.0,
        )

    def test_exponential_fallback_is_capped(self) -> None:
        self.assertEqual(retry_delay(None, 2), 4)
        self.assertEqual(retry_delay(None, 9), 16)


if __name__ == "__main__":
    unittest.main()
