"""Small JSON-line client for Codex app-server verification probes."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


class AppServerError(RuntimeError):
    """Raised when the Codex app-server JSON protocol cannot complete."""


class CodexAppServerClient:
    """Minimal newline-delimited JSON client for ``codex app-server``."""

    def __init__(self, command: list[str], cwd: Path) -> None:
        self._stdout: queue.Queue[str | None] = queue.Queue()
        self._stderr_lines: list[str] = []
        self._notifications: list[dict[str, Any]] = []
        self._protocol_noise: list[str] = []
        self._next_id = 1
        self._proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    @property
    def notifications(self) -> list[dict[str, Any]]:
        return list(self._notifications)

    @property
    def protocol_noise(self) -> list[str]:
        return list(self._protocol_noise)

    @property
    def stderr_tail(self) -> str:
        return "".join(self._stderr_lines)[-4000:]

    def _read_stdout(self) -> None:
        assert self._proc.stdout is not None
        try:
            for line in self._proc.stdout:
                self._stdout.put(line)
        finally:
            self._stdout.put(None)

    def _read_stderr(self) -> None:
        assert self._proc.stderr is not None
        for line in self._proc.stderr:
            self._stderr_lines.append(line)
            if len(self._stderr_lines) > 200:
                self._stderr_lines = self._stderr_lines[-200:]

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 60.0,
        raise_on_error: bool = True,
    ) -> dict[str, Any]:
        if self._proc.poll() is not None:
            raise AppServerError(
                f"codex app-server exited before {method}: {self._proc.returncode}"
            )
        request_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        assert self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._proc.stdin.flush()

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"timed out waiting for {method}")
            try:
                raw_response = self._stdout.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                if self._proc.poll() is not None:
                    raise AppServerError(
                        "codex app-server exited while waiting for "
                        f"{method}: {self._proc.returncode}"
                    ) from None
                continue
            if raw_response is None:
                raise AppServerError(f"codex app-server closed stdout while waiting for {method}")
            try:
                response = json.loads(raw_response)
            except json.JSONDecodeError:
                self._protocol_noise.append(raw_response[:240])
                if len(self._protocol_noise) > 20:
                    self._protocol_noise = self._protocol_noise[-20:]
                continue
            if response.get("id") != request_id:
                self._notifications.append(response)
                continue
            if raise_on_error and response.get("error"):
                raise AppServerError(f"{method} failed: {response['error']}")
            return response

    def close(self) -> None:
        if self._proc.poll() is None:
            try:
                assert self._proc.stdin is not None
                self._proc.stdin.close()
            except (OSError, ValueError):
                pass
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)
