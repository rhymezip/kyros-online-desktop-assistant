import asyncio
from pathlib import Path
import sys
import tempfile
import unittest
from core.executor import run_process, ToolExecutor, applescript_string
from core.web_page import PageParser, fetch


class ExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_exit_code_and_error(self):
        result = await run_process(
            [
                sys.executable,
                "-c",
                'import sys; print("problem",file=sys.stderr); sys.exit(7)',
            ]
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["exit_code"], 7)
        self.assertIn("problem", result["stderr"])

    async def test_output_is_bounded_but_process_drains(self):
        result = await run_process(
            [sys.executable, "-c", 'print("x"*200000)'], limit=100
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["stdout"]), 100)

    async def test_general_command_creates_unseen_file(self):
        with tempfile.TemporaryDirectory(prefix="kyros test ") as folder:
            result = await ToolExecutor().execute(
                "run_shell",
                {
                    "script": "printf '%s' 'menemen değil herhangi bir içerik' > result.txt",
                    "cwd": folder,
                },
            )
            self.assertTrue(result["ok"])
            self.assertEqual(
                (Path(folder) / "result.txt").read_text(),
                "menemen değil herhangi bir içerik",
            )

    async def test_cancellation_stops_delayed_side_effect(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "must-not-exist"
            code = 'import time,pathlib,sys; print("ready",flush=True); time.sleep(1); pathlib.Path(sys.argv[1]).touch()'
            task = asyncio.create_task(
                run_process([sys.executable, "-c", code, str(target)])
            )
            await asyncio.sleep(0.1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
            await asyncio.sleep(1.05)
            self.assertFalse(target.exists())

    async def test_timeout_kills_descendant(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "must-not-exist"
            child = "import time,pathlib,sys; time.sleep(.8); pathlib.Path(sys.argv[1]).touch()"
            parent = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",sys.argv[1],sys.argv[2]]); time.sleep(5)'
            result = await run_process(
                [sys.executable, "-c", parent, child, str(target)], timeout=0.15
            )
            self.assertEqual(result["error"], "timeout")
            await asyncio.sleep(0.85)
            self.assertFalse(target.exists())

    async def test_timeout_noisy_process_does_not_deadlock(self):
        result = await asyncio.wait_for(
            run_process(
                [sys.executable, "-c", 'import os\nwhile True: os.write(1,b"x"*10000)'],
                timeout=0.1,
            ),
            3,
        )
        self.assertEqual(result["error"], "timeout")

    async def test_unknown_tool_is_failure(self):
        self.assertFalse((await ToolExecutor().execute("missing", {}))["ok"])

    def test_applescript_string_quotes_untrusted_content(self):
        self.assertEqual(applescript_string('a"b\\c\nd'), '"a\\"b\\\\c\\nd"')

    def test_web_text_strips_scripts_and_keeps_links(self):
        parser = PageParser()
        parser.feed('<h1>Haber</h1><script>ignore()</script><a href="/news">Bugün</a>')
        self.assertEqual(parser.text, ["Haber", "Bugün"])
        self.assertEqual(parser.links, ["/news"])

    def test_web_rejects_non_http_protocol(self):
        with self.assertRaises(ValueError):
            fetch("file:///etc/passwd")
