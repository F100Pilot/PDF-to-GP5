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
