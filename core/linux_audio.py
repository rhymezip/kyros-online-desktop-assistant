"""Linux audio backends.

The macOS backend is intentionally kept in :mod:`core.audio_io`.  Linux has
several audio stacks in the wild, so this module keeps the platform boundary
small and explicit:

* PipeWire's ``pw-record``/``pw-play`` are the preferred backend.  They are
  available on a normal PipeWire desktop without requiring a Python audio
  binding, and they preserve the exact PCM contract used by Gemini Live.
* PortAudio remains an opt-in fallback for machines where PipeWire's command
  line clients are not installed.

No speech or intent policy lives here.  This module only moves PCM and reports
real process/device failures to the caller.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import deque
import re
import shutil
import signal
import subprocess
import time

import config

log = logging.getLogger("kyros.audio")

INPUT_RATE = 16_000
OUTPUT_RATE = 24_000
CHANNELS = 1
SAMPLE_BYTES = 2
INPUT_CHUNK_BYTES = INPUT_RATE // 50 * SAMPLE_BYTES  # 20 ms, s16 mono

_HEADPHONE_MARKERS = (
    "headphones",
    "headphone",
    "headset",
    "earbuds",
    "airpods",
    "beats",
    "bluetooth",
    "bluez",
    "a2dp",
    "usb audio",
)


def _command(name: str) -> str | None:
    return shutil.which(name)


def _child_env() -> dict:
    env = os.environ.copy()
    env.pop("GEMINI_API_KEY", None)
    return env


def _device_name(info: dict) -> str:
    props = info.get("info", {}).get("props", {})
    return str(
        props.get("node.description")
        or props.get("node.nick")
        or props.get("node.name")
        or info.get("id", "Unknown")
    )


def _device_id(info: dict) -> str:
    props = info.get("info", {}).get("props", {})
    # PipeWire accepts a node serial or a node name as --target.  Serial is
    # more stable than the ephemeral numeric node id and is what modern
    # portal/PipeWire documentation recommends for stream targeting.
    return str(
        props.get("object.serial")
        or props.get("node.name")
        or info.get("id", "")
    )


def _default_node(kind: str) -> str:
    command = _command("pactl")
    if command:
        try:
            result = subprocess.run(
                [command, f"get-default-{kind}"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
                env=_child_env(),
            )
            value = result.stdout.strip()
            if value:
                return value
        except (OSError, subprocess.SubprocessError):
            pass

    # pactl is not guaranteed on a PipeWire-only installation. WirePlumber's
    # wpctl exposes the same default-node references without a PulseAudio shim.
    wpctl = _command("wpctl")
    if not wpctl:
        return ""
    reference = "@DEFAULT_AUDIO_SOURCE@" if kind == "source" else "@DEFAULT_AUDIO_SINK@"
    try:
        result = subprocess.run(
            [wpctl, "inspect", reference],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            env=_child_env(),
        )
        output = result.stdout or ""
        match = re.search(r'^\s*node\.name\s*=\s*"([^"]+)"', output, re.MULTILINE)
        if match:
            return match.group(1)
        match = re.search(r'^\s*object\.serial\s*=\s*"?([^"\s]+)', output, re.MULTILINE)
        if match:
            return match.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def list_audio_devices() -> dict:
    """Return PipeWire source/sink devices in the settings-friendly format.

    ``pw-dump`` is used first because it is native to PipeWire and exposes
    stable node properties.  A small ``pactl`` fallback keeps PulseAudio-only
    installations useful.  Discovery is deliberately best-effort: startup
    still reports the real audio process error if no device can be opened.
    """

    devices = {"input_devices": [], "output_devices": []}
    dump = _command("pw-dump")
    if dump:
        try:
            result = subprocess.run(
                [dump],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                env=_child_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
                entries = json.loads(result.stdout)
                default_source = _default_node("source")
                default_sink = _default_node("sink")
                for entry in entries if isinstance(entries, list) else []:
                    props = entry.get("info", {}).get("props", {})
                    media_class = str(props.get("media.class", ""))
                    is_source = media_class == "Audio/Source" or media_class.startswith("Audio/Source/")
                    is_sink = media_class == "Audio/Sink" or media_class.startswith("Audio/Sink/")
                    if not (is_source or is_sink):
                        continue
                    device_id = _device_id(entry)
                    node_name = str(props.get("node.name", ""))
                    default_value = (
                        default_source if is_source else default_sink
                    )
                    item = {
                        "id": device_id,
                        "name": _device_name(entry),
                        "node_name": node_name,
                        "is_default": default_value
                        in (node_name, str(props.get("object.serial", "")), device_id),
                    }
                    if not item["id"]:
                        continue
                    target = (
                        devices["input_devices"]
                        if is_source
                        else devices["output_devices"]
                    )
                    target.append(item)
                if devices["input_devices"] or devices["output_devices"]:
                    return devices
        except (OSError, ValueError, TypeError, subprocess.SubprocessError):
            log.debug("PipeWire aygıt listesi alınamadı.", exc_info=True)

    pactl = _command("pactl")
    if not pactl:
        return devices
    # Keep the fallback intentionally conservative.  Names are valid
    # --target values for pw-record/pw-play and are also accepted by pactl.
    for kind, key in (("sources", "input_devices"), ("sinks", "output_devices")):
        try:
            result = subprocess.run(
                [pactl, "-f", "json", "list", kind],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                env=_child_env(),
            )
            if result.returncode != 0:
                continue
            entries = json.loads(result.stdout)
            default = _default_node("source" if key == "input_devices" else "sink")
            for entry in entries if isinstance(entries, list) else []:
                name = str(entry.get("name", ""))
                description = str(
                    entry.get("description") or entry.get("properties", {}).get("device.description") or name
                )
                if name:
                    devices[key].append(
                        {"id": name, "name": description, "node_name": name, "is_default": name == default}
                    )
        except (OSError, ValueError, TypeError, subprocess.SubprocessError):
            log.debug("PulseAudio aygıt listesi alınamadı.", exc_info=True)
    return devices


async def _terminate(process: asyncio.subprocess.Process | None) -> None:
    if process is None or process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), 0.5)
    except asyncio.TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()


class PipeWireAudio:
    """Full-duplex raw PCM through PipeWire command-line clients.

    PipeWire's command-line clients do not expose a playback callback, so the
    playing signal is based on the amount of PCM sent plus its real-time
    duration.  ``clear`` also restarts the playback process, which removes
    data already buffered in the old process instead of merely emptying a
    Python queue.
    """

    def __init__(self, input_device_id=None, output_device_id=None):
        self.process = None  # kept as an alias for diagnostics/compatibility
        self.record_process = None
        self.play_process = None
        self.tasks = []
        self.monitor = None
        self.route_monitor = None
        self.commands = asyncio.Queue(maxsize=256)
        self.ready = asyncio.Event()
        self.error = ""
        self.diagnostics = deque(maxlen=16)
        self.on_route_change = None
        self.on_headphone = None
        self.headphone = False
        self._input_device_id = input_device_id
        self._output_device_id = output_device_id
        self._closing = False
        self._loop = None
        self._play_lock = None
        self._route_lock = None
        self._clear_task = None
        self._route_restarting = False
        self._last_stable_routes = None
        self._playing_until = 0.0
        self._playing = False
        self._dropped_output = 0

    def _record_argv(self):
        command = _command("pw-record")
        if not command:
            raise RuntimeError(
                "PipeWire ses aracı bulunamadı (pw-record). PipeWire/WirePlumber kurun veya --audio-backend portaudio kullanın."
            )
        argv = [
            command,
            "--raw",
            "--format",
            "s16",
            "--rate",
            str(INPUT_RATE),
            "--channels",
            str(CHANNELS),
            "--channel-map",
            "MONO",
            "--media-category",
            "Capture",
            "--media-role",
            "Communication",
            "--latency",
            "20ms",
        ]
        if self._input_device_id:
            argv.extend(["--target", str(self._input_device_id)])
        argv.append("-")
        return argv

    def _play_argv(self):
        command = _command("pw-play")
        if not command:
            raise RuntimeError(
                "PipeWire ses aracı bulunamadı (pw-play). PipeWire/WirePlumber kurun veya --audio-backend portaudio kullanın."
            )
        argv = [
            command,
            "--raw",
            "--format",
            "s16",
            "--rate",
            str(OUTPUT_RATE),
            "--channels",
            str(CHANNELS),
            "--channel-map",
            "MONO",
            "--media-category",
            "Playback",
            "--media-role",
            "Communication",
            "--latency",
            "20ms",
        ]
        if self._output_device_id:
            argv.extend(["--target", str(self._output_device_id)])
        argv.append("-")
        return argv

    async def _spawn_processes(self):
        env = _child_env()
        self.record_process = await asyncio.create_subprocess_exec(
            *self._record_argv(),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        try:
            self.play_process = await asyncio.create_subprocess_exec(
                *self._play_argv(),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                start_new_session=True,
            )
        except BaseException:
            await _terminate(self.record_process)
            self.record_process = None
            raise
        self.process = self.record_process

    async def start(self, on_pcm, on_playing):
        self.on_pcm, self.on_playing = on_pcm, on_playing
        self._loop = asyncio.get_running_loop()
        self._play_lock = asyncio.Lock()
        self._route_lock = asyncio.Lock()
        self._closing = False
        self._route_restarting = False
        self._last_stable_routes = None
        self.ready.clear()
        self.error = ""
        self._playing_until = 0.0
        self._set_playing(False)
        self._set_headphone(self._output_device_id)
        await self._spawn_processes()
        self.tasks = self._stream_tasks()
        self.monitor = asyncio.create_task(self._monitor())
        self.route_monitor = asyncio.create_task(self._monitor_routes())
        ready_task = asyncio.create_task(self.ready.wait())
        try:
            done, _ = await asyncio.wait(
                [ready_task, self.monitor],
                timeout=15,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if self.monitor in done:
                await self.monitor
            if not self.ready.is_set():
                raise RuntimeError(
                    "PipeWire mikrofonu 15 saniye içinde PCM üretmedi; izin/aygıtı kontrol edin."
                )
        except BaseException:
            await self.close()
            raise
        finally:
            ready_task.cancel()
            await asyncio.gather(ready_task, return_exceptions=True)

    def _stream_tasks(self):
        return [
            asyncio.create_task(self._read_microphone()),
            asyncio.create_task(self._stderr(self.record_process, "mikrofon")),
            asyncio.create_task(self._stderr(self.play_process, "hoparlör")),
            asyncio.create_task(self._writer()),
        ]

    def _set_headphone(self, device_name):
        value = any(
            marker in str(device_name or "").lower()
            for marker in _HEADPHONE_MARKERS
        )
        if value != self.headphone:
            self.headphone = value
            if self.on_headphone:
                self.on_headphone(value)

    async def _monitor_routes(self):
        """Restart default streams when WirePlumber changes their route."""

        if self._input_device_id and self._output_device_id:
            return
        try:
            while not self._closing:
                current = await asyncio.to_thread(
                    lambda: (
                        None if self._input_device_id else _default_node("source"),
                        None if self._output_device_id else _default_node("sink"),
                    )
                )
                watched_values = [value for value in current if value is not None]
                stable = bool(watched_values) and all(watched_values)
                if stable and self._last_stable_routes is None:
                    self._last_stable_routes = current
                elif stable and current != self._last_stable_routes:
                    self._last_stable_routes = current
                    # A service can report an empty route briefly while a USB
                    # or Bluetooth device is disappearing.  Wait for a real
                    # replacement instead of restarting into an empty target.
                    await self._restart_routes(current)
                self._set_headphone(self._output_device_id or current[1])
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            raise

    async def _restart_routes(self, routes):
        async with self._route_lock:
            if self._closing or self._route_restarting:
                return
            self._route_restarting = True
            if self.on_route_change:
                self.on_route_change(True)
            self._playing_until = 0.0
            while not self.commands.empty():
                try:
                    self.commands.get_nowait()
                except asyncio.QueueEmpty:
                    break
            self._set_playing(False)
            if self._clear_task:
                if not self._clear_task.done():
                    self._clear_task.cancel()
                    await asyncio.gather(self._clear_task, return_exceptions=True)
                else:
                    self._clear_task.result()
                self._clear_task = None
            old_tasks = self.tasks
            self.tasks = []
            for task in old_tasks:
                task.cancel()
            await asyncio.gather(*old_tasks, return_exceptions=True)
            await _terminate(self.record_process)
            await _terminate(self.play_process)
            self.record_process = None
            self.play_process = None
            self.ready.clear()
            self.error = ""
            try:
                await self._spawn_processes()
                self.tasks = self._stream_tasks()
                ready_task = asyncio.create_task(self.ready.wait())
                try:
                    await asyncio.wait_for(ready_task, 15)
                finally:
                    ready_task.cancel()
                    await asyncio.gather(ready_task, return_exceptions=True)
                self._set_headphone(self._output_device_id or routes[1])
            finally:
                self._route_restarting = False
                if self.on_route_change:
                    self.on_route_change(False)

    def _set_playing(self, value):
        value = bool(value)
        if value != self._playing:
            self._playing = value
            if getattr(self, "on_playing", None):
                self.on_playing(value)

    async def _read_microphone(self):
        pending = bytearray()
        while True:
            chunk = await self.record_process.stdout.read(4096)
            if not chunk:
                raise RuntimeError(self.error or "PipeWire mikrofon akışı kapandı.")
            pending.extend(chunk)
            while len(pending) >= INPUT_CHUNK_BYTES:
                if not self.ready.is_set():
                    self.ready.set()
                pcm = bytes(pending[:INPUT_CHUNK_BYTES])
                del pending[:INPUT_CHUNK_BYTES]
                self.on_pcm(pcm)

    async def _stderr(self, process, label):
        while process and process.stderr:
            line = await process.stderr.readline()
            if not line:
                return
            text = line.decode(errors="replace").strip()[-1600:]
            self.diagnostics.append(f"{label}: {text}")
            # pw-* writes normal stream diagnostics to stderr.  Keep them at
            # debug level, but remember error-looking output for a useful
            # failure message if the process exits.
            if any(word in text.lower() for word in ("error", "failed", "cannot", "no such")):
                self.error = text
                log.debug("PipeWire %s: %s", label, text)

    async def _monitor(self):
        while not self._closing:
            await asyncio.sleep(0.05)
            if self.route_monitor and self.route_monitor.done():
                self.route_monitor.result()
            if self._clear_task and self._clear_task.done():
                clear_task = self._clear_task
                self._clear_task = None
                clear_task.result()
            for task in self.tasks:
                if task.done():
                    task.result()
            self.tasks = [task for task in self.tasks if not task.done()]
            if self.record_process and self.record_process.returncode is not None:
                raise RuntimeError(self.error or "PipeWire mikrofon süreci durdu.")
            if (
                self.play_process
                and self.play_process.returncode is not None
                and not self._closing
            ):
                raise RuntimeError(self.error or "PipeWire hoparlör süreci durdu.")
            if self._playing and time.monotonic() >= self._playing_until and self.commands.empty():
                self._set_playing(False)

    async def _writer(self):
        while True:
            pcm = await self.commands.get()
            if pcm is None:
                return
            async with self._play_lock:
                process = self.play_process
                if not process or not process.stdin:
                    raise RuntimeError("PipeWire hoparlör akışı hazır değil.")
                process.stdin.write(pcm)
                await process.stdin.drain()
            now = time.monotonic()
            self._playing_until = max(now, self._playing_until) + len(pcm) / (OUTPUT_RATE * SAMPLE_BYTES)
            self._set_playing(True)

    async def _restart_playback(self):
        async with self._play_lock:
            old = self.play_process
            self.play_process = None
            await _terminate(old)
            if not self._closing:
                env = _child_env()
                self.play_process = await asyncio.create_subprocess_exec(
                    *self._play_argv(),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    start_new_session=True,
                )
                # Keep a diagnostic reader for the replacement process.  It
                # is removed by close; it is not part of the monitor's fatal
                # task set because an EOF is normal during clear().
                diagnostic_task = asyncio.create_task(
                    self._stderr(self.play_process, "hoparlör")
                )
                self.tasks.append(diagnostic_task)

    def feed(self, pcm):
        if self._closing:
            return
        if self.commands.full():
            try:
                self.commands.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self._dropped_output += 1
            if self._dropped_output % 32 == 1:
                log.warning("PipeWire playback kuyruğu yoğunlaştı; eski ses parçası atlandı.")
        self.commands.put_nowait(bytes(pcm))

    def clear(self):
        self._playing_until = 0.0
        while not self.commands.empty():
            try:
                self.commands.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._set_playing(False)
        if self._loop and not self._closing:
            if not self._clear_task or self._clear_task.done():
                self._clear_task = asyncio.create_task(self._restart_playback())

    async def close(self):
        self._closing = True
        if self._clear_task and not self._clear_task.done():
            self._clear_task.cancel()
            await asyncio.gather(self._clear_task, return_exceptions=True)
        if self.monitor:
            self.monitor.cancel()
        if self.route_monitor:
            self.route_monitor.cancel()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(
            self.monitor, self.route_monitor, *self.tasks, return_exceptions=True
        )
        self.monitor = None
        self.route_monitor = None
        self.tasks = []
        while not self.commands.empty():
            try:
                self.commands.get_nowait()
            except asyncio.QueueEmpty:
                break
        await _terminate(self.record_process)
        await _terminate(self.play_process)
        self.record_process = None
        self.play_process = None
        self.process = None
        self._set_playing(False)


class PortAudio:
    """Linux PortAudio fallback with optional explicit device names."""

    def __init__(self, input_device_id=None, output_device_id=None):
        self.input_device_id = input_device_id or None
        self.output_device_id = output_device_id or None
        self.lock = __import__("threading").Lock()
        self.buffer = bytearray()
        self.playing = False
        self.streams = []
        self.monitor = None
        self._closed = False

    @staticmethod
    def _resolve_device(sd, selected):
        if not selected:
            return None
        numeric = None
        try:
            numeric = int(selected)
        except (TypeError, ValueError):
            pass
        candidates = {str(selected)}
        try:
            portaudio_devices = list(sd.query_devices())
            if numeric is not None and 0 <= numeric < len(portaudio_devices):
                return numeric
            devices = list_audio_devices()
            for item in devices.get("input_devices", []) + devices.get("output_devices", []):
                if str(item.get("id", "")) == str(selected):
                    for key in ("node_name", "name"):
                        if item.get(key):
                            candidates.add(str(item[key]))
                    break
            for index, info in enumerate(portaudio_devices):
                name = str(info.get("name", ""))
                if any(candidate == name or candidate in name for candidate in candidates):
                    return index
        except Exception:
            log.debug("PortAudio aygıt adı çözümlenemedi.", exc_info=True)
        return numeric if numeric is not None else selected

    async def start(self, on_pcm, on_playing):
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "Linux PortAudio fallback için sounddevice kurulmalı; PipeWire backendini tercih edin."
            ) from exc

        loop = asyncio.get_running_loop()
        self.on_playing = on_playing
        self.failed = loop.create_future()

        def fail(message):
            if not self.failed.done():
                self.failed.set_exception(RuntimeError(message))

        def capture(data, _frames, _timing, status):
            if status and status.input_overflow:
                loop.call_soon_threadsafe(fail, "Mikrofon tamponu taştı; ses aygıtını kontrol edin.")
            loop.call_soon_threadsafe(on_pcm, bytes(data))

        def playback(out, _frames, _timing, status):
            with self.lock:
                size = min(len(out), len(self.buffer))
                out[:] = bytes(self.buffer[:size]) + bytes(len(out) - size)
                del self.buffer[:size]
                active = size > 0
                if active != self.playing:
                    self.playing = active
                    loop.call_soon_threadsafe(on_playing, active)

        try:
            input_device = self._resolve_device(sd, self.input_device_id)
            output_device = self._resolve_device(sd, self.output_device_id)
            self.streams = [
                sd.RawInputStream(
                    samplerate=INPUT_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=INPUT_CHUNK_BYTES // SAMPLE_BYTES,
                    callback=capture,
                    latency="low",
                    device=input_device,
                ),
                sd.RawOutputStream(
                    samplerate=OUTPUT_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=OUTPUT_RATE // 50,
                    callback=playback,
                    latency="low",
                    device=output_device,
                ),
            ]
            for stream in self.streams:
                stream.start()
        except BaseException:
            await self.close()
            raise
        self.monitor = asyncio.ensure_future(self.failed)

    def feed(self, pcm):
        with self.lock:
            max_bytes = OUTPUT_RATE * SAMPLE_BYTES * config.MAX_AUDIO_BUFFER_SECONDS
            if len(self.buffer) + len(pcm) > max_bytes:
                raise RuntimeError("Playback buffer overflow")
            self.buffer.extend(pcm)

    def clear(self):
        with self.lock:
            self.buffer.clear()
            self.playing = False
        self.on_playing(False)

    async def close(self):
        self._closed = True
        for stream in self.streams:
            try:
                stream.abort()
                stream.close()
            except Exception:
                log.debug("PortAudio akışı kapanırken hata.", exc_info=True)
        self.streams.clear()
        if self.monitor:
            self.monitor.cancel()
            await asyncio.gather(self.monitor, return_exceptions=True)
            self.monitor = None


def check_pipewire_audio(timeout=8, input_device_id=None) -> tuple[bool, str]:
    """Capture a small real microphone frame for ``--audio-check``."""

    record = _command("pw-record")
    if not record:
        return False, "pw-record bulunamadı. PipeWire/WirePlumber kurun."
    argv = [
        record,
        "--raw",
        "--format",
        "s16",
        "--rate",
        str(INPUT_RATE),
        "--channels",
        "1",
        "--channel-map",
        "MONO",
        "--media-category",
        "Capture",
        "--media-role",
        "Communication",
    ]
    if input_device_id:
        argv.extend(["--target", str(input_device_id)])
    argv.append("-")
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            env=_child_env(),
        )
    except OSError as exc:
        return False, str(exc)
    ok = False
    detail = ""
    try:
        import select

        data = bytearray()
        deadline = time.monotonic() + timeout
        while len(data) < INPUT_CHUNK_BYTES:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                detail = "Mikrofon çerçevesi zamanında gelmedi; PipeWire izin/aygıtını kontrol edin."
                break
            ready, _, _ = select.select([process.stdout], [], [], remaining)
            if not ready:
                detail = "Mikrofon çerçevesi zamanında gelmedi; PipeWire izin/aygıtını kontrol edin."
                break
            try:
                chunk = os.read(process.stdout.fileno(), INPUT_CHUNK_BYTES - len(data))
            except OSError as exc:
                detail = f"Mikrofon PCM okunamadı: {exc}"
                break
            if not chunk:
                detail = "Mikrofon PCM akışı erken kapandı."
                break
            data.extend(chunk)
        if len(data) >= INPUT_CHUNK_BYTES:
            ok = True
            detail = f"PipeWire mikrofonu hazır ({len(data)} byte PCM)."
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            _stdout, stderr = process.communicate(timeout=1)
            if not ok and stderr:
                detail = stderr.decode(errors="replace").strip() or detail
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _stdout, stderr = process.communicate()
            if not ok and stderr:
                detail = stderr.decode(errors="replace").strip() or detail
    return ok, detail or "PipeWire mikrofon kontrolü başarısız oldu."


def check_portaudio_audio(timeout=8, input_device_id=None) -> tuple[bool, str]:
    """Capture one real PortAudio input block for ``--audio-check``."""

    try:
        import sounddevice as sd
    except ImportError:
        return False, "PortAudio fallback için sounddevice kurulmalı."
    stream = None
    try:
        stream = sd.RawInputStream(
            samplerate=INPUT_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=INPUT_CHUNK_BYTES // SAMPLE_BYTES,
            latency="low",
            device=PortAudio._resolve_device(sd, input_device_id),
        )
        stream.start()
        data, overflowed = stream.read(INPUT_CHUNK_BYTES // SAMPLE_BYTES)
        if data is None or len(data) == 0:
            return False, "PortAudio mikrofonu boş PCM döndürdü."
        detail = f"PortAudio mikrofonu hazır ({len(bytes(data))} byte PCM)."
        if overflowed:
            detail += " Giriş tamponu taştı; ses aygıtı gecikmesini kontrol edin."
        return True, detail
    except Exception as exc:
        return False, f"PortAudio mikrofon kontrolü başarısız: {exc}"
    finally:
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()
