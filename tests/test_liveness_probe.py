# ABOUTME: Hermetic tests for McMasterBrowser.is_alive() against a fake Chrome DevTools endpoint (no Chrome).
# ABOUTME: In UC/CDP mode WebDriver is disconnected on a healthy browser, so liveness must come from DevTools.

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import browser as browser_mod  # noqa: E402
from browser import McMasterBrowser  # noqa: E402


class FakeChrome:
    """Serves /json/version and /json/list like Chrome's remote-debugging port."""

    def __init__(self, browser_id="1111-aaaa", pages=1):
        self.browser_id = browser_id
        self.pages = pages
        chrome = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path == "/json/version":
                    body = {"Browser": "Chrome/158",
                            "webSocketDebuggerUrl": f"ws://127.0.0.1/devtools/browser/{chrome.browser_id}"}
                elif self.path == "/json/list":
                    body = [{"type": "page", "id": str(i)} for i in range(chrome.pages)]
                    body.append({"type": "service_worker", "id": "sw"})
                else:
                    self.send_error(404)
                    return
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.addr = f"127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class DisconnectedDriver:
    """A UC-mode driver after sb.open(): capabilities are cached, every WebDriver call is refused."""

    def __init__(self, addr):
        self.capabilities = {"goog:chromeOptions": {"debuggerAddress": addr}}

    @property
    def window_handles(self):
        raise ConnectionRefusedError("[WinError 10061] No connection could be made (chromedriver disconnected)")


class FakeSB:
    def __init__(self, addr):
        self.driver = DisconnectedDriver(addr)


def started_browser(addr, tmp_path):
    """A McMasterBrowser in the state start() leaves it, with SB replaced by a fake."""
    b = McMasterBrowser(headless=True, profile_dir=str(tmp_path))
    b._sb = FakeSB(addr)
    b._devtools_addr = browser_mod._debugger_address(b._sb)
    b._devtools_browser_id = browser_mod._devtools_browser_id(b._devtools_addr)
    return b


@pytest.fixture
def chrome():
    c = FakeChrome()
    yield c
    c.close()


def test_healthy_browser_with_disconnected_webdriver_is_alive(chrome, tmp_path):
    # The 2026-11-24 window_handles probe said False here and relaunched Chrome on every call.
    b = started_browser(chrome.addr, tmp_path)
    assert b._devtools_browser_id == "1111-aaaa"
    assert b.is_alive() is True


def test_crashed_or_closed_chrome_is_dead(chrome, tmp_path):
    b = started_browser(chrome.addr, tmp_path)
    chrome.close()  # Chrome exits when its last window closes: the debugging port refuses connections
    assert b.is_alive() is False


def test_chrome_with_no_open_page_is_dead(chrome, tmp_path):
    b = started_browser(chrome.addr, tmp_path)
    chrome.pages = 0
    assert b.is_alive() is False


def test_another_chrome_on_the_reused_port_is_not_mistaken_for_this_one(chrome, tmp_path):
    b = started_browser(chrome.addr, tmp_path)
    chrome.browser_id = "2222-bbbb"  # this Chrome died, another worker's Chrome took the port
    assert b.is_alive() is False


def test_unknown_debugger_address_keeps_the_old_behaviour(tmp_path):
    b = started_browser(None, tmp_path)
    assert b._devtools_addr is None
    assert b.is_alive() is True


def test_stopped_browser_is_not_alive(chrome, tmp_path):
    b = started_browser(chrome.addr, tmp_path)
    b._sb = None
    assert b.is_alive() is False


def test_probe_is_bounded_when_the_port_hangs(tmp_path, monkeypatch):
    import socket
    import time

    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)  # accepts, never answers
    addr = f"127.0.0.1:{srv.getsockname()[1]}"
    monkeypatch.setattr(browser_mod, "DEVTOOLS_TIMEOUT_S", 0.5)
    b = started_browser(None, tmp_path)
    b._devtools_addr, b._devtools_browser_id = addr, "1111-aaaa"
    t0 = time.monotonic()
    try:
        assert b.is_alive() is False
    finally:
        srv.close()
    assert time.monotonic() - t0 < 3
