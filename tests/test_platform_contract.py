import importlib.util
import sys
import unittest
from unittest.mock import patch

from core import protocol


class MacPlatformContractTests(unittest.TestCase):
    def test_darwin_surface_keeps_mac_tools_and_prompt(self):
        spec = importlib.util.spec_from_file_location(
            "protocol_darwin_contract", protocol.__file__
        )
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, "platform", "darwin"):
            spec.loader.exec_module(module)

        names = {item["name"] for item in module.FUNCTIONS}
        self.assertIn("run_applescript", names)
        self.assertIn("launch_app", names)
        self.assertIn("media_control", names)
        self.assertIn("clipboard", names)
        self.assertNotIn("linux_desktop", names)
        shell = next(item for item in module.FUNCTIONS if item["name"] == "run_shell")
        self.assertIn("elevated", shell["parameters"]["properties"])
        self.assertIn("MAC ERİŞİMİ:", module.SYSTEM_INSTRUCTION)
        self.assertNotIn("LINUX / WAYLAND KURALI:", module.SYSTEM_INSTRUCTION)


if __name__ == "__main__":
    unittest.main()
