"""Streaming audio backends. Native macOS provides acoustic echo cancellation."""

import asyncio
from collections import deque
import json
import logging
import struct
import sys
import threading
import time
import config


_HEADPHONE_MARKERS = (
    "headphones", "airpods", "beats", "earbuds", "headset",
    "usb audio", "bluetooth",
)


def _is_headphone_name(name):
    lower = name.lower()
    return any(m in lower for m in _HEADPHONE_MARKERS)


def list_audio_devices():
    """List available audio devices by calling native/kyros-audio --list-devices."""
    binary = config.ROOT / "native/kyros-audio"
    if not binary.exists():
        return {"input_devices": [], "output_devices": []}
    try:
        import subprocess
        result = subprocess.run(
            [str(binary), "--list-devices"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout:
            return json.loads(result.stdout.decode("utf-8", errors="replace"))
    except Exception:
        pass
    return {"input_devices": [], "output_devices": []}


class NativeAudio:
    def __init__(self, input_device_id=None, output_device_id=None):
        self.process = None
        self.tasks = []
        self.monitor = None
        self.generation = 0
        self.commands = asyncio.Queue(maxsize=256)
        self.ready = asyncio.Event()
        self.error = ""
        self.diagnostics = deque(maxlen=12)
        self.on_route_change = None
        self.on_headphone = None
        self.headphone = False
        self._recovering = False
        self._closing = False
        self._restarts = deque()
        self._initialization_failures = 0
        self._input_device_id = input_device_id
        self._output_device_id = output_device_id

    async def start(self, on_pcm, on_playing):
        self.on_pcm, self.on_playing = on_pcm, on_playing
        binary = config.ROOT / "native/kyros-audio"
        if not binary.exists():
            raise RuntimeError(
                "Yerel ses motoru yok. Mac üzerinde bash install.sh çalıştırın."
            )
        await self._spawn()
        self.monitor = asyncio.create_task(self._monitor())
        ready_task = asyncio.create_task(self.ready.wait())
        try:
            done, _ = await asyncio.wait(
                [ready_task, self.monitor],
                timeout=60,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if self.monitor in done:
                await self.monitor
            if not self.ready.is_set():
                raise RuntimeError(
                    "Mikrofon başlatılamadı; macOS mikrofon iznini kontrol edin."
                )
        except BaseException:
            await self.close()
            raise
        finally:
            ready_task.cancel()
            await asyncio.gather(ready_task, return_exceptions=True)

    async def _spawn(self):
        self.ready.clear()
        self.error = ""
        self._recovering = True
        self.clear()
        # On Intel Macs voice processing (3ch) currently produces no audio — skip VP to avoid 1.5s fallback delay.
        # Apple Silicon can keep VP for AEC. Allow override via KYROS_NO_VP env.
        import platform as _plat
        import os as _os

        args = [str(config.ROOT / "native/kyros-audio")]
        if _os.environ.get("KYROS_NO_VP") == "1" or _plat.machine() == "x86_64":
            args.append("--no-vp")
        elif _os.environ.get("KYROS_VP") == "1":
            args.append("--voice-processing")
        if self._input_device_id is not None:
            args.extend(["--input-device", str(self._input_device_id)])
        if self._output_device_id is not None:
            args.extend(["--output-device", str(self._output_device_id)])
        self.process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.tasks = [
            asyncio.create_task(self._read()),
            asyncio.create_task(self._write()),
            asyncio.create_task(self._stderr()),
        ]

    async def _monitor(self):
        while not self._closing:
            try:
                await self._watch_process()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                try:
                    code = await asyncio.wait_for(self.process.wait(), 0.5)
                except asyncio.TimeoutError:
                    raise error
                # Explicit native signals, not error-text or device-name matching.
                # 75: default route/configuration changed; 76: transient initialization failure.
                if code not in (75, 76) or self._closing:
                    raise error
                now = time.monotonic()
                self._restarts.append(now)
                while self._restarts and now - self._restarts[0] > 10:
                    self._restarts.popleft()
                if code == 76:
                    self._initialization_failures += 1
                if len(self._restarts) > 6 or self._initialization_failures > 3:
                    raise RuntimeError(
                        f"Varsayılan ses aygıtları başlatılamadı: {error}"
                    ) from error
                self._recovering = True
                self.ready.clear()
                self.clear()
                if self.on_route_change:
                    self.on_route_change(True)
                await self._stop_process()
                logging.getLogger("kyros").info(
                    "Reopening current macOS default audio devices"
                )
                await asyncio.sleep(
                    0.3 if code == 75 else 0.6 * self._initialization_failures
                )
                await self._spawn()

    async def _watch_process(self):
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        # EOF on stdout can win the race with the final diagnostic on stderr.
        # Fallback diagnostics need time to flush (synchronize) before exit.
        if self.tasks[0] in done and not self.tasks[2].done():
            try:
                await asyncio.wait_for(asyncio.shield(self.tasks[2]), 0.6)
            except asyncio.TimeoutError:
                pass
        for task in done:
            try:
                task.result()
            except Exception as exc:
                raise RuntimeError(
                    self.error or f"Yerel ses bağlantısı kapandı: {exc}"
                ) from exc
        raise RuntimeError(self.error or "Yerel ses motoru durdu.")

    async def _stderr(self):
        while line := await self.process.stderr.readline():
            text = line.decode(errors="replace").strip()[-1600:]
            self.diagnostics.append(text)
            if text.startswith("[KYROS AUDIO]"):
                logging.getLogger("kyros").info("%s", text)
                if text.startswith("[KYROS AUDIO] Output:"):
                    device_name = text.split("Output:", 1)[1].split("(id=")[0].strip()
                    if _is_headphone_name(device_name):
                        self.headphone = True
                        if self.on_headphone:
                            self.on_headphone(True)
            else:
                self.error = text

    async def _read(self):
        while True:
            header = await self.process.stdout.readexactly(5)
            kind, size = header[:1], struct.unpack("<I", header[1:])[0]
            if size > 2_000_000:
                raise RuntimeError("Invalid native audio frame")
            data = await self.process.stdout.readexactly(size)
            if kind == b"R":
                self._recovering = False
                self._initialization_failures = 0
                self.ready.set()
                if self.on_route_change:
                    self.on_route_change(False)
            elif kind == b"M":
                if not self._recovering:
                    self.on_pcm(data)
            elif kind == b"S" and size == 5:
                generation = struct.unpack("<I", data[:4])[0]
                if generation == self.generation:
                    self.on_playing(bool(data[4]))

    async def _write(self):
        while True:
            kind, data = await self.commands.get()
            self.process.stdin.write(kind + struct.pack("<I", len(data)) + data)
            await self.process.stdin.drain()

    def feed(self, pcm):
        if not self._recovering:
            self.commands.put_nowait((b"P", pcm))

    def clear(self):
        self.generation += 1
        while not self.commands.empty():
            self.commands.get_nowait()
        self.commands.put_nowait((b"C", struct.pack("<I", self.generation)))
        self.on_playing(False)

    async def _stop_process(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 2)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def close(self):
        self._closing = True
        if self.monitor:
            self.monitor.cancel()
            await asyncio.gather(self.monitor, return_exceptions=True)
        await self._stop_process()


class PortAudio:
    """Explicit diagnostic fallback; no echo cancellation. Use headphones."""

    def __init__(self):
        self.lock = threading.Lock()
        self.buffer = bytearray()
        self.playing = False
        self.streams = []
        self.monitor = None

    async def start(self, on_pcm, on_playing):
        import sounddevice as sd

        loop = asyncio.get_running_loop()
        self.on_playing = on_playing
        self.failed = loop.create_future()

        def fail(message):
            if not self.failed.done():
                self.failed.set_exception(RuntimeError(message))

        def capture(data, frames, timing, status):
            if status.input_overflow:
                loop.call_soon_threadsafe(
                    fail, "Mikrofon tamponu taştı; ses aygıtını kontrol edin."
                )
            loop.call_soon_threadsafe(on_pcm, bytes(data))

        def playback(out, frames, timing, status):
            with self.lock:
                size = min(len(out), len(self.buffer))
                out[:] = bytes(self.buffer[:size]) + bytes(len(out) - size)
                del self.buffer[:size]
                playing = size > 0
                if playing != self.playing:
                    self.playing = playing
                    loop.call_soon_threadsafe(on_playing, playing)

        try:
            self.streams.append(
                sd.RawInputStream(
                    samplerate=16000,
                    channels=1,
                    dtype="int16",
                    blocksize=320,
                    callback=capture,
                    latency="low",
                )
            )
            self.streams.append(
                sd.RawOutputStream(
                    samplerate=24000,
                    channels=1,
                    dtype="int16",
                    blocksize=480,
                    callback=playback,
                    latency="low",
                )
            )
            for stream in self.streams:
                stream.start()
        except BaseException:
            await self.close()
            raise
        self.monitor = asyncio.ensure_future(self.failed)

    def feed(self, pcm):
        with self.lock:
            if len(self.buffer) + len(pcm) > 48000 * config.MAX_AUDIO_BUFFER_SECONDS:
                raise RuntimeError("Playback buffer overflow")
            self.buffer.extend(pcm)

    def clear(self):
        with self.lock:
            self.buffer.clear()
            self.playing = False
        self.on_playing(False)

    async def close(self):
        for stream in self.streams:
            stream.abort()
            stream.close()
        self.streams.clear()
        if self.monitor:
            self.monitor.cancel()
