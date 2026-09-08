"""Cancellable general-purpose local execution. No intent matching."""

import asyncio
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import config


def applescript_string(value):
    return (
        '"'
        + value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        + '"'
    )


async def terminate_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), 0.4)
    except asyncio.TimeoutError:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    async def drain(stream):
        while await stream.read(8192):
            pass

    await asyncio.gather(drain(process.stdout), drain(process.stderr))
    await process.wait()


async def run_process(argv, *, stdin=None, cwd=None, timeout=60, limit=24000):
    env = os.environ.copy()
    env.pop("GEMINI_API_KEY", None)
    env["KYROS_PYTHON"] = sys.executable
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
        start_new_session=True,
    )

    async def read_limited(stream):
        result = bytearray()
        total = 0
        while chunk := await stream.read(8192):
            total += len(chunk)
            result.extend(chunk[: max(0, limit - len(result))])
        return result.decode("utf-8", errors="replace"), total > limit

    async def feed_input():
        try:
            if stdin:
                process.stdin.write(stdin)
                await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            process.stdin.close()

    async def collect():
        _, out, err, code = await asyncio.gather(
            feed_input(),
            read_limited(process.stdout),
            read_limited(process.stderr),
            process.wait(),
        )
        return {
            "ok": code == 0,
            "exit_code": code,
            "stdout": out[0],
            "stderr": err[0],
            "truncated": out[1] or err[1],
        }

    try:
        return await asyncio.wait_for(collect(), timeout)
    except asyncio.TimeoutError:
        await terminate_group(process)
        return {
            "ok": False,
            "error": "timeout",
            "detail": "Process group stopped; completed side effects may remain.",
        }
    except asyncio.CancelledError:
        await terminate_group(process)
        raise


class ToolExecutor:
    async def execute(self, name, args):
        handler = {
            "run_shell": self.shell,
            "run_applescript": self.applescript,
            "computer": self.computer,
            "read_web": self.web,
        }.get(name)
        if handler is None:
            return {"ok": False, "error": "Unknown tool"}
        if not isinstance(args, dict):
            return {"ok": False, "error": "Tool arguments must be an object"}
        try:
            return await handler(args)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            return {"ok": False, "error": str(exc)}

    def timeout(self, args):
        return max(
            1,
            min(int(args.get("timeout", config.TOOL_TIMEOUT)), config.MAX_TOOL_TIMEOUT),
        )

    async def shell(self, args):
        script = args["script"]
        if not isinstance(script, str) or not script.strip():
            raise ValueError("script must be a nonempty string")
        cwd = str(Path(args.get("cwd", str(Path.home()))).expanduser().resolve())
        if args.get("elevated", False):
            if sys.platform != "darwin":
                raise ValueError("Administrator dialog requires macOS")
            import shlex

            command = (
                "cd " + shlex.quote(cwd) + " && /bin/zsh -lc " + shlex.quote(script)
            )
            source = (
                "do shell script "
                + applescript_string(command)
                + " with administrator privileges"
            )
            return await run_process(
                ["/usr/bin/osascript", "-"],
                stdin=source.encode(),
                timeout=self.timeout(args),
                limit=config.MAX_TOOL_OUTPUT,
            )
        shell = "/bin/zsh" if sys.platform == "darwin" else "/bin/sh"
        return await run_process(
            [shell, "-lc", script],
            cwd=cwd,
            timeout=self.timeout(args),
            limit=config.MAX_TOOL_OUTPUT,
        )

    async def applescript(self, args):
        language = args.get("language", "AppleScript")
        if language not in ("AppleScript", "JavaScript"):
            raise ValueError("Unsupported scripting language")
        return await run_process(
            ["/usr/bin/osascript", "-l", language, "-"],
            stdin=args["script"].encode(),
            timeout=self.timeout(args),
            limit=config.MAX_TOOL_OUTPUT,
        )

    async def computer(self, args):
        if sys.platform != "darwin":
            raise ValueError("Computer control requires macOS")
        with tempfile.TemporaryDirectory(prefix="kyros-screen-") as folder:
            payload = dict(args)
            payload["image_path"] = str(Path(folder) / "screen.jpg")
            result = await run_process(
                [sys.executable, str(config.ROOT / "core/macos_ui.py")],
                stdin=json.dumps(payload).encode(),
                timeout=30,
                limit=256000,
            )
            if not result["ok"]:
                return result
            if result["truncated"]:
                return {
                    "ok": False,
                    "error": "UI result too large; inspect a specific subtree.",
                }
            result = json.loads(result["stdout"])
            picture = Path(payload["image_path"])
            if result.get("ok") and picture.exists():
                import base64

                result["_image"] = base64.b64encode(picture.read_bytes()).decode()
            return result

    async def web(self, args):
        result = await run_process(
            [sys.executable, str(config.ROOT / "core/web_page.py")],
            stdin=json.dumps(args).encode(),
            timeout=25,
            limit=256000,
        )
        if result.get("truncated"):
            return {
                "ok": False,
                "error": "Page result too large; use system tools to read a smaller portion.",
            }
        return json.loads(result["stdout"]) if result["ok"] else result
