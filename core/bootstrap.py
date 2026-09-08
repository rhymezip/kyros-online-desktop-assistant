"""Use the installed project environment when launched with a system Python."""

import os
from pathlib import Path
import sys


def use_project_environment(root):
    environment = Path(root) / "venv"
    python = environment / "bin/python"
    marker = "KYROS_PROJECT_ENV"
    if (
        sys.platform == "darwin"
        and Path(sys.prefix).resolve() != environment.resolve()
        and os.environ.get(marker) != str(environment)
        and python.is_file()
        and os.access(python, os.X_OK)
    ):
        os.environ[marker] = str(environment)
        os.execv(str(python), [str(python), *sys.argv])
