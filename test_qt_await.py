import time

import pytest
from pytestqt.qt_compat import qt_api

from qt_await import start_async, sleep

@pytest.fixture(scope="session")
def qapp_cls():
   return qt_api.QtCore.QCoreApplication

def test_sleep(qtbot):
    async def sleep_eg(cb):
        t0 = time.perf_counter()
        await sleep(ms=500)
        t1 = time.perf_counter()
        cb(t1 - t0)

    with qtbot.waitCallback(timeout=2000) as cb:
        start_async(sleep_eg(cb))

    assert 0.4 < cb.args[0] < 0.6

