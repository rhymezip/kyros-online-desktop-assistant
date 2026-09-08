import asyncio
import base64
import json
import unittest
from core.gemini_live import GeminiLive, AKTIF, STANDBY
from core.protocol import setup_message


class FakeSocket:
    def __init__(self):
        self.sent = []

    async def send(self, data):
        self.sent.append(json.loads(data))


class FakeAudio:
    def __init__(self):
        self.chunks = []
        self.clears = 0

    def feed(self, data):
        self.chunks.append(data)

    def clear(self):
        self.chunks.clear()
        self.clears += 1


class FakeExecutor:
    def __init__(self):
        self.calls = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False
        self.block = False

    async def execute(self, name, args):
        self.calls.append((name, args))
        self.started.set()
        if self.block:
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        return {"ok": True, "stdout": "actual result"}


def call(id="1", name="run_shell", **args):
    return {"id": id, "name": name, "args": args}


def calls(*items):
    return {"toolCall": {"functionCalls": list(items)}}


class LiveTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.executor = FakeExecutor()
        self.live = GeminiLive(executor=self.executor)
        self.live.ws = FakeSocket()
        self.socket = self.live.ws
        self.live.audio = FakeAudio()
        self.live._send_lock = asyncio.Lock()
        self.live._tool_lock = asyncio.Lock()
        self.live._mic_queue = asyncio.Queue(maxsize=2)
        self.live.connected = True

    async def asyncTearDown(self):
        self.live.ws = None
        self.live._cancel_tools()
        await asyncio.gather(*list(self.live._tasks.values()), return_exceptions=True)
        await asyncio.gather(*list(self.live._notifications), return_exceptions=True)

    async def finish(self):
        await asyncio.gather(*list(self.live._tasks.values()), return_exceptions=True)
        await asyncio.sleep(0)

    def audio(self):
        return {
            "serverContent": {
                "modelTurn": {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "audio/pcm;rate=24000",
                                "data": base64.b64encode(b"\x01\x00" * 100).decode(),
                            }
                        }
                    ]
                }
            }
        }

    async def test_standby_blocks_system_actions_and_audio(self):
        await self.live._handle_message(calls(call(script="anything")))
        await self.live._handle_message(self.audio())
        self.assertEqual(self.executor.calls, [])
        self.assertEqual(self.live.audio.chunks, [])
        result = self.socket.sent[-1]["toolResponse"]["functionResponses"][0]
        self.assertFalse(result["response"]["ok"])
        self.assertEqual(result["name"], "run_shell")

    async def test_model_text_never_changes_mode(self):
        await self.live._handle_message(
            {"serverContent": {"outputTranscription": {"text": "Efendim"}}}
        )
        self.assertEqual(self.live.state, STANDBY)
        await self.live._control("wake")
        await self.live._handle_message(
            {
                "serverContent": {
                    "outputTranscription": {"text": "Tamam efendim bekliyorum"}
                }
            }
        )
        self.assertEqual(self.live.state, AKTIF)

    async def test_wake_and_arbitrary_command_same_batch(self):
        await self.live._handle_message(
            calls(
                call("wake", "session_control", action="wake"),
                call(script="previously unseen command"),
            )
        )
        await self.finish()
        self.assertEqual(
            self.executor.calls,
            [("run_shell", {"script": "previously unseen command"})],
        )
        await self.live._handle_message(self.audio())
        self.assertEqual(len(self.live.audio.chunks), 1)

    async def test_audio_streams_before_turn_complete(self):
        await self.live._control("wake")
        await self.live._handle_message(self.audio())
        self.assertTrue(self.live.audio.chunks)
        self.live._on_playing(True)
        await self.live._handle_message({"serverContent": {"turnComplete": True}})
        self.assertTrue(
            self.live.playing
        )  # real playback, not generation completion, drives UI

    async def test_interrupt_cancels_running_and_queued_work(self):
        self.executor.block = True
        await self.live._control("wake")
        await self.live._handle_message(
            calls(call("1", script="first"), call("2", script="second"))
        )
        await self.executor.started.wait()
        await self.live._handle_message(self.audio())
        await self.live._handle_message({"serverContent": {"interrupted": True}})
        await self.finish()
        self.assertTrue(self.executor.cancelled)
        self.assertEqual(len(self.executor.calls), 1)
        self.assertFalse(self.live.audio.chunks)
        self.assertFalse(self.live._tasks)
        self.assertEqual(self.live.state, AKTIF)

    async def test_cancel_before_coroutine_starts(self):
        await self.live._control("wake")
        await self.live._handle_message(calls(call(script="never start")))
        await self.live._control("stop")
        await self.finish()
        self.assertFalse(self.executor.calls)
        self.assertFalse(self.live._tasks)
        self.assertTrue(self.live._results["1"]["cancelled"])

    async def test_server_cancel_ids_do_not_send_late_response(self):
        self.executor.block = True
        await self.live._control("wake")
        await self.live._handle_message(calls(call(script="first")))
        await self.executor.started.wait()
        await self.live._handle_message({"toolCallCancellation": {"ids": ["1"]}})
        await self.finish()
        self.assertEqual(self.socket.sent, [])

    async def test_standby_cancels_and_blocks_rest_of_batch(self):
        await self.live._control("wake")
        await self.live._handle_message(
            calls(
                call("s", "session_control", action="standby"),
                call(script="do not run"),
            )
        )
        await self.finish()
        self.assertEqual(self.live.state, STANDBY)
        self.assertFalse(self.executor.calls)

    async def test_duplicate_call_is_not_executed_twice(self):
        await self.live._control("wake")
        item = calls(call(script="create one note"))
        await self.live._handle_message(item)
        await self.finish()
        await self.live._handle_message(item)
        self.assertEqual(len(self.executor.calls), 1)
        self.assertEqual(len(self.socket.sent), 2)

    async def test_receiving_continues_while_tool_runs(self):
        self.executor.block = True
        await self.live._control("wake")
        await self.live._handle_message(calls(call(script="slow")))
        await self.executor.started.wait()
        texts = []
        self.live.on_text = lambda who, text: texts.append((who, text))
        await asyncio.wait_for(
            self.live._handle_message(
                {"serverContent": {"inputTranscription": {"text": "yeni istek"}}}
            ),
            0.1,
        )
        await self.live._handle_message(self.audio())
        self.assertEqual(texts, [("Sen", "yeni istek")])
        self.assertTrue(self.live.audio.chunks)

    async def test_resumption_handle_and_nonresumable_update(self):
        await self.live._handle_message(
            {"sessionResumptionUpdate": {"resumable": True, "newHandle": "opaque"}}
        )
        self.assertEqual(self.live._handle, "opaque")
        await self.live._handle_message(
            {"sessionResumptionUpdate": {"resumable": False}}
        )
        self.assertIsNone(self.live._handle)

    async def test_microphone_off_blocks_wake_and_tools(self):
        self.live.mic_muted = True
        result = await self.live._control("wake")
        self.assertFalse(result["ok"])
        await self.live._handle_message(calls(call(script="blocked")))
        self.assertFalse(self.executor.calls)

    async def test_source_links_forwarded_only_when_active(self):
        found = []
        self.live.on_sources = found.append
        msg = {
            "serverContent": {
                "groundingMetadata": {
                    "groundingChunks": [
                        {"web": {"uri": "https://example.org", "title": "Source"}}
                    ]
                }
            }
        }
        await self.live._handle_message(msg)
        self.assertFalse(found)
        await self.live._control("wake")
        await self.live._handle_message(msg)
        self.assertEqual(found[0][0]["title"], "Source")

    def test_setup_keeps_live_model_and_background_tools(self):
        setup = setup_message("original-audio-model", STANDBY, "resume")["setup"]
        self.assertEqual(setup["model"], "models/original-audio-model")
        self.assertEqual(setup["sessionResumption"], {"handle": "resume"})
        self.assertEqual(setup["tools"][1], {"googleSearch": {}})
        for tool in setup["tools"][0]["functionDeclarations"]:
            if tool["name"] != "session_control":
                self.assertEqual(tool["behavior"], "NON_BLOCKING")
        self.assertEqual(
            setup["realtimeInputConfig"]["activityHandling"],
            "START_OF_ACTIVITY_INTERRUPTS",
        )

    async def test_audio_device_change_preserves_session_and_wake_state(self):
        await self.live._control("wake")
        socket = self.live.ws
        self.live._mic_queue.put_nowait(b"old microphone data")
        self.live._on_audio_route(True)
        self.assertEqual(self.live.state, AKTIF)
        self.assertTrue(self.live.connected)
        self.assertIs(self.live.ws, socket)
        self.assertTrue(self.live._mic_queue.empty())
        self.assertEqual(self.live._last_mode, "sesaygiti")
        self.live._on_audio_route(False)
        self.assertEqual(self.live._last_mode, "dinliyor")
        self.live.state = STANDBY
        self.live._on_audio_route(True)
        self.live._on_audio_route(False)
        self.assertEqual(self.live.state, STANDBY)
        self.assertEqual(self.live._last_mode, "bekliyor")
