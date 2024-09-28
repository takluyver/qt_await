from PyQt5 import QtCore

from .core import SignalQueue

def sleep(ms):
    timer = QtCore.QTimer()
    timer.setSingleShot(True)
    sq = SignalQueue(timer.timeout)
    timer.start(ms)
    return sq

async def sleep_loop(ms):
    timer = QtCore.QTimer()
    sq = SignalQueue(timer.timeout)
    timer.start(ms)
    while True:
        await sq
        # If the timer is firing faster than we wait for it, discard excess signals
        sq.signals_q.clear()
        yield

async def with_timeout(waitable, timeout_ms):
    timer = QtCore.QTimer()
    timer.setSingleShot(True)
    timeout_q = SignalQueue(timer.timeout)
    timer.start(timeout_ms)
    sig_obj = await one_of(waitable, timeout_q)
    if sig_obj.sender is timer:
        raise TimeoutError(timeout_ms)
    return sig_obj

def run_process(qproc: QtCore.QProcess, program=None, arguments=None):
    sq = SignalQueue(qproc.finished)
    if program is not None:
        qproc.start(program, arguments)
    else:
        qproc.start()
    return sq
