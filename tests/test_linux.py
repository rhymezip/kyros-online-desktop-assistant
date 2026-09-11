import asyncio
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

from core import linux_audio, linux_ui, protocol
from core.executor import ToolExecutor


@unittest.skipUnless(sys.platform == "linux", "Linux capability tests")
class LinuxDesktopTests(unittest.TestCase):
    def test_normal_window_accepts_hyprland_geometry_and_malformed_fallbacks(self):
        result = linux_ui._normal_window(
            {
                "address": "0x123",
                "pid": 42,
                "class": "Editor",
                "title": "Belge",
                "at": (10, 20),
                "size": (800, 600),
                "workspace": {"id": 3, "name": "three"},
            }
        )
        self.assertEqual(result["x"], 10)
        self.assertEqual(result["y"], 20)
        self.assertEqual(result["width"], 800)
        self.assertEqual(result["height"], 600)
        self.assertEqual(result["workspace"], "three")

        fallback = linux_ui._normal_window({"x": 7, "y": 8, "w": 9, "h": 10})
        self.assertEqual(
            (fallback["x"], fallback["y"], fallback["width"], fallback["height"]),
            (7, 8, 9, 10),
        )

    def test_target_selector_requires_a_real_safe_address(self):
        self.assertEqual(
            linux_ui._target_selector({"address": "0xABC"}), "address:0xABC"
        )
        self.assertEqual(linux_ui._target_selector({"pid": 42}), "pid:42")
        self.assertEqual(
            linux_ui._target_selector({"class": "org.example.Editor"}),
            "class:org.example.Editor",
        )
        with self.assertRaises(linux_ui.LinuxDesktopError):
            linux_ui._target_selector({"address": "not a window"})

    def test_modifier_mapping_rejects_unknown_input(self):
        self.assertEqual(
            linux_ui._input_modifiers(["control", "shift"]),
            [("ctrl", "CTRL"), ("shift", "SHIFT")],
        )
        with self.assertRaises(linux_ui.LinuxDesktopError):
            linux_ui._input_modifiers(["command-ish"])

    def test_xdotool_is_not_claimed_for_native_wayland_without_opt_in(self):
        with patch.dict(
            os.environ,
            {"DISPLAY": ":1", "WAYLAND_DISPLAY": "wayland-1"},
            clear=False,
        ):
            self.assertFalse(linux_ui._x11_control_allowed())

    def test_ydotool_uses_the_per_user_runtime_socket(self):
        with patch.dict(
            os.environ,
            {"XDG_RUNTIME_DIR": "/run/user/1000"},
            clear=True,
        ):
            self.assertEqual(
                linux_ui._ydotool_socket(), "/run/user/1000/.ydotool_socket"
            )

    def test_launch_uses_argv_and_never_a_shell(self):
        process = Mock(pid=1234)
        with patch.object(
            linux_ui,
            "_which",
            side_effect=lambda name: "/usr/bin/xdg-open" if name == "xdg-open" else None,
        ), patch.object(linux_ui.subprocess, "Popen", return_value=process) as popen:
            result = linux_ui._launch({"path_name": "/tmp/a file.txt"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["argv"], ["/usr/bin/xdg-open", "/tmp/a file.txt"])
        self.assertEqual(popen.call_args.kwargs["start_new_session"], True)

    def test_capabilities_is_explicit_about_available_backends(self):
        with patch.object(linux_ui, "_which", return_value=None), patch.object(
            linux_ui, "_load_atspi", side_effect=linux_ui.LinuxDesktopError("missing")
        ), patch.object(
            linux_ui, "_load_gio", side_effect=linux_ui.LinuxDesktopError("missing")
        ):
            result = linux_ui.capabilities()
        self.assertFalse(result["audio"]["pipewire"])
        self.assertFalse(result["screen"]["grim"])
        self.assertFalse(result["accessibility"]["atspi2"])
        self.assertIn("pointer_wayland", result["requirements"])


@unittest.skipUnless(sys.platform == "linux", "Linux capability tests")
class LinuxAudioTests(unittest.TestCase):
    def test_pipewire_commands_preserve_gemini_pcm_contract(self):
        audio = linux_audio.PipeWireAudio("101", "alsa_output.example")
        with patch.object(
            linux_audio,
            "_command",
            side_effect=lambda name: f"/usr/bin/{name}",
        ):
            record = audio._record_argv()
            play = audio._play_argv()
        self.assertEqual(record[-3:-1], ["--target", "101"])
        self.assertEqual(play[-3:-1], ["--target", "alsa_output.example"])
        self.assertIn("--rate", record)
        self.assertEqual(record[record.index("--rate") + 1], "16000")
        self.assertEqual(play[play.index("--rate") + 1], "24000")
        self.assertEqual(play.count("--media-role"), 1)

    def test_pipewire_dump_device_discovery_keeps_stable_target(self):
        payload = [
            {
                "id": 44,
                "info": {
                    "props": {
                        "media.class": "Audio/Source",
                        "object.serial": "101",
                        "node.name": "alsa_input.example",
                        "node.description": "Mikrofon",
                    }
                },
            },
            {
                "id": 55,
                "info": {
                    "props": {
                        "media.class": "Audio/Sink",
                        "object.serial": "202",
                        "node.name": "alsa_output.example",
                        "node.description": "Hoparlör",
                    }
                },
            },
        ]
        completed = Mock(returncode=0, stdout=json.dumps(payload))
        with patch.object(
            linux_audio,
            "_command",
            side_effect=lambda name: "/usr/bin/pw-dump" if name == "pw-dump" else None,
        ), patch.object(
            linux_audio, "_default_node", side_effect=["alsa_input.example", "alsa_output.example"]
        ), patch.object(linux_audio.subprocess, "run", return_value=completed):
            devices = linux_audio.list_audio_devices()
        self.assertEqual(devices["input_devices"][0]["id"], "101")
        self.assertTrue(devices["input_devices"][0]["is_default"])
        self.assertEqual(devices["output_devices"][0]["id"], "202")
        self.assertTrue(devices["output_devices"][0]["is_default"])

    def test_default_node_uses_wpctl_when_pactl_is_absent(self):
        completed = Mock(returncode=0, stdout='node.name = "alsa_output.example"\n')
        with patch.object(
            linux_audio,
            "_command",
            side_effect=lambda name: "/usr/bin/wpctl" if name == "wpctl" else None,
        ), patch.object(linux_audio.subprocess, "run", return_value=completed) as run:
            self.assertEqual(linux_audio._default_node("sink"), "alsa_output.example")
        self.assertEqual(
            run.call_args.args[0],
            ["/usr/bin/wpctl", "inspect", "@DEFAULT_AUDIO_SINK@"],
        )


@unittest.skipUnless(sys.platform == "linux", "Linux capability tests")
class LinuxIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_computer_and_linux_desktop_dispatch_to_linux_helper(self):
        async def fake_run(argv, **_kwargs):
            self.assertEqual(Path(argv[1]).name, "linux_ui.py")
            return {
                "ok": True,
                "stdout": '{"ok": true, "action": "capabilities"}',
                "stderr": "",
                "truncated": False,
            }

        executor = ToolExecutor()
        with patch("core.executor.run_process", new=AsyncMock(side_effect=fake_run)):
            first = await executor.execute("computer", {"action": "capabilities"})
            second = await executor.execute("linux_desktop", {"action": "capabilities"})
        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(first["action"], "capabilities")
        self.assertEqual(second["action"], "capabilities")

    async def test_linux_tool_is_cancellable_through_existing_executor_boundary(self):
        task = asyncio.create_task(
            ToolExecutor().execute("linux_desktop", {"action": "screenshot"})
        )
        task.cancel()
        # Cancellation is intentionally propagated by run_process; the Live
        # session turns it into its existing truthful cancelled response.
        with self.assertRaises(asyncio.CancelledError):
            await task


@unittest.skipUnless(sys.platform == "linux", "Linux capability tests")
class LinuxProtocolTests(unittest.TestCase):
    def test_linux_tool_surface_has_no_mac_only_apple_script(self):
        names = {item["name"] for item in protocol.FUNCTIONS}
        self.assertIn("linux_desktop", names)
        self.assertIn("launch_app", names)
        self.assertIn("media_control", names)
        self.assertIn("clipboard", names)
        self.assertNotIn("run_applescript", names)
        shell = next(item for item in protocol.FUNCTIONS if item["name"] == "run_shell")
        self.assertIn("elevated", shell["parameters"]["properties"])
        linux_tool = next(item for item in protocol.FUNCTIONS if item["name"] == "linux_desktop")
        self.assertIn("capabilities", linux_tool["parameters"]["properties"]["action"]["enum"])
