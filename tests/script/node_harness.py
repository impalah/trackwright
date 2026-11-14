"""Drive the real MIDI Remote script under Node.js (``harness.js``): shared by the script tests.

Moved out of ``test_script_node.py`` (T-06) so that test modules do not import each other.
"""

from __future__ import annotations

import json
import select
import shutil
import subprocess
from pathlib import Path
from typing import Any

from trackwright import protocol
from trackwright.cubase import SCRIPT_PATH

NODE = shutil.which("node")
HARNESS = Path(__file__).with_name("harness.js")
STEP_TIMEOUT = 10.0
JsonObject = dict[str, Any]


class Harness:
    def __init__(self, script: Path = SCRIPT_PATH) -> None:
        assert NODE is not None
        self.proc = subprocess.Popen(
            [NODE, str(HARNESS), str(script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.sid = ""
        self._seq = 0
        self._rid = 0

    def step(self, **step: Any) -> JsonObject:
        assert self.proc.stdin is not None
        assert self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(step) + "\n")
        self.proc.stdin.flush()
        ready, _, _ = select.select([self.proc.stdout], [], [], STEP_TIMEOUT)  # T-05: never hang the suite
        assert ready, f"the Node harness did not answer in {STEP_TIMEOUT:g} s"
        line = self.proc.stdout.readline()
        assert line, self.proc.stderr.read() if self.proc.stderr else "harness died"
        reply: JsonObject = json.loads(line)
        return reply

    def frames_for(
        self, op: str, params: JsonObject | None = None, *, rid: str | None = None, sid: str | None = None
    ) -> list[list[int]]:
        self._rid += 1
        self._seq += 1
        request = protocol.make_request(op, rid or f"r{self._rid}", self.sid if sid is None else sid, params)
        return protocol.build_frames(protocol.encode_payload(request), self._seq)

    @staticmethod
    def decode(sent: list[list[int]]) -> list[JsonObject]:
        reassembler = protocol.Reassembler()
        messages = []
        for raw in sent:
            frame = protocol.parse_frame(raw)
            assert frame is not None, raw[:8]
            payload = reassembler.feed(frame)
            if payload is not None:
                messages.append(protocol.decode_payload(payload))
        return messages

    def call(self, op: str, params: JsonObject | None = None, **kw: Any) -> JsonObject:
        """Send a request, run idle ticks until it is answered, return the single response."""
        replies = self.decode(self.step(frames=self.frames_for(op, params, **kw))["sent"])
        ticks = 0
        while not replies and ticks < 5:
            replies = self.decode(self.step(idle=1)["sent"])
            ticks += 1
        assert len(replies) == 1, replies
        return replies[0]

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
        for stream in (self.proc.stdout, self.proc.stderr):  # TW-1415: no ResourceWarning for the pipes
            if stream:
                stream.close()
