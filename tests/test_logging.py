import logging
import unittest

from main import ColorFormatter, banner


class LoggingTests(unittest.TestCase):
    def test_terminal_log_is_localized_aligned_and_multiline(self):
        record = logging.LogRecord(
            "kyros.audio", logging.WARNING, "", 0, "İlk satır\nİkinci satır", (), None
        )
        output = ColorFormatter(use_color=False).format(record)
        self.assertIn("UYARI   SES      İlk satır", output)
        self.assertTrue(output.endswith("İkinci satır"))
        self.assertNotIn("\033[", output)

    def test_plain_banner_has_no_ansi_or_emoji(self):
        output = banner(use_color=False)
        self.assertIn("KYROS 3.0", output)
        self.assertNotIn("\033[", output)


if __name__ == "__main__":
    unittest.main()
