"""Ephemeral PCM speech transport. Provider callbacks never log recognition content."""
from __future__ import annotations

import asyncio
import importlib
from typing import Any, Protocol


class SpeechStream(Protocol):
    events: asyncio.Queue[dict[str, Any]]

    async def start(self) -> None: ...
    async def write(self, pcm: bytes) -> None: ...
    async def finish(self) -> None: ...
    async def close(self) -> None: ...


class AzureSpeechStream:
    """Continuous Azure Speech recognition from signed 16-bit, 16 kHz mono PCM."""

    def __init__(self, *, key: str, region: str, locale: str) -> None:
        sdk = importlib.import_module("azure.cognitiveservices.speech")
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=128)
        self._loop = asyncio.get_running_loop()
        self._closed = False
        self._segment = 0
        self._seen: set[str] = set()
        self._ended = asyncio.Event()
        config = sdk.SpeechConfig(subscription=key, region=region)
        config.speech_recognition_language = locale
        self._input = sdk.audio.PushAudioInputStream(
            stream_format=sdk.audio.AudioStreamFormat(samples_per_second=16000, bits_per_sample=16, channels=1)
        )
        self._recognizer = sdk.SpeechRecognizer(
            speech_config=config, audio_config=sdk.audio.AudioConfig(stream=self._input)
        )
        self._recognizer.recognizing.connect(lambda event: self._schedule("partial", event.result))
        self._recognizer.recognized.connect(lambda event: self._schedule("final", event.result))
        self._recognizer.canceled.connect(lambda event: self._loop.call_soon_threadsafe(
            self._error if event.reason == sdk.CancellationReason.Error else self._ended.set))
        self._recognizer.session_stopped.connect(lambda _: self._loop.call_soon_threadsafe(self._ended.set))

    def _schedule(self, kind: str, result: Any) -> None:
        self._loop.call_soon_threadsafe(self._result, kind, str(result.result_id), str(result.text))

    def _result(self, kind: str, result_id: str, text: str) -> None:
        if self._closed or not text.strip() or result_id in self._seen:
            return
        event = {"type": kind, "segment": self._segment, "text": text.strip()[:8000]}
        if kind == "final":
            self._seen.add(result_id)
            self._segment += 1
        if self.events.full():
            self._error()
        else:
            self.events.put_nowait(event)

    def _error(self) -> None:
        if self._closed:
            return
        while not self.events.empty():
            self.events.get_nowait()
            self.events.task_done()
        self.events.put_nowait({"type": "error", "code": "provider_failed"})
        self._ended.set()

    async def start(self) -> None:
        await asyncio.to_thread(lambda: self._recognizer.start_continuous_recognition_async().get())

    async def write(self, pcm: bytes) -> None:
        self._input.write(pcm)

    async def finish(self) -> None:
        self._input.close()
        await asyncio.wait_for(self._ended.wait(), timeout=15)

    async def close(self) -> None:
        self._closed = True
        self._input.close()
        try:
            await asyncio.wait_for(
                asyncio.to_thread(lambda: self._recognizer.stop_continuous_recognition_async().get()), 5
            )
        finally:
            while not self.events.empty():
                self.events.get_nowait()
            self._seen.clear()
