# ABOUTME: Hermetic tests for worker-browser recovery (no Chrome, no network).
# ABOUTME: A worker whose browser window was closed or crashed must start a fresh browser instead of failing forever.

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402


class DeadSession(Exception):
    """Stands in for selenium's NoSuchWindowException / 'chrome not reachable'."""


class FakeBrowser:
    instances: list = []

    def __init__(self, headless=False, **_):
        self.alive = False
        self.stopped = False
        self.calls = 0
        self.die_during_next_call = False
        FakeBrowser.instances.append(self)

    def start(self):
        self.alive = True
        return self

    def stop(self):
        self.stopped = True
        self.alive = False

    def is_alive(self):
        return self.alive

    def get_product(self, part_number):
        self.calls += 1
        if self.die_during_next_call:
            self.die_during_next_call = False
            self.alive = False
        if not self.alive:
            raise DeadSession("no such window: target window already closed")
        return f"product {part_number} from browser {FakeBrowser.instances.index(self)}"


@pytest.fixture
def fake(monkeypatch):
    FakeBrowser.instances = []
    monkeypatch.setattr(server, "McMasterBrowser", FakeBrowser)
    monkeypatch.setattr(server, "_local", threading.local())
    monkeypatch.setattr(server, "_browsers", [])
    return FakeBrowser


def on_one_worker(*steps):
    """Run the steps in one fresh thread (the worker pool's thread-local browser) and return their results."""
    out = []

    def run():
        for step in steps:
            try:
                out.append(step())
            except Exception as e:  # noqa: BLE001 - the test inspects it
                out.append(e)

    t = threading.Thread(target=run)
    t.start()
    t.join(10)
    return out


def test_closed_window_gets_a_fresh_browser(fake):
    def close_window():
        fake.instances[0].alive = False

    first, _, second = on_one_worker(
        lambda: server._get_product_sync("47865K23"),
        close_window,
        lambda: server._get_product_sync("47865K23"),
    )
    assert first == "product 47865K23 from browser 0"
    assert second == "product 47865K23 from browser 1", second
    assert fake.instances[0].stopped
    assert server._browsers == [fake.instances[1]]


def test_browser_dying_mid_call_is_retried_once_on_a_fresh_browser(fake):
    def die_next():
        fake.instances[0].die_during_next_call = True

    _, _, result = on_one_worker(
        lambda: server._get_product_sync("1"),
        die_next,
        lambda: server._get_product_sync("2"),
    )
    assert result == "product 2 from browser 1", result
    assert len(fake.instances) == 2


def test_error_from_a_live_browser_is_not_retried(fake):
    def boom(part_number):
        raise ValueError("spec table not found")

    def break_page():
        fake.instances[0].get_product = boom

    _, _, result = on_one_worker(
        lambda: server._get_product_sync("1"),
        break_page,
        lambda: server._get_product_sync("2"),
    )
    assert isinstance(result, ValueError)
    assert len(fake.instances) == 1 and not fake.instances[0].stopped
