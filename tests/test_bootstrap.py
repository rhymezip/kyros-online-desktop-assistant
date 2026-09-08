import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from core.bootstrap import use_project_environment


class BootstrapTests(unittest.TestCase):
    def test_system_python_relaunches_in_project_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            python = Path(folder) / "venv/bin/python"
            python.parent.mkdir(parents=True)
            python.touch()
            python.chmod(0o700)
            with (
                patch("sys.platform", "darwin"),
                patch("sys.prefix", "/system-python"),
                patch.dict(os.environ, {}, clear=True),
                patch("os.execv") as execute,
            ):
                use_project_environment(folder)
                self.assertEqual(execute.call_args.args[0], str(python))
                self.assertEqual(execute.call_args.args[1][0], str(python))
                self.assertEqual(
                    os.environ["KYROS_PROJECT_ENV"], str(Path(folder) / "venv")
                )

    def test_already_active_environment_is_not_relaunched(self):
        with tempfile.TemporaryDirectory() as folder:
            with (
                patch("sys.platform", "darwin"),
                patch("sys.prefix", str(Path(folder) / "venv")),
                patch("os.execv") as execute,
            ):
                use_project_environment(folder)
                execute.assert_not_called()

    def test_missing_environment_does_not_attempt_exec(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("sys.platform", "darwin"), patch("os.execv") as execute:
                use_project_environment(folder)
                execute.assert_not_called()
