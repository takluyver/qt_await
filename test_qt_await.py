import sys
import time

import pytest
from pytestqt.qt_compat import qt_api
QtCore = qt_api.QtCore

from qt_await import start_async, sleep, with_timeout, run_process, read_streaming_text

@pytest.fixture(scope="session")
def qapp_cls():
   return QtCore.QCoreApplication

def test_sleep(qtbot):
    async def sleep_eg(cb):
        t0 = time.perf_counter()
        await sleep(ms=500)
        t1 = time.perf_counter()
        cb(t1 - t0)

    with qtbot.waitCallback(timeout=2000) as cb:
        start_async(sleep_eg(cb))

    assert 0.4 < cb.args[0] < 0.6


def test_with_timeout(qtbot):
    async def timeout_eg_1(cb):
        t0 = time.perf_counter()
        try:
            await with_timeout(sleep(ms=200), timeout_ms=500)
            err = False
        except TimeoutError as e:
            err = True
        t1 = time.perf_counter()
        cb(err, t1 - t0)

    with qtbot.waitCallback(timeout=2000) as cb:
        start_async(timeout_eg_1(cb))

    assert cb.args[0] is False
    assert 0.1 < cb.args[1] < 0.3

    async def timeout_eg_2(cb):
        t0 = time.perf_counter()
        try:
            await with_timeout(sleep(ms=500), timeout_ms=200)
            err = False
        except TimeoutError as e:
            err = True
        t1 = time.perf_counter()
        cb(err, t1 - t0)

    with qtbot.waitCallback(timeout=2000) as cb:
        start_async(timeout_eg_2(cb))

    assert cb.args[0] is True
    assert 0.1 < cb.args[1] < 0.3


def test_run_process(qtbot):
    async def proc_eg(cb):
        qp = QtCore.QProcess()
        await run_process(qp, sys.executable, ['-c', 'print(6 * 7)'])
        cb(bytes(qp.readAllStandardOutput()))

    with qtbot.waitCallback(timeout=2000) as cb:
        start_async(proc_eg(cb))

    assert cb.args[0].strip() == b'42'


def test_read_streaming_text(qtbot, qapp):
    async def streaming_eg(cb):
        qp = QtCore.QProcess(qapp)
        qp.setProcessChannelMode(QtCore.QProcess.ForwardedErrorChannel)
        qp.start(sys.executable)
        qp.write(b'import time\nfor i in range(5):\n  print(i, flush=True)\n  time.sleep(0.1)')
        qp.closeWriteChannel()
        pieces = []
        async for s in read_streaming_text(qp):
            pieces.append(s.strip())
        qp.deleteLater()
        cb(pieces)

    with qtbot.waitCallback(timeout=2000) as cb:
        start_async(streaming_eg(cb))

    assert cb.args[0] == ['0', '1', '2', '3', '4']
