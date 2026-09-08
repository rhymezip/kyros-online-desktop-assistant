import asyncio
import importlib.util
import json
import unittest
from unittest.mock import patch
from core.gemini_live import GeminiLive, AKTIF


@unittest.skipUnless(
    importlib.util.find_spec("websockets"), "websockets dependency not installed"
)
class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_resumes_without_reexecuting_interrupted_tool(self):
        import websockets
        from websockets.asyncio.server import serve

        class Executor:
            def __init__(self):
                self.count = 0
                self.started = asyncio.Event()
                self.cancelled = False

            async def execute(self, name, args):
                self.count += 1
                self.started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    self.cancelled = True
                    raise

        executor = Executor()
        live = GeminiLive(text_only=True, executor=executor)
        live.api_key = "offline-test-key"
        live.state = AKTIF
        setups, responses = [], []
        server_errors = []

        async def server(socket):
            try:
                setups.append(json.loads(await socket.recv())["setup"])
                await socket.send(json.dumps({"setupComplete": {}}))
                tool = {
                    "toolCall": {
                        "functionCalls": [
                            {
                                "id": "same-id",
                                "name": "run_shell",
                                "args": {"script": "never actually executed"},
                            }
                        ]
                    }
                }
                if len(setups) == 1:
                    await socket.send(
                        json.dumps(
                            {
                                "sessionResumptionUpdate": {
                                    "resumable": True,
                                    "newHandle": "opaque-resume-token",
                                }
                            }
                        )
                    )
                    await socket.send(json.dumps(tool))
                    await executor.started.wait()
                    await socket.close()
                else:
                    await socket.send(json.dumps(tool))
                    async for data in socket:
                        message = json.loads(data)
                        if "toolResponse" in message:
                            responses.append(
                                message["toolResponse"]["functionResponses"][0]
                            )
                            live._stop.set()
                            return
            except Exception as exc:
                server_errors.append(exc)
                if live._stop:
                    live._stop.set()

        real_connect = websockets.connect
        async with serve(server, "127.0.0.1", 0) as listener:
            port = listener.sockets[0].getsockname()[1]
            with patch(
                "websockets.connect",
                side_effect=lambda url, **kwargs: real_connect(
                    f"ws://127.0.0.1:{port}", **kwargs
                ),
            ):
                await asyncio.wait_for(live._run(), 6)
        self.assertFalse(server_errors)
        self.assertEqual(len(setups), 2)
        self.assertEqual(
            setups[1]["sessionResumption"], {"handle": "opaque-resume-token"}
        )
        self.assertEqual(executor.count, 1)
        self.assertTrue(executor.cancelled)
        self.assertTrue(responses[0]["response"]["cancelled"])
        self.assertEqual(responses[0]["scheduling"], "SILENT")
        self.assertFalse(live._tasks)
        self.assertFalse(live.connected)

    async def test_setup_error_is_not_reported_as_connected(self):
        import websockets
        from websockets.asyncio.server import serve

        live = GeminiLive(text_only=True)
        live.api_key = "offline-test-key"
        modes = []
        live.on_state_change = modes.append

        async def server(socket):
            await socket.recv()
            await socket.send(json.dumps({"error": {"message": "model unavailable"}}))

        real_connect = websockets.connect
        async with serve(server, "127.0.0.1", 0) as listener:
            port = listener.sockets[0].getsockname()[1]
            with patch(
                "websockets.connect",
                side_effect=lambda url, **kwargs: real_connect(
                    f"ws://127.0.0.1:{port}", **kwargs
                ),
            ):
                with self.assertRaises(RuntimeError):
                    await asyncio.wait_for(live._run(), 2)
        self.assertNotIn("dinliyor", modes)
        self.assertNotIn("bekliyor", modes)
        self.assertFalse(live.connected)


class StartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_quit_during_microphone_permission_wait(self):
        class Audio:
            def __init__(self):
                self.entered = asyncio.Event()
                self.closed = False

            async def start(self, *args):
                self.entered.set()
                await asyncio.Event().wait()

            async def close(self):
                self.closed = True

        audio = Audio()
        live = GeminiLive()
        with patch("core.audio_io.NativeAudio", return_value=audio):
            task = asyncio.create_task(live._run())
            await audio.entered.wait()
            live._stop.set()
            await asyncio.wait_for(task, 1)
        self.assertTrue(audio.closed)
