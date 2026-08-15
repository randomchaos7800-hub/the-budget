"""Stdlib HTTP server. No dependencies."""

from __future__ import annotations

import json
import os
import posixpath
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .service import Wallet

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DEFAULT_DB = Path(os.environ.get("BUDGET_DB", ROOT / "data" / "budget.db"))
DEFAULT_HOST = os.environ.get("BUDGET_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("BUDGET_PORT", "8787"))


class Handler(SimpleHTTPRequestHandler):
    wallet: Wallet

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        sys_stderr = __import__("sys").stderr
        print(f"[budget] {self.address_string()} {fmt % args}", file=sys_stderr)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/api/state":
            scenario = (query.get("scenario") or [None])[0]
            days = int((query.get("days") or [0])[0] or 0) or None
            return self._json(self.wallet.dashboard(scenario, days))
        if path == "/api/history":
            return self._json(self.wallet.history())
        if path == "/api/scenarios":
            return self._json(self.wallet.scenarios())
        if path == "/api/export":
            return self._json(self.wallet.export())
        if path == "/api/health":
            return self._json({"ok": True})
        if path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        body = self._body()
        try:
            if path == "/api/templates":
                return self._json(self.wallet.save_template(body), 201)
            if path.startswith("/api/templates/") and path.endswith("/delete"):
                self.wallet.delete_template(path.split("/")[3])
                return self._json({"ok": True})
            if path == "/api/plan":
                self.wallet.set_plan(body["template_id"], body["date"], body["status"])
                return self._json({"ok": True})
            if path == "/api/plan/clear":
                return self._json({"cleared": self.wallet.clear_plan()})
            if path == "/api/plan/reset":
                return self._json({"cleared": self.wallet.reset_plan()})
            if path == "/api/balance":
                amount = self.wallet.set_balance(float(body["amount"]), body.get("date"))
                return self._json({"balance": amount})
            if path == "/api/ledger":
                return self._json(self.wallet.add_ledger(body), 201)
            if path == "/api/import":
                text = body.get("csv") or ""
                if not text:
                    return self._error(400, "csv field required")
                return self._json(self.wallet.import_csv(text))
            if path.startswith("/api/proposals/") and path.endswith("/accept"):
                return self._json(self.wallet.accept_proposal(path.split("/")[3]))
            if path.startswith("/api/proposals/") and path.endswith("/reject"):
                self.wallet.reject_proposal(path.split("/")[3])
                return self._json({"ok": True})
            if path == "/api/goals":
                return self._json(self.wallet.save_goal(body), 201)
            if path.startswith("/api/goals/") and path.endswith("/delete"):
                self.wallet.delete_goal(path.split("/")[3])
                return self._json({"ok": True})
            if path == "/api/settings":
                return self._json(self.wallet.update_settings(body))
            if path == "/api/nightly":
                return self._json(self.wallet.nightly())
            if path.startswith("/api/alerts/") and path.endswith("/ack"):
                self.wallet.ack_alert(path.split("/")[3])
                return self._json({"ok": True})
        except KeyError as exc:
            return self._error(404, str(exc))
        except (ValueError, TypeError) as exc:
            return self._error(400, str(exc))
        return self._error(404, f"no route {path}")

    def translate_path(self, path: str) -> str:
        path = posixpath.normpath(urlparse(path).path)
        if path.startswith("/api/"):
            return str(WEB / "index.html")
        return super().translate_path(path)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        ctype = self.headers.get("Content-Type", "")
        if "application/json" in ctype:
            return json.loads(raw.decode("utf-8"))
        if "text/csv" in ctype or "text/plain" in ctype:
            return {"csv": raw.decode("utf-8")}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {"csv": raw.decode("utf-8")}

    def _json(self, payload, status: int = 200) -> None:
        data = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message}, status)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, db: Path = DEFAULT_DB) -> None:
    Handler.wallet = Wallet(db)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"the budget → http://{host}:{port}  db={db}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
        server.server_close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="the budget")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()
    serve(args.host, args.port, Path(args.db))


if __name__ == "__main__":
    main()
