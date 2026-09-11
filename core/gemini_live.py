"""Full-duplex Gemini Live session with cancellable general desktop tools."""

import asyncio
import base64
import json
import logging
import sys
import threading
import time
from collections import OrderedDict
from urllib.parse import quote

import config
from core.executor import ToolExecutor
from core.protocol import setup_message

STANDBY = "standby"
AKTIF = "aktif"
log = logging.getLogger("kyros.live")
tool_log = logging.getLogger("kyros.tool")

MODE_LABELS = {
    "kapali": "Mikrofon kapalı",
    "baglaniyor": "Bağlantı kuruluyor",
    "sesaygiti": "Ses aygıtı değişiyor",
    "bekliyor": "Bekliyor",
    "konusuyor": "Yanıt veriyor",
    "uyguluyor": "İşlem uyguluyor",
    "dinliyor": "Dinliyor",
    "hata": "Bağlantı veya ses hatası",
}
TOOL_LABELS = {
    "run_shell": "Komut",
    "run_applescript": "Mac otomasyonu",
    "computer": "Ekran işlemi",
    "linux_desktop": "Linux masaüstü",
    "launch_app": "Uygulama başlatma",
    "media_control": "Medya kontrolü",
    "clipboard": "Clipboard",
    "read_web": "Web okuma",
    "google_search": "Web araması",
    "session_control": "Oturum kontrolü",
}


def _friendly_error_message(exc):
    message = str(exc)
    lower = message.lower()
    if _is_audio_protocol_error(message):
        return (
            "Gemini Live bu ses akışını oturum yapılandırmasında kabul etmedi "
            "(1007); bağlantı güvenli şekilde durduruldu. Model/protokol yapılandırmasını kontrol edin."
        )
    if "1011" in message or "internal error" in lower:
        return "Gemini bağlantısı beklenmedik biçimde kapandı (1011). Yeniden bağlanılacak."
    if "timed out" in lower or "timeout" in lower:
        return "Bağlantı zaman aşımına uğradı. Yeniden denenecek."
    if "401" in message or "403" in message:
        return "Gemini API anahtarı reddedildi. Ayarlardaki anahtarı kontrol edin."
    return message


def _is_audio_protocol_error(message):
    lower = str(message).lower()
    return "1007" in str(message) and (
        "content_type_audio" in lower
        or "audio content type" in lower
        or "invalid frame payload data" in lower
    )


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
        self._shutdown_done = threading.Event()
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
        self._model_responding = False
        self._playback_epoch = 0
        self._playback_stop_task = None
        self._mic_dropped = 0
        self._last_mic_drop_log = 0.0
        self._last_interrupt_at = 0.0
        # Live can emit a late second response while the microphone is idle.
        # Keep an explicit user-turn gate so that late model speech/tool calls
        # cannot become a self-started conversation.
        self._user_input_serial = 0
        self._last_session_control_serial = 0
        self._assistant_turn_open = False
        self._tool_response_pending = False
        self._awaiting_user_input = True
        self._last_action_input_serial = -1

    def _emit(self, callback, *args):
        # Qt/AppKit callbacks can repaint native windows.  Once shutdown has
        # started, no worker-thread callback is allowed to reach the UI.
        if callback and not self._startup_stop.is_set():
            try:
                callback(*args)
            except Exception:
                log.exception("Arayüz güncellenemedi.")

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
            if self.playing or self._model_responding
            else "uyguluyor"
            if self._tasks
            else "dinliyor"
        )
        if mode != self._last_mode:
            self._last_mode = mode
            log.info("Durum: %s.", MODE_LABELS.get(mode, mode))
            self._emit(self.on_state_change, mode)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._startup_stop.clear()
        self._shutdown_done.clear()
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
            # A websocket handshake may have its 15-second open timeout.  Do
            # not leave the daemon audio/asyncio thread behind while Qt exits.
            self._thread.join(timeout=20)
            if self._thread.is_alive():
                log.warning("Canlı oturum güvenli kapanış için beklenen sürede durmadı.")

    def _thread_main(self):
        try:
            asyncio.run(self._run())
        except Exception as exc:
            self._error(exc)
        finally:
            self.is_running = False
            self.connected = False
            self._refresh("hata" if not self._startup_stop.is_set() else "kapali")
            self._shutdown_done.set()

    def _error(self, exc):
        # Don't spam "0 bytes read" on normal Ctrl+C / close
        if self._startup_stop.is_set() or not self.is_running:
            log.debug("Kapanış ayrıntısı: %s", str(exc)[:200])
            return
        message = str(exc)
        if self.api_key:
            message = message.replace(self.api_key, "[hidden]").replace(
                quote(self.api_key, safe=""), "[hidden]"
            )
        technical_message = message[:1000]
        friendly_message = _friendly_error_message(technical_message)
        log.error("Bağlantı sorunu: %s", friendly_message)
        if friendly_message != technical_message:
            log.debug("Ham bağlantı hatası: %s", technical_message)
        self._emit(self.on_error, friendly_message)

    async def _run(self):
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._tool_lock = asyncio.Lock()
        self._mic_queue = asyncio.Queue(maxsize=config.MIC_QUEUE_SIZE)
        if self._startup_stop.is_set():
            return
        self._refresh("baglaniyor")
        tasks = []
        try:
            if not self.text_only:
                if sys.platform == "darwin":
                    from core.audio_io import NativeAudio, PortAudio

                    if self.audio_backend == "native":
                        input_id = int(config.AUDIO_INPUT_DEVICE) if config.AUDIO_INPUT_DEVICE else None
                        output_id = int(config.AUDIO_OUTPUT_DEVICE) if config.AUDIO_OUTPUT_DEVICE else None
                        self.audio = NativeAudio(input_device_id=input_id, output_device_id=output_id)
                    else:
                        # Preserve the original macOS fallback semantics for
                        # every non-native value; Linux selects its own branch.
                        self.audio = PortAudio()
                elif sys.platform == "linux":
                    from core.linux_audio import PipeWireAudio, PortAudio

                    input_id = config.AUDIO_INPUT_DEVICE or None
                    output_id = config.AUDIO_OUTPUT_DEVICE or None
                    if self.audio_backend in ("pipewire", "native"):
                        self.audio = PipeWireAudio(
                            input_device_id=input_id, output_device_id=output_id
                        )
                    elif self.audio_backend == "portaudio":
                        self.audio = PortAudio(
                            input_device_id=input_id, output_device_id=output_id
                        )
                    else:
                        raise RuntimeError(
                            f"Linux ses backendi desteklenmiyor: {self.audio_backend}"
                        )
                else:
                    raise RuntimeError("Kyros ses backendi yalnızca macOS ve Linux'ta destekleniyor.")
                self.audio.on_route_change = self._on_audio_route
                if hasattr(self.audio, "on_headphone"):
                    self.audio.on_headphone = self._on_headphone
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
        self._playback_epoch += 1
        self._cancel_playback_stop()
        self.playing = False
        self._emit(self.on_mic_level, 0.0)
        self._refresh()

    def _on_headphone(self, is_headphone):
        if is_headphone:
            config.BARGE_IN_RMS = 1100
        else:
            config.BARGE_IN_RMS = 5000
        log.debug(
            "Ses çıkışı türü: %s; söz kesme eşiği=%d",
            "kulaklık" if is_headphone else "hoparlör",
            config.BARGE_IN_RMS,
        )

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
                is_playing = self.playing or self._model_responding
                is_recent = now - self._last_playing_end < config.MIC_GATE_HANGOVER_MS / 1000.0
                if is_playing:
                    if now - self._playing_start < config.MIC_GATE_BLOCK_MS / 1000.0:
                        self._gated_dropped += 1
                        return
                    # Require several consecutive frames so a click/pop or a
                    # single echo peak does not cancel a response.
                    if rms > config.BARGE_IN_RMS:
                        self._barge_in_loud_count += 1
                    else:
                        self._barge_in_loud_count = 0
                    if (
                        self._barge_in_loud_count
                        >= config.BARGE_IN_CONSECUTIVE_CHUNKS
                    ):
                        log.info("Sesli durdurma algılandı; yanıt kesildi.")
                        log.debug("Söz kesme seviyesi: rms=%.0f eşik=%d", rms, config.BARGE_IN_RMS)
                        self._barge_in_loud_count = 0
                        self._barge_in_until = now + 0.9  # sonraki 0.9s boyunca tüm mic'i geçir
                        self._clear_audio()
                        self._cancel_tools()
                        # bu chunk dahil hepsi gidecek — düşürme
                    else:
                        self._gated_dropped += 1
                        if self._gated_dropped % 80 == 0:
                            log.debug("Konuşma sırasında yankı bastırıldı: rms=%.0f", rms)
                        return
                else:
                    self._barge_in_loud_count = 0
                if is_recent and rms < config.MIC_GATE_RMS:
                    self._gated_dropped += 1
                    if self._gated_dropped % 40 == 0:
                        log.debug(
                            "Yanıt sonrası yankı bastırıldı: rms=%.0f eşik=%d",
                            rms,
                            config.MIC_GATE_RMS,
                        )
                    return
            # Never replay stale microphone audio after congestion/reconnection.
            if self._mic_queue.full():
                self._mic_queue.get_nowait()
                self._mic_dropped += 1
                if (
                    now - self._last_mic_drop_log
                    >= config.MIC_DROP_LOG_INTERVAL
                ):
                    log.warning(
                        "Mikrofon akışı yoğunlaştı; %d eski ses parçası atlandı.",
                        self._mic_dropped,
                    )
                    self._mic_dropped = 0
                    self._last_mic_drop_log = now
            self._mic_queue.put_nowait(pcm)

    def _cancel_playback_stop(self):
        task = self._playback_stop_task
        if task and not task.done():
            task.cancel()
        self._playback_stop_task = None

    async def _settle_playback_stop(self, epoch):
        try:
            await asyncio.sleep(config.PLAYBACK_STATE_HANGOVER_MS / 1000.0)
            if epoch != self._playback_epoch:
                return
            self.playing = False
            self._last_playing_end = time.monotonic()
            self._refresh()
        except asyncio.CancelledError:
            return
        finally:
            if self._playback_stop_task is asyncio.current_task():
                self._playback_stop_task = None

    def _on_playing(self, playing):
        was_playing = self.playing
        requested = bool(playing and self.state == AKTIF and not self.mic_muted)
        self._playback_epoch += 1
        epoch = self._playback_epoch
        if requested:
            self._cancel_playback_stop()
        elif was_playing:
            # PipeWire and PortAudio can briefly report an empty buffer between
            # adjacent writes.  Keep the echo gate/UI in the speaking state for
            # a short, bounded hangover and let a new true edge cancel it.
            self._playback_stop_task = asyncio.create_task(
                self._settle_playback_stop(epoch)
            )
        self.playing = requested if requested else was_playing
        if not was_playing and self.playing:
            self._playing_start = time.monotonic()
        if requested:
            self._last_playing_end = 0.0
        self._refresh()

    def _clear_audio(self):
        self._playback_epoch += 1
        self._cancel_playback_stop()
        if self.audio:
            self.audio.clear()
        self._playback_epoch += 1
        self._cancel_playback_stop()
        if self.playing:
            self._last_playing_end = time.monotonic()
        self.playing = False
        self._model_responding = False
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
                    log.info("Gemini Live oturumu kuruldu. Model: %s.", self.model)
                    if self._handle:
                        log.debug("Önceki Gemini oturumu sürdürüldü.")
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
                status = getattr(
                    getattr(exc, "response", None), "status_code", None
                )
                stale_resume = not established and bool(self._handle)
                protocol_close = (
                    isinstance(exc, ConnectionClosed) and exc.code in (1007, 1008)
                )
                setup_failure = (
                    not established
                    and (
                        isinstance(exc, RuntimeError)
                        or status in (400, 401, 403, 404)
                        or protocol_close
                    )
                )
                # Retrying a negotiated 1007 audio-protocol failure in a tight
                # loop only reproduces the same server rejection and floods the
                # microphone queue.  Stop the session and show one actionable
                # error; a later restart/model change can recover cleanly.
                if (established and (protocol_close or _is_audio_protocol_error(exc))) or (
                    setup_failure and not stale_resume
                ):
                    raise
                self._error(exc)
                # A stale resumption token may be rejected; retry once as a fresh session.
                if stale_resume:
                    self._handle = None
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
                await asyncio.wait_for(
                    self._send(
                        {
                            "realtimeInput": {
                                "audio": {
                                    "mimeType": "audio/pcm;rate=16000",
                                    "data": base64.b64encode(pcm).decode(),
                                }
                            }
                        }
                    ),
                    config.AUDIO_SEND_TIMEOUT,
                )

    async def _receiver(self, ws):
        async for raw in ws:
            message = json.loads(raw)
            await self._handle_message(message)
            if "goAway" in message:
                log.info("Gemini oturumu yenileniyor.")
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
            now = time.monotonic()
            log_interrupt = (
                now - self._last_interrupt_at
                >= config.INTERRUPT_LOG_DEDUP_MS / 1000.0
            )
            self._last_interrupt_at = now
            self._discard_until_turn_end = True
            self._model_responding = False
            self._assistant_turn_open = False
            self._tool_response_pending = False
            self._awaiting_user_input = True
            self._clear_audio()
            self._cancel_tools()
            if log_interrupt:
                log.info("Kullanıcı araya girdi; yanıt ve bekleyen işlemler durduruldu.")
        transcript = content.get("inputTranscription", {}).get("text")
        if transcript:
            self._user_input_serial += 1
            self._assistant_turn_open = True
            self._tool_response_pending = False
            self._discard_until_turn_end = False
            if self._awaiting_user_input:
                self._last_action_input_serial = self._user_input_serial - 1
                self._awaiting_user_input = False
            self._last_input_at = time.monotonic()
            self._emit(self.on_text, "Sen", transcript)
            log.debug("Kullanıcı transkripti: %s", transcript.replace("\n", " ")[:240])
        transcript = content.get("outputTranscription", {}).get("text")
        # Standby/wake feedback (bekleme cümlesi) STANDBY'de de duyulsun — _feedback_until penceresi
        is_feedback_window = time.monotonic() < self._feedback_until
        if (
            transcript
            and (self.state == AKTIF or is_feedback_window)
            and not self.mic_muted
            and self._assistant_turn_open
            and not self._discard_until_turn_end
        ):
            self._emit(self.on_text, "Kyros", transcript)
        if transcript and self._tool_response_pending:
            # The first model output after a tool response belongs to the
            # same user turn.  Once it starts, the next turnComplete closes
            # the response gate again.
            self._tool_response_pending = False
        if not self._discard_until_turn_end:
            for part in content.get("modelTurn", {}).get("parts", []):
                data = part.get("inlineData", {})
                if (
                    data.get("mimeType", "").startswith("audio/pcm")
                    and (self.state == AKTIF or is_feedback_window)
                    and not self.mic_muted
                    and self._assistant_turn_open
                ):
                    if self._tool_response_pending:
                        self._tool_response_pending = False
                    if not self._model_responding:
                        self._model_responding = True
                    if self.audio:
                        self.audio.feed(base64.b64decode(data["data"]))
                    if self._last_input_at is not None:
                        log.debug(
                            "Yanıt sesinin ilk gecikmesi: %.0f ms",
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
                action = args.get("action")
                # A model may continue a completed turn by itself.  Wake is
                # allowed to recover the initial standby session, but standby
                # and stop must be attached to a fresh user turn; otherwise
                # they would make the assistant "talk to itself" or sleep
                # after an unrelated task.
                fresh_user_turn = (
                    self._assistant_turn_open
                    and self._user_input_serial > self._last_session_control_serial
                )
                if action in ("standby", "stop") and (
                    not fresh_user_turn
                    or self._user_input_serial <= self._last_action_input_serial
                ):
                    result = {
                        "ok": False,
                        "ignored": True,
                        "error": "Ignored session control; wait for an explicit user request.",
                    }
                    stopped_batch = True
                    self._assistant_turn_open = False
                    self._tool_response_pending = False
                    self._discard_until_turn_end = True
                    self._clear_audio()
                    log.debug(
                        "İzinsiz oturum kontrolü yok sayıldı: %s (yeni kullanıcı turu yok).",
                        action,
                    )
                else:
                    result = await self._control(action)
                    self._last_session_control_serial = self._user_input_serial
                    stopped_batch = action in ("stop", "standby")
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
                self._last_action_input_serial = self._user_input_serial
                task = asyncio.create_task(self._run_tool(call, self._epoch))
                self._tasks[call_id] = task
                task.add_done_callback(
                    lambda done, call=call: self._tool_done(call, done)
                )
                self._refresh()
        if content.get("turnComplete"):
            self._discard_until_turn_end = False
            self._model_responding = False
            if not self._tasks and not self._tool_response_pending:
                self._assistant_turn_open = False
                self._awaiting_user_input = True

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
            self._assistant_turn_open = True
            # Wake feedback ("Efendim, sizi dinliyorum") 1.8s boyunca kesilmesin
            self._feedback_until = time.monotonic() + 1.8
        elif action == "standby":
            # Bekleme cümlesi ÖNCE söylendi (protokolde), sonra standby çağrılır.
            # O cümleyi kesmemek için discard/clear yapma — sadece araçları iptal et.
            self.state = STANDBY
            self._assistant_turn_open = True
            self._feedback_until = time.monotonic() + 1.5
            self._cancel_tools()
        elif action == "stop":
            self.state = AKTIF
            self._assistant_turn_open = False
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
            label = TOOL_LABELS.get(name, name.replace("_", " ").title())
            elapsed = time.monotonic() - started
            if result.get("cancelled"):
                tool_log.warning("İptal edildi: %s (%.1f sn).", label, elapsed)
            elif result.get("ok"):
                tool_log.info("Tamamlandı: %s (%.1f sn).", label, elapsed)
            else:
                detail = (
                    result.get("error")
                    or result.get("detail")
                    or result.get("stderr")
                    or "tool returned ok=false"
                )
                tool_log.error(
                    "Başarısız: %s [%s] (%.1f sn): %s",
                    label,
                    str(call_id)[:80],
                    elapsed,
                    str(detail).replace("\n", " ")[:320],
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

    async def _respond(self, call, result, *, silent=False):
        response = dict(result)
        function_response = {
            "id": call.get("id", ""),
            "name": call.get("name", ""),
            "response": response,
        }
        if (
            call.get("name") != "session_control"
            and "gemini-3.1" not in str(self.model).lower()
        ):
            function_response["scheduling"] = (
                "SILENT"
                if silent
                or result.get("cancelled")
                or result.get("ignored")
                or self.state != AKTIF
                else "WHEN_IDLE"
            )
        if not silent and not result.get("ignored"):
            self._assistant_turn_open = True
            self._tool_response_pending = True
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
            self._user_input_serial += 1
            self._assistant_turn_open = True
            self._tool_response_pending = False
            self._awaiting_user_input = False
            self._last_action_input_serial = self._user_input_serial - 1
            self._discard_until_turn_end = False
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
