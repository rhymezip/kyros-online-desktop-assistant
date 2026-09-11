"""Cancellable general-purpose local execution. No intent matching."""

import asyncio
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
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
            "linux_desktop": self.linux_desktop,
            "launch_app": self.launch_app,
            "media_control": self.media_control,
            "clipboard": self.clipboard,
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
            if sys.platform == "linux":
                import shutil

                pkexec = shutil.which("pkexec")
                if not pkexec:
                    raise ValueError(
                        "Linux yönetici komutu için polkit pkexec bulunamadı; parola istemek yerine açık hata döndürüldü."
                    )
                shell = "/bin/sh"
                return await run_process(
                    [pkexec, shell, "-lc", script],
                    cwd=cwd,
                    timeout=self.timeout(args),
                    limit=config.MAX_TOOL_OUTPUT,
                )
            if sys.platform != "darwin":
                raise ValueError("Administrator dialog requires macOS or Linux polkit")
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

    @staticmethod
    def _argv(value):
        if not isinstance(value, list) or not value or not all(
            isinstance(item, str) and item for item in value
        ):
            raise ValueError("argv must be a non-empty string array")
        return value

    @staticmethod
    def _linux_desktop_entry(app):
        data_home = Path(
            os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
        ).expanduser()
        data_dirs = [data_home]
        for value in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":"):
            if value:
                data_dirs.append(Path(value).expanduser())
        # Flatpak exports are commonly outside XDG_DATA_DIRS on minimal
        # Wayland sessions, but still use the standard desktop-entry format.
        data_dirs.extend(
            [
                Path.home() / ".local/share/flatpak/exports/share",
                Path("/var/lib/flatpak/exports/share"),
            ]
        )
        wanted = str(app).strip().casefold()
        seen = set()
        for root in data_dirs:
            applications = root / "applications"
            if not applications.is_dir():
                continue
            try:
                entries = list(applications.rglob("*.desktop"))
            except OSError:
                continue
            for entry in entries:
                try:
                    resolved = entry.resolve()
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    section = False
                    names = []
                    hidden = False
                    for line in entry.read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines():
                        line = line.strip()
                        if line == "[Desktop Entry]":
                            section = True
                            continue
                        if section and line.startswith("["):
                            break
                        if not section or "=" not in line or line.startswith("#"):
                            continue
                        key, value = line.split("=", 1)
                        if key == "Name" or key.startswith("Name["):
                            names.append(value.strip())
                        elif key == "Hidden":
                            hidden = value.strip().casefold() == "true"
                    if not hidden and (
                        wanted == entry.stem.casefold()
                        or any(name.casefold() == wanted for name in names)
                    ):
                        relative = entry.relative_to(applications).with_suffix("")
                        return relative.as_posix(), str(entry)
                except (OSError, ValueError):
                    continue
        return None, None

    def _launch_argv(self, args):
        argv = args.get("argv")
        if argv is not None:
            return self._argv(argv)

        if sys.platform == "darwin":
            app = args.get("app") or args.get("application")
            target = args.get("uri") or args.get("path")
            if app:
                return ["/usr/bin/open", "-a", str(app)]
            if target:
                return ["/usr/bin/open", str(target)]
        elif sys.platform == "linux":
            desktop_id = args.get("desktop_id")
            app = args.get("app") or args.get("application")
            target = args.get("uri") or args.get("path")
            if desktop_id:
                command = shutil.which("gtk-launch")
                if not command:
                    raise ValueError("gtk-launch is not installed")
                return [command, str(desktop_id)]
            if app:
                app_value = str(app).strip()
                for candidate in (app_value, app_value.casefold()):
                    command = shutil.which(candidate)
                    if command:
                        return [command]
                desktop_id, desktop_file = self._linux_desktop_entry(app_value)
                command = shutil.which("gtk-launch")
                if command and desktop_id:
                    return [command, desktop_id]
                gio = shutil.which("gio")
                if gio and desktop_file:
                    return [gio, "launch", desktop_file]
                raise ValueError(
                    "The Linux application is neither an executable in PATH nor a desktop_id"
                )
            if target:
                command = shutil.which("xdg-open")
                if not command:
                    raise ValueError("xdg-open is not installed")
                return [command, str(target)]
        raise ValueError(
            "Provide argv, an application name, a desktop_id, a URI, or a path"
        )

    async def launch_app(self, args):
        """Start an arbitrary user-requested application without a shell."""
        argv = self._launch_argv(args)
        if args.get("wait"):
            result = await run_process(
                argv,
                cwd=(
                    str(Path(args["cwd"]).expanduser().resolve())
                    if args.get("cwd")
                    else None
                ),
                timeout=self.timeout(args),
                limit=config.MAX_TOOL_OUTPUT,
            )
            return {"operation": "wait", "argv": argv, **result}

        env = os.environ.copy()
        env.pop("GEMINI_API_KEY", None)
        env["KYROS_PYTHON"] = sys.executable
        cwd = (
            str(Path(args["cwd"]).expanduser().resolve())
            if args.get("cwd")
            else None
        )
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
        return {
            "ok": True,
            "argv": argv,
            "pid": process.pid,
            "detail": "Process started; inspect the desktop to verify the requested application state.",
        }

    @staticmethod
    def _player_name(args):
        player = args.get("player") or args.get("player_name")
        if player is not None and (not isinstance(player, str) or not player.strip()):
            raise ValueError("player must be a non-empty string when provided")
        return player.strip() if isinstance(player, str) else None

    async def media_control(self, args):
        """Control the user's selected media player through native OS APIs."""
        action = str(args.get("action", ""))
        actions = {
            "play": "play",
            "pause": "pause",
            "play_pause": "play-pause",
            "stop": "stop",
            "next": "next",
            "previous": "previous",
            "status": "status",
            "metadata": "metadata",
        }
        if action not in actions:
            raise ValueError(f"Unsupported media action: {action}")
        player = self._player_name(args)

        if sys.platform == "linux":
            command = shutil.which("playerctl")
            if not command:
                raise ValueError(
                    "playerctl is not installed; install the Kyros Linux system dependencies"
                )
            argv = [command]
            if player:
                argv.append(f"--player={player}")
            if action == "metadata":
                argv.extend(
                    [
                        "metadata",
                        "--format",
                        "{{status}}\t{{artist}}\t{{title}}\t{{album}}",
                    ]
                )
            else:
                argv.append(actions[action])
            result = await run_process(
                argv,
                timeout=self.timeout(args),
                limit=config.MAX_TOOL_OUTPUT,
            )
            return {"action": action, "player": player, "argv": argv, **result}

        if sys.platform == "darwin":
            if not player:
                raise ValueError(
                    "player is required on macOS; use the application name returned by inspection"
                )
            command = {
                "play": "play",
                "pause": "pause",
                "play_pause": "playpause",
                "stop": "stop",
                "next": "next track",
                "previous": "previous track",
            }
            if action in command:
                script = (
                    f"tell application {applescript_string(player)}\n"
                    f"    {command[action]}\n"
                    "end tell\n"
                )
            else:
                script = (
                    f"tell application {applescript_string(player)}\n"
                    "    set kyrosState to player state as text\n"
                    "    set kyrosTitle to name of current track\n"
                    "    set kyrosArtist to artist of current track\n"
                    "    set kyrosAlbum to album of current track\n"
                    "    return kyrosState & tab & kyrosArtist & tab & kyrosTitle & tab & kyrosAlbum\n"
                    "end tell\n"
                )
            result = await run_process(
                ["/usr/bin/osascript", "-"],
                stdin=script.encode(),
                timeout=self.timeout(args),
                limit=config.MAX_TOOL_OUTPUT,
            )
            return {"action": action, "player": player, **result}

        raise ValueError("Media control requires macOS or Linux")

    async def clipboard(self, args):
        action = str(args.get("action", ""))
        selection = str(args.get("selection", "clipboard"))
        if action not in ("read", "write"):
            raise ValueError("clipboard action must be read or write")
        if selection not in ("clipboard", "primary"):
            raise ValueError("clipboard selection must be clipboard or primary")
        if action == "write" and not isinstance(args.get("text"), str):
            raise ValueError("clipboard write requires text as a string")

        if sys.platform == "darwin":
            if selection != "clipboard":
                raise ValueError("macOS does not expose a primary selection through pbcopy")
            command = "/usr/bin/pbpaste" if action == "read" else "/usr/bin/pbcopy"
            stdin = None if action == "read" else str(args.get("text", "")).encode()
        elif sys.platform == "linux":
            primary = ["--primary"] if selection == "primary" else []
            if shutil.which("wl-paste") and shutil.which("wl-copy"):
                command = shutil.which("wl-paste") if action == "read" else shutil.which("wl-copy")
                argv = [command, *primary]
                stdin = None if action == "read" else str(args.get("text", "")).encode()
            elif shutil.which("xclip"):
                command = shutil.which("xclip")
                argv = [command, "-selection", selection, "-out" if action == "read" else "-in"]
                stdin = None if action == "read" else str(args.get("text", "")).encode()
            elif shutil.which("xsel"):
                command = shutil.which("xsel")
                argv = [command, "--output" if action == "read" else "--input"]
                if selection == "primary":
                    argv.append("--primary")
                stdin = None if action == "read" else str(args.get("text", "")).encode()
            else:
                raise ValueError("No clipboard backend found (wl-clipboard, xclip, or xsel)")
        else:
            raise ValueError("Clipboard control requires macOS or Linux")

        if sys.platform == "darwin":
            argv = [command]
        result = await run_process(
            argv,
            stdin=stdin,
            timeout=self.timeout(args),
            limit=config.MAX_TOOL_OUTPUT,
        )
        if action == "read":
            result["text"] = result.get("stdout", "")
        return {"action": action, "selection": selection, **result}

    async def computer(self, args):
        if sys.platform == "darwin":
            script = config.ROOT / "core/macos_ui.py"
        elif sys.platform == "linux":
            script = config.ROOT / "core/linux_ui.py"
        else:
            raise ValueError("Computer control requires macOS or Linux")
        return await self._desktop_process(args, script)

    async def linux_desktop(self, args):
        if sys.platform != "linux":
            raise ValueError("linux_desktop yalnızca Linux'ta kullanılabilir")
        return await self._desktop_process(args, config.ROOT / "core/linux_ui.py")

    async def _desktop_process(self, args, script):
        with tempfile.TemporaryDirectory(prefix="kyros-screen-") as folder:
            payload = dict(args)
            payload["image_path"] = str(Path(folder) / "screen.jpg")
            result = await run_process(
                [sys.executable, str(script)],
                stdin=json.dumps(payload).encode(),
                timeout=config.COMPUTER_TIMEOUT,
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
        if not result["ok"]:
            return result
        try:
            return json.loads(result["stdout"])
        except (json.JSONDecodeError, ValueError):
            return {"ok": False, "error": "Invalid response from web fetcher"}
