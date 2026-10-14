"""The child's resource limits: a limit the system refuses must not stop the conversion."""

import resource

import pytest

from app import sandbox


class FakeResource:
    """Records setrlimit calls; refuses the address-space cap as macOS does."""

    RLIMIT_AS = resource.RLIMIT_AS
    RLIMIT_CPU = resource.RLIMIT_CPU
    RLIM_INFINITY = resource.RLIM_INFINITY

    def __init__(self, hard=None, refuse_as=False):
        self.hard = {} if hard is None else hard
        self.refuse_as = refuse_as
        self.calls = []

    def getrlimit(self, which):
        return (self.RLIM_INFINITY, self.hard.get(which, self.RLIM_INFINITY))

    def setrlimit(self, which, limits):
        if which == self.RLIMIT_AS and self.refuse_as:
            raise ValueError("current limit exceeds maximum limit")
        self.calls.append((which, limits))


@pytest.fixture
def fake(monkeypatch):
    def install(**kwargs):
        module = FakeResource(**kwargs)
        monkeypatch.setitem(__import__("sys").modules, "resource", module)
        return module

    return install


def test_refused_memory_cap_still_limits_cpu(fake, monkeypatch):
    monkeypatch.setattr(sandbox.sys, "platform", "linux")
    module = fake(refuse_as=True)
    sandbox._limit_resources(2048, 120)  # must not raise
    assert module.calls == [(FakeResource.RLIMIT_CPU, (120, 125))]


def test_macos_skips_the_memory_cap(fake, monkeypatch):
    monkeypatch.setattr(sandbox.sys, "platform", "darwin")
    module = fake(refuse_as=True)
    sandbox._limit_resources(2048, 120)
    assert module.calls == [(FakeResource.RLIMIT_CPU, (120, 125))]


def test_limits_never_ask_above_the_hard_limit(fake, monkeypatch):
    monkeypatch.setattr(sandbox.sys, "platform", "linux")
    module = fake(hard={FakeResource.RLIMIT_AS: 1024 * 1024 * 1024, FakeResource.RLIMIT_CPU: 60})
    sandbox._limit_resources(2048, 120)
    assert module.calls == [
        (FakeResource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024)),
        (FakeResource.RLIMIT_CPU, (60, 60)),
    ]


def test_linux_applies_both_limits(fake, monkeypatch):
    monkeypatch.setattr(sandbox.sys, "platform", "linux")
    module = fake()
    sandbox._limit_resources(2048, 120)
    assert module.calls == [
        (FakeResource.RLIMIT_AS, (2048 * 1024 * 1024, 2048 * 1024 * 1024)),
        (FakeResource.RLIMIT_CPU, (120, 125)),
    ]


def _network_after_isolation(conn):
    """In a child: give up what the conversion never needs, then try the network."""
    import socket

    unshared = sandbox._isolate()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            sock.connect(("1.1.1.1", 80))
        reached = True
    except OSError:
        reached = False
    conn.send((unshared, reached))
    conn.close()


@pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="Linux namespaces")
def test_the_child_has_no_network_on_linux():
    """A parser bug exploited by a crafted PDF finds no network to reach (where the system
    allows user namespaces; elsewhere the resource limits still hold)."""
    receiver, sender = sandbox._CTX.Pipe(duplex=False)
    process = sandbox._CTX.Process(target=_network_after_isolation, args=(sender,))
    process.start()
    sender.close()
    unshared, reached = receiver.recv()
    process.join()
    if not unshared:
        pytest.skip("this system refuses unprivileged user namespaces")
    assert reached is False


def test_on_macos_the_parent_stops_a_child_that_uses_too_much_memory(monkeypatch):
    """macOS enforces no memory limit inside the child: the parent watches its memory."""
    import sys
    import time

    from app.converter import ConversionError, ConversionOptions

    def slow_worker(conn, pdfs, options, memory_mb, job, cpu_seconds, lang="pt"):
        time.sleep(30)

    monkeypatch.setattr(sandbox, "_worker", slow_worker)
    monkeypatch.setattr(sandbox, "_CTX", sandbox.mp.get_context("fork"))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sandbox, "_rss_mb", lambda pid: 5000.0)
    started = time.monotonic()
    with pytest.raises(ConversionError, match="memória|memory"):
        sandbox.run_isolated(b"x", ConversionOptions(), timeout_s=20, memory_mb=1024)
    assert time.monotonic() - started < 5


def test_rss_is_read_from_ps():
    import os

    rss = sandbox._rss_mb(os.getpid())
    assert rss is not None and rss > 1
