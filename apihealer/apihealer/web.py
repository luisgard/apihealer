"""
APIHealer local web UI.

A single-command graphical front end over the same engine the CLI uses. Run:

    python -m apihealer.web

...and it opens a local page in your browser. Nothing leaves your machine; the
server only talks to the engine you already have.

Uses the standard library only (http.server) so there are no extra
dependencies. The page is served from here; the /api/run endpoint runs a
remediation and returns the structured result as JSON, which the page renders.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .adapters import select_adapter
from .adapters.base import ClientKind, FixContext
from .core import diff as diff_mod
from .core.contract_source import SwaggerSource
from .core.llm_providers import available_providers, get_provider
from .core.report import to_dict
from .core.snapshot_store import SnapshotStore

HOST = "127.0.0.1"
PORT = 8750


def _run_healer(payload: dict) -> dict:
    """Run one detection/remediation and return a JSON-able result dict."""
    path = (payload.get("path") or "").strip()
    url = (payload.get("swagger_url") or "").strip()
    name = (payload.get("name") or "").strip() or None
    apply = bool(payload.get("apply"))
    llm_name = (payload.get("llm") or "").strip() or None

    # --- validation, with friendly messages the UI shows directly ---
    if not diff_mod.oasdiff_installed():
        return {"ok": False, "stage": "setup",
                "message": "oasdiff isn't on your PATH. Install it, then reload."}
    if not path:
        return {"ok": False, "stage": "input", "message": "Choose the project folder."}
    project_root = Path(path).expanduser()
    if not project_root.is_dir():
        return {"ok": False, "stage": "input",
                "message": f"That folder doesn't exist: {project_root}"}
    if not url:
        return {"ok": False, "stage": "input", "message": "Enter the contract (Swagger) URL."}

    adapter = select_adapter(project_root)
    if adapter is None:
        return {"ok": False, "stage": "detect",
                "message": "No supported project found here. .NET is supported today."}

    classification = adapter.classify_client(project_root)
    store = SnapshotStore(project_root)
    api_key = store.resolve_key(name, url)

    baseline = store.baseline_path(api_key)
    incoming = store.api_dir(api_key) / "contract_incoming.json"

    try:
        SwaggerSource(url).fetch(incoming)
    except Exception as exc:
        return {"ok": False, "stage": "fetch",
                "message": f"Couldn't fetch the contract: {exc}"}

    diff = diff_mod.diff_contracts(baseline, incoming)

    base = {
        "ok": True,
        "project": str(project_root),
        "api_key": api_key,
        "client_kind": classification.kind.value,
        "client_reasons": classification.reasons,
    }

    if diff.first_run:
        store.write_baseline(api_key, incoming.read_bytes())
        incoming.unlink(missing_ok=True)
        base.update({"stage": "baseline",
                     "title": "Snapshot saved \u2014 nothing to repair yet",
                     "message": (
                         "This is the first time APIHealer sees this API, so it saved a "
                         "snapshot of the current contract as the baseline. There's nothing "
                         "to compare against yet. Run it again after the API changes, and "
                         "it will compare the new contract to this snapshot and repair what "
                         "breaks.")})
        return base

    if not diff.changed:
        incoming.unlink(missing_ok=True)
        base.update({"stage": "nochange",
                     "title": "No changes \u2014 nothing to do",
                     "message": (
                         "The API's contract is identical to the saved snapshot, so nothing "
                         "in your code is affected. APIHealer only acts when the contract "
                         "actually changes.")})
        return base

    if not diff.has_breaking:
        store.write_baseline(api_key, incoming.read_bytes())
        incoming.unlink(missing_ok=True)
        base.update({"stage": "nonbreaking",
                     "title": "Contract changed, but nothing breaking",
                     "message": (
                         "The contract changed, but only in ways that don't break your code "
                         "(for example, a new optional field). APIHealer updated the snapshot "
                         "and left your code untouched.")})
        return base

    # breaking changes -> remediate
    llm = get_provider(llm_name)
    result = adapter.propose_fix(FixContext(
        project_root=project_root,
        contract_new=incoming,
        breaking_changes=diff.breaking_report,
        llm=llm,
        apply=apply,
    ))

    if result.applied:
        store.write_baseline(api_key, incoming.read_bytes())
    incoming.unlink(missing_ok=True)

    base.update({
        "stage": "remediated",
        "breaking_report": diff.breaking_report,
        "had_llm": llm is not None,
        "result": to_dict(result),
    })
    return base


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = PAGE_HTML.encode("utf-8")
            self._send(200, html, "text/html; charset=utf-8")
        elif self.path == "/api/providers":
            body = json.dumps({"providers": available_providers()}).encode()
            self._send(200, body, "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path != "/api/run":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._send(400, b'{"ok":false,"message":"bad request"}', "application/json")
            return
        try:
            result = _run_healer(payload)
        except Exception as exc:
            result = {"ok": False, "stage": "error", "message": f"Unexpected error: {exc}"}
        body = json.dumps(result).encode("utf-8")
        self._send(200, body, "application/json")

    def log_message(self, *args):
        pass  # keep the console quiet


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/"
    print("=" * 56)
    print("  APIHealer  -  local web UI")
    print("=" * 56)
    print(f"  Open: {url}")
    print("  (Press Ctrl+C here to stop the server.)")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.shutdown()


# The page is defined in web_page.py to keep this file focused on the server.
from .web_page import PAGE_HTML  # noqa: E402


if __name__ == "__main__":
    main()
