import asyncio
import struct
import unittest
from types import SimpleNamespace
from core.audio_io import NativeAudio


def frame(kind, data=b""):
    return kind + struct.pack("<I", len(data)) + data


class AudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_pcm_and_generation_aware_playback_events(self):
        audio = NativeAudio()
        pcm, playing = [], []
        audio.on_pcm, audio.on_playing = pcm.append, playing.append
        audio.generation = 2
        reader = asyncio.StreamReader()
        audio.process = SimpleNamespace(stdout=reader)
        reader.feed_data(frame(b"R") + frame(b"M", b"\x01\x00" * 320))
        reader.feed_data(
            frame(b"S", struct.pack("<I", 1) + b"\x01")
        )  # old output must not revive UI
        reader.feed_data(frame(b"S", struct.pack("<I", 2) + b"\x01"))
        reader.feed_eof()
        with self.assertRaises(asyncio.IncompleteReadError):
            await audio._read()
        self.assertTrue(audio.ready.is_set())
        self.assertEqual(pcm, [b"\x01\x00" * 320])
        self.assertEqual(playing, [True])

    async def test_clear_discards_queued_audio_before_native_stop(self):
        audio = NativeAudio()
        playing = []
        audio.on_playing = playing.append
        audio.feed(b"old audio")
        audio.feed(b"more old audio")
        audio.clear()
        self.assertEqual(audio.commands.qsize(), 1)
        kind, data = audio.commands.get_nowait()
        self.assertEqual(kind, b"C")
        self.assertEqual(struct.unpack("<I", data)[0], 1)
        self.assertEqual(playing, [False])

    async def test_native_write_uses_framed_pcm(self):
        class Sink:
            def __init__(self):
                self.data = bytearray()

            def write(self, data):
                self.data.extend(data)

            async def drain(self):
                pass

        audio = NativeAudio()
        sink = Sink()
        audio.process = SimpleNamespace(stdin=sink)
        audio.feed(b"\x01\x00")
        task = asyncio.create_task(audio._write())
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(sink.data, frame(b"P", b"\x01\x00"))

    async def test_final_native_error_is_preserved_when_stdout_closes_first(self):
        audio = NativeAudio()

        async def stdout():
            raise asyncio.IncompleteReadError(b"", 5)

        async def writer():
            await asyncio.Event().wait()

        async def stderr():
            await asyncio.sleep(0.02)
            audio.error = "failed at start voice-processing engine: code=-10875"

        audio.tasks = [
            asyncio.create_task(stdout()),
            asyncio.create_task(writer()),
            asyncio.create_task(stderr()),
        ]
        try:
            with self.assertRaisesRegex(RuntimeError, "code=-10875"):
                await audio._watch_process()
        finally:
            for task in audio.tasks:
                task.cancel()
            await asyncio.gather(*audio.tasks, return_exceptions=True)

    async def test_default_device_change_restarts_audio_without_finishing_monitor(self):
        from unittest.mock import AsyncMock

        audio = NativeAudio()
        audio.on_playing = lambda value: None
        routes = []
        audio.on_route_change = routes.append
        audio.process = SimpleNamespace(wait=AsyncMock(return_value=75))
        reconnected = asyncio.Event()
        reads = 0

        async def watch():
            nonlocal reads
            reads += 1
            if reads == 1:
                raise RuntimeError("route changed")
            reconnected.set()
            await asyncio.Event().wait()

        audio._watch_process = watch
        audio._stop_process = AsyncMock()
        audio._spawn = AsyncMock()
        monitor = asyncio.create_task(audio._monitor())
        try:
            await asyncio.wait_for(reconnected.wait(), 1)
            audio._spawn.assert_awaited_once()
            self.assertFalse(monitor.done())
            self.assertEqual(routes, [True])
            self.assertTrue(audio._recovering)
            queued = audio.commands.qsize()
            audio.feed(b"old speaker data during device switch")
            self.assertEqual(audio.commands.qsize(), queued)
        finally:
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)

    async def test_permanent_native_error_does_not_restart_forever(self):
        from unittest.mock import AsyncMock

        audio = NativeAudio()
        audio.process = SimpleNamespace(wait=AsyncMock(return_value=1))
        audio._watch_process = AsyncMock(side_effect=RuntimeError("permission denied"))
        audio._spawn = AsyncMock()
        with self.assertRaisesRegex(RuntimeError, "permission denied"):
            await audio._monitor()
        audio._spawn.assert_not_awaited()

    async def test_initialization_retries_are_bounded(self):
        from unittest.mock import AsyncMock, patch

        audio = NativeAudio()
        audio.on_playing = lambda value: None
        audio.process = SimpleNamespace(wait=AsyncMock(return_value=76))
        audio._watch_process = AsyncMock(
            side_effect=RuntimeError("initialization failed")
        )
        audio._stop_process = AsyncMock()
        audio._spawn = AsyncMock()
        with patch("core.audio_io.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaisesRegex(RuntimeError, "başlatılamadı"):
                await audio._monitor()
        self.assertEqual(audio._spawn.await_count, 3)
