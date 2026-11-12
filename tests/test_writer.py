"""Writer client tests: synthesis against a fake OpenAI-compatible server.

Run from the repo root: python3 tests/test_writer.py
"""

import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from miner.write import WriterError, synthesize, write_draft

_FIELDS = {
    "handler_id": "sub_growth",
    "criteria": "Subscriber growth report request.",
    "patterns": ["(growth|report).{0,20}(subscribers)"],
    "must_match": ["subscriber growth report"],
    "must_miss": ["send the report to mom"],
    "run_body": 'raise ValueError("draft not implemented")',
}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        body = {"choices": [{"message": {"content": json.dumps(_FIELDS)}}]}
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass


def _fake_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_synthesize_and_write():
    server = _fake_server()
    try:
        candidate = {"text": "subscriber growth report", "count": 2,
                     "tools": [{"name": "stats", "arg_keys": []}], "result": "table"}
        fields = synthesize(candidate, base_url=f"http://127.0.0.1:{server.server_port}/v1",
                            model="test-model", timeout=10.0)
        assert fields["handler_id"] == "sub_growth"
        with tempfile.TemporaryDirectory() as tmp:
            path = write_draft(candidate, fields, drafts_dir=tmp)
            assert path is not None and path.name == "sub_growth.py"
            text = path.read_text(encoding="utf-8")
            assert 'HANDLER_ID = "sub_growth"' in text
            assert "raise ValueError" in text
            assert write_draft(candidate, fields, drafts_dir=tmp) is None  # no overwrite
    finally:
        server.shutdown()


def test_writer_failure_is_typed():
    try:
        synthesize({"text": "x", "count": 2, "tools": [], "result": ""},
                   base_url="http://127.0.0.1:1/v1", model="m", timeout=2.0)
    except WriterError:
        pass
    else:
        raise AssertionError("expected WriterError")


if __name__ == "__main__":
    test_synthesize_and_write()
    test_writer_failure_is_typed()
    print("OK: writer")
