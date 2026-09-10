import unittest

from core.panel_geometry import top_attached_panel_positions


class PanelGeometryTests(unittest.TestCase):
    def test_panel_is_centered_and_attached_to_screen_top(self):
        hidden, visible = top_attached_panel_positions(0, 0, 1512, 300, 100)

        self.assertEqual(visible, ((1512 - 300) // 2, 0))
        self.assertEqual(hidden, ((1512 - 300) // 2, -100))

    def test_panel_positions_include_secondary_screen_origin(self):
        hidden, visible = top_attached_panel_positions(
            -1920, 120, 1920, 300, 100
        )

        self.assertEqual(visible, (-1920 + (1920 - 300) // 2, 120))
        self.assertEqual(hidden, (-1920 + (1920 - 300) // 2, 20))
