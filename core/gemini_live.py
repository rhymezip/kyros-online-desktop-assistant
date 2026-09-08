"""Full-duplex Gemini Live session with cancellable general macOS tools."""

import asyncio
import base64
from collections import OrderedDict
import json
import logging
import threading
import time
from urllib.parse import quote

import config
from core.executor import ToolExecutor
from core.protocol import setup_message

STANDBY = "standby"
AKTIF = "aktif"
log = logging.getLogger("kyros")


class GeminiLive:
    def __init__(self, *, text_only=False, audio_backend=None, executor=None):
        self.api_key = config.GEMINI_API_KEY
        self.model = config.GEMINI_MODEL
        self.text_only = text_only
        self.audio_backend = audio_backend or config.AUDIO_BACKEND
        self.executor = executor or ToolExecutor()
        self.state = STANDBY
        self.mic_muted = False
        self.is_running = False
        self.connected = False
        self.playing = False
        self.ws = None
        self.audio = None
        self.on_text = None
        self.on_state_change = None
        self.on_mic_level = None
        self.on_disconnect = None
        self.on_error = None
        self.on_tool = None
        self.on_sources = None
        self._thread = None
        self._loop = None
        self._stop = None
        self._startup_stop = threading.Event()
        self._send_lock = None
        self._tool_lock = None
        self._mic_queue = None
        self._tasks = {}
        self._notifications = set()
        self._results = OrderedDict()
        self._server_cancelled = set()
        self._epoch = 0
        self._handle = None
        self._last_mode = None
        self._last_level_at = 0
        self._last_input_at = None
        self._discard_until_turn_end = False
        self._audio_changing = False
        self._last_playing_end = 0.0
        self._playing_start = 0.0
        self._gated_dropped = 0
        self._feedback_until = 0.0
        self._barge_in_loud_count = 0
        self._barge_in_until = 0.0

    def _emit(self, callback, *args):
        if callback:
            try:
                callback(*args)
            except Exception:
                log.exception("UI callback failed")

    def _refresh(self, override=None):
        mode = override or (
            "kapali"
            if self.mic_muted
            else "baglaniyor"
            if not self.connected
            else "sesaygiti"
            if self._audio_changing
            else "bekliyor"
            if self.state == STANDBY
            else "konusuyor"
            if self.playing
            else "uyguluyor"
            if self._tasks
            else "dinliyor"
        )
        if mode != self._last_mode:
            self._last_mode = mode
            self._emit(self.on_state_change, mode)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._startup_stop.clear()
        self.is_running = True
        self._thread = threading.Thread(
            target=self._thread_main, name="kyros-live", daemon=True
        )
        self._thread.start()

    def stop(self):
        self._startup_stop.set()
        if self._loop and self._stop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=6)

    def _thread_main(self):
        try:
            asyncio.run(self._run())
        except Exception as exc:
            self._error(exc)
        finally:
            self.is_running = False
            self.connected = False
            self._refresh("hata" if not self._startup_stop.is_set() else "kapali")

    def _error(self, exc):
        # Don't spam "0 bytes read" on normal Ctrl+C / close
        if self._startup_stop.is_set() or not self.is_running:
            log.info("Shutting down: %s", str(exc)[:200])
            return
        message = str(exc)
        if self.api_key:
            message = message.replace(self.api_key, "[hidden]").replace(
                quote(self.api_key, safe=""), "[hidden]"
            )
        message = message[:1000]
        log.error("%s", message)
        self._emit(self.on_error, message)

    async def _run(self):
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._tool_lock = asyncio.Lock()
        self._mic_queue = asyncio.Queue(maxsize=15)
        if self._startup_stop.is_set():
            return
        self._refresh("baglaniyor")
        tasks = []
        try:
            if not self.text_only:
                from core.audio_io import NativeAudio, PortAudio

                self.audio = (
                    NativeAudio() if self.audio_backend == "native" else PortAudio()
                )
                self.audio.on_route_change = self._on_audio_route
                startup = asyncio.create_task(
                    self.audio.start(self._on_pcm, self._on_playing)
                )
                stop_startup = asyncio.create_task(self._stop.wait())
                try:
                    done, _ = await asyncio.wait(
                        [startup, stop_startup], return_when=asyncio.FIRST_COMPLETED
                    )
                    if stop_startup in done:
                        return
                    await startup
                finally:
                    startup.cancel()
                    stop_startup.cancel()
                    await asyncio.gather(startup, stop_startup, return_exceptions=True)
                tasks.append(self.audio.monitor)
            tasks.extend(
                [
                    asyncio.create_task(self._connections()),
                    asyncio.create_task(self._stop.wait()),
                ]
            )
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            self.connected = False
            # Stop the receiver before awaiting tool cleanup so no new work can enter.
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.ws = None
            self._cancel_tools()
            await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)
            for task in list(self._notifications):
                task.cancel()
            await asyncio.gather(*list(self._notifications), return_exceptions=True)
            if self.audio:
                await self.audio.close()
            self.audio = None

    def _on_audio_route(self, changing):
        self._audio_changing = changing
        self._drain_mic()
        self.playing = False
        self._emit(self.on_mic_level, 0.0)
        self._refresh()

    def _on_pcm(self, pcm):
        now = time.monotonic()
        # Compute RMS once for both level and gating
        import array

        samples = array.array("h", pcm)
        rms = (sum(value * value for value in samples) / max(1, len(samples))) ** 0.5
        if now - self._last_level_at >= 0.05:
            self._emit(
                self.on_mic_level, 0.0 if self.mic_muted else min(1.0, rms / 6000)
            )
            self._last_level_at = now
        if self.connected and not self.mic_muted:
            # — Wake/standby feedback kesilmesin
            if now < self._feedback_until:
                return
            # Barge-in penceresi açıksa direkt gönder
            if now < self._barge_in_until:
                # barge-in aktif — gate bypass
                pass
            else:
                is_playing = self.playing
                is_recent = now - self._last_playing_end < config.MIC_GATE_HANGOVER_MS / 1000.0
                if is_playing:
                    if now - self._playing_start < config.MIC_GATE_BLOCK_MS / 1000.0:
                        self._gated_dropped += 1
                        return
                    # Barge-in: sus/dur/bir dakika/bir dakika bekle — 2 ardışık yüksek ses yeterli
                    if rms > 2500:
                        self._barge_in_loud_count += 1
                    else:
                        self._barge_in_loud_count = 0
                    if self._barge_in_loud_count >= 2:  # ~170ms
                        log.info("Barge-in: dur/sus algılandı rms=%.0f — kesiliyor", rms)
                        self._barge_in_loud_count = 0
                        self._barge_in_until = now + 0.9  # sonraki 0.9s boyunca tüm mic'i geçir
                        self._clear_audio()
                        self._cancel_tools()
                    else:
                        self._gated_dropped += 1
                        if self._gated_dropped % 80 == 0:
                            log.info("Mic gate: dropping while playing rms=%.0f", rms)
                        return
                else:
                    self._barge_in_loud_count = 0
                if is_recent and rms < config.MIC_GATE_RMS:
                    self._gated_dropped += 1
                    if self._gated_dropped % 40 == 0:
                        log.info(
                            "Mic gate: dropping echo hangover rms=%.0f thr=%d",
                            rms,
                            config.MIC_GATE_RMS,
                        )
                    return
            # Never replay stale microphone audio after congestion/reconnection.
            if self._mic_queue.full():
                self._mic_queue.get_nowait()
                log.warning("Microphone congestion: oldest chunk discarded")
            self._mic_queue.put_nowait(pcm)

    def _on_playing(self, playing):
        was_playing = self.playing
        self.playing = playing and self.state == AKTIF and not self.mic_muted
        if not was_playing and self.playing:
            self._playing_start = time.monotonic()
        if was_playing and not self.playing:
            self._last_playing_end = time.monotonic()
        self._refresh()

    def _clear_audio(self):
        if self.audio:
            self.audio.clear()
        self.playing = False
        self._refresh()

    async def _send(self, message):
        async with self._send_lock:
            if not self.ws:
                raise ConnectionError("Gemini bağlantısı yok")
            await self.ws.send(json.dumps(message))

    async def _connections(self):
        import websockets
        from websockets.exceptions import ConnectionClosed

        delay = 1
        while not self._stop.is_set():
            established = False
            try:
                url = (
                    "wss://generativelanguage.googleapis.com/ws/"
                    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key="
                    + quote(self.api_key, safe="")
                )
                self._refresh("baglaniyor")
                async with websockets.connect(
                    url,
                    max_size=16 * 1024 * 1024,
                    open_timeout=15,
                    close_timeout=2,
                    ping_interval=20,
                    ping_timeout=20,
                ) as ws:
                    self.ws = ws
                    await self._send(
                        setup_message(self.model, self.state, self._handle)
                    )
                    response = json.loads(await asyncio.wait_for(ws.recv(), 15))
                    if "setupComplete" not in response:
                        raise RuntimeError(
                            "Gemini oturumu kabul edilmedi: " + json.dumps(response)
                        )
                    established = True
                    self.connected = True
                    self._discard_until_turn_end = False
                    delay = 1
                    self._drain_mic()
                    self._refresh()
                    log.info(
                        "Live connected model=%s resumed=%s",
                        self.model,
                        bool(self._handle),
                    )
                    # Reconcile real local state with resumed conversation; never replay commands.
                    if self._handle:
                        await self._send(
                            {
                                "realtimeInput": {
                                    "text": f"[Uygulama durumu] Yeniden bağlanıldı. Oturum: {self.state}. "
                                    "Bağlantı sırasında çalışan işler durduruldu; tamamlanmış etkiler kalmış olabilir. "
                                    "Bu durum bildirimine cevap verme. Kullanıcı istemeden eski işi yeniden başlatma; gerektiğinde önce sonucu kontrol et."
                                }
                            }
                        )
                    sender = asyncio.create_task(self._sender())
                    receiver = asyncio.create_task(self._receiver(ws))
                    try:
                        done, _ = await asyncio.wait(
                            [sender, receiver], return_when=asyncio.FIRST_COMPLETED
                        )
                        for task in done:
                            task.result()
                    finally:
                        sender.cancel()
                        receiver.cancel()
                        await asyncio.gather(sender, receiver, return_exceptions=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._error(exc)
                # A stale resumption token may be rejected; retry once as a fresh session.
                if not established and self._handle:
                    self._handle = None
                elif not established:
                    status = getattr(
                        getattr(exc, "response", None), "status_code", None
                    )
                    if (
                        isinstance(exc, RuntimeError)
                        or status in (400, 401, 403, 404)
                        or (
                            isinstance(exc, ConnectionClosed)
                            and exc.code in (1007, 1008)
                        )
                    ):
                        raise
            finally:
                self.connected = False
                self.ws = None
                self._clear_audio()
                self._cancel_tools()
                await asyncio.gather(
                    *list(self._tasks.values()), return_exceptions=True
                )
                self._drain_mic()
                self._emit(self.on_disconnect)
                self._refresh()
            try:
                await asyncio.wait_for(self._stop.wait(), delay)
            except asyncio.TimeoutError:
                pass
            delay = min(delay * 2, 20)

    def _drain_mic(self):
        if self._mic_queue:
            while not self._mic_queue.empty():
                self._mic_queue.get_nowait()

    async def _sender(self):
        while True:
            pcm = await self._mic_queue.get()
            if not self.mic_muted:
                await self._send(
                    {
                        "realtimeInput": {
                            "audio": {
                                "mimeType": "audio/pcm;rate=16000",
                                "data": base64.b64encode(pcm).decode(),
                            }
                        }
                    }
                )

    async def _receiver(self, ws):
        async for raw in ws:
            message = json.loads(raw)
            await self._handle_message(message)
            if "goAway" in message:
                log.info("Server requested session renewal")
                return

    async def _handle_message(self, message):
        if "error" in message:
            raise RuntimeError(json.dumps(message["error"]))
        update = message.get("sessionResumptionUpdate")
        if update is not None:
            if update.get("resumable") and update.get("newHandle"):
                self._handle = update["newHandle"]
            elif update.get("resumable") is False:
                self._handle = None
        cancellation = message.get("toolCallCancellation", {})
        if cancellation:
            ids = cancellation.get("ids", [])
            self._server_cancelled.update(ids)
            self._cancel_tools(ids)
        content = message.get("serverContent", {})
        if content.get("interrupted"):
            self._discard_until_turn_end = True
            self._clear_audio()
            self._cancel_tools()
            log.info("User interruption: playback flushed, pending work cancelled")
        transcript = content.get("inputTranscription", {}).get("text")
        if transcript:
            self._last_input_at = time.monotonic()
            self._emit(self.on_text, "Sen", transcript)
        transcript = content.get("outputTranscription", {}).get("text")
        # Standby/wake feedback (bekleme cümlesi) STANDBY'de de duyulsun — _feedback_until penceresi
        is_feedback_window = time.monotonic() < self._feedback_until
        if (
            transcript
            and (self.state == AKTIF or is_feedback_window)
            and not self.mic_muted
            and not self._discard_until_turn_end
        ):
            self._emit(self.on_text, "Kyros", transcript)
        if not self._discard_until_turn_end:
            for part in content.get("modelTurn", {}).get("parts", []):
                data = part.get("inlineData", {})
                if (
                    data.get("mimeType", "").startswith("audio/pcm")
                    and (self.state == AKTIF or is_feedback_window)
                    and not self.mic_muted
                ):
                    if self.audio:
                        self.audio.feed(base64.b64decode(data["data"]))
                    if self._last_input_at is not None:
                        log.info(
                            "First audio after last transcript: %.0f ms",
                            (time.monotonic() - self._last_input_at) * 1000,
                        )
                        self._last_input_at = None
        grounding = content.get("groundingMetadata")
        if grounding and self.state == AKTIF:
            sources = [
                chunk["web"]
                for chunk in grounding.get("groundingChunks", [])
                if "web" in chunk
            ]
            self._emit(self.on_sources, sources)
        stopped_batch = False
        for call in message.get("toolCall", {}).get("functionCalls", []):
            call_id, name = call.get("id", ""), call.get("name", "")
            args = call.get("args", {})
            if call_id in self._tasks:
                continue
            if call_id in self._results:
                await self._respond(call, self._results[call_id])
                continue
            if stopped_batch:
                await self._respond(call, {"ok": False, "cancelled": True})
            elif name == "session_control":
                result = await self._control(args.get("action"))
                stopped_batch = args.get("action") in ("stop", "standby")
                self._remember(call_id, result)
                await self._respond(call, result)
            elif self.state != AKTIF or self.mic_muted or self._discard_until_turn_end:
                result = {
                    "ok": False,
                    "error": "Standby/microphone off: wake first; no system action executed.",
                }
                self._remember(call_id, result)
                await self._respond(call, result)
            else:
                task = asyncio.create_task(self._run_tool(call, self._epoch))
                self._tasks[call_id] = task
                task.add_done_callback(
                    lambda done, call=call: self._tool_done(call, done)
                )
                self._refresh()
        if content.get("turnComplete"):
            self._discard_until_turn_end = False

    def _tool_done(self, call, task):
        # Cancellation may arrive before the coroutine's first instruction/finally block.
        if not task.cancelled():
            return
        call_id = call["id"]
        self._tasks.pop(call_id, None)
        result = {
            "ok": False,
            "cancelled": True,
            "detail": "Cancelled before execution.",
        }
        self._remember(call_id, result)
        self._refresh()
        if self.ws and call_id not in self._server_cancelled:

            async def notify_cancelled():
                try:
                    await self._respond(call, result)
                except Exception as exc:
                    self._error(exc)

            notification = asyncio.create_task(notify_cancelled())
            self._notifications.add(notification)
            notification.add_done_callback(self._notifications.discard)

    async def _control(self, action):
        if action == "wake":
            if self.mic_muted:
                return {"ok": False, "error": "Microphone is disabled by the user."}
            self.state = AKTIF
            # Wake feedback ("Efendim, sizi dinliyorum") 1.2s boyunca kesilmesin
            self._feedback_until = time.monotonic() + 1.2
        elif action == "standby":
            # Bekleme cümlesi ÖNCE söylendi (protokolde), sonra standby çağrılır.
            # O cümleyi kesmemek için discard/clear yapma — sadece araçları iptal et.
            self.state = STANDBY
            self._feedback_until = time.monotonic() + 1.0
            self._cancel_tools()
        elif action == "stop":
            self.state = AKTIF
            self._discard_until_turn_end = True
            self._clear_audio()
            self._cancel_tools()
        else:
            return {"ok": False, "error": "Unknown session action"}
        self._refresh()
        return {
            "ok": True,
            "state": self.state,
            "detail": "Pending work cancelled; completed side effects are not undone."
            if action != "wake"
            else "Awake",
        }

    def _cancel_tools(self, ids=None):
        if ids is None:
            self._epoch += 1
        for call_id, task in list(self._tasks.items()):
            if ids is None or call_id in ids:
                if not task.cancelling():
                    task.cancel()

    def _remember(self, call_id, result):
        self._results[call_id] = result
        self._results.move_to_end(call_id)
        while len(self._results) > 256:
            old, _ = self._results.popitem(last=False)
            self._server_cancelled.discard(old)

    async def _run_tool(self, call, epoch):
        call_id, name = call["id"], call["name"]
        started = time.monotonic()
        result = {
            "ok": False,
            "cancelled": True,
            "detail": "Cancelled; verify any already completed side effects before retrying.",
        }
        try:
            # Serialize mutations so separately returned tool calls cannot race in the UI.
            async with self._tool_lock:
                if epoch != self._epoch or self.state != AKTIF or self.mic_muted:
                    return
                self._emit(self.on_tool, name, "başladı")
                result = await self.executor.execute(name, call.get("args", {}))
                image = result.pop("_image", None)
                if image and self.ws and epoch == self._epoch:
                    await self._send(
                        {
                            "realtimeInput": {
                                "video": {"mimeType": "image/jpeg", "data": image}
                            }
                        }
                    )
        except asyncio.CancelledError:
            result = {
                "ok": False,
                "cancelled": True,
                "detail": "Cancelled; completed side effects may remain. Do not restart without user intent.",
            }
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        finally:
            self._remember(call_id, result)
            self._tasks.pop(call_id, None)
            log.info(
                "Tool name=%s ok=%s cancelled=%s elapsed_ms=%.0f",
                name,
                result.get("ok"),
                result.get("cancelled", False),
                (time.monotonic() - started) * 1000,
            )
            self._emit(
                self.on_tool,
                name,
                "iptal"
                if result.get("cancelled")
                else "tamamlandı"
                if result.get("ok")
                else "hata",
            )
            self._refresh()
            if self.ws and call_id not in self._server_cancelled:
                try:
                    await self._respond(call, result)
                except Exception as exc:
                    self._error(exc)

    async def _respond(self, call, result):
        response = dict(result)
        function_response = {
            "id": call.get("id", ""),
            "name": call.get("name", ""),
            "response": response,
        }
        if call.get("name") != "session_control":
            function_response["scheduling"] = (
                "SILENT"
                if result.get("cancelled") or self.state != AKTIF
                else "WHEN_IDLE"
            )
        await self._send({"toolResponse": {"functionResponses": [function_response]}})

    def _submit(self, factory):
        if not self._loop or self._loop.is_closed() or not self.is_running:
            return
        future = asyncio.run_coroutine_threadsafe(factory(), self._loop)

        def finished(done):
            try:
                done.result()
            except Exception as exc:
                self._error(exc)

        future.add_done_callback(finished)

    def send_text(self, text):
        if not text.strip():
            return

        async def send():
            self._clear_audio()
            self._cancel_tools()
            self._emit(self.on_text, "Sen", text)
            await self._send({"realtimeInput": {"text": text}})

        self._submit(send)

    def control(self, action):
        async def apply():
            result = await self._control(action)
            if self.connected:
                instruction = (
                    "Kısaca selamla."
                    if action == "wake" and result.get("ok")
                    else "Sessiz kal, yalnızca sonraki kullanıcı isteğini bekle."
                )
                await self._send(
                    {
                        "realtimeInput": {
                            "text": f"[Panel kontrolü] {action}; gerçek durum {self.state}. Önceki işi tekrar başlatma. {instruction}"
                        }
                    }
                )

        self._submit(apply)

    def set_mic_muted(self, muted):
        async def apply():
            self.mic_muted = bool(muted)
            self._drain_mic()
            if muted:
                await self._control("standby")
                if self.connected:
                    await self._send({"realtimeInput": {"audioStreamEnd": True}})
            self._refresh()

        self._submit(apply)
