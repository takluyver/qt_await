from PyQt5 import QtCore

from .core import one_of, SignalQueue


def sleep(ms):
    """Wait for ms (milliseconds) to elapse"""
    timer = QtCore.QTimer()
    timer.setSingleShot(True)
    sq = SignalQueue(timer.timeout)
    timer.start(ms)
    return sq

async def sleep_loop(ms):
    """Use ``async for _ in sleep_loop(ms):`` to wake up at regular intervals

    If the code in the loop takes longer than the timer interval, the next
    iteration will start straight away, but it won't try to catch up with a backlog.
    """
    timer = QtCore.QTimer()
    sq = SignalQueue(timer.timeout)
    timer.start(ms)
    while True:
        await sq
        # If the timer is firing faster than we wait for it, discard excess signals
        sq.signals_q.clear()
        yield

async def with_timeout(waitable, timeout_ms):
    """Raise TimeoutError if something isn't ready in timeout_ms."""
    timer = QtCore.QTimer()
    timer.setSingleShot(True)
    timeout_q = SignalQueue(timer.timeout)
    timer.start(timeout_ms)
    sig_obj = await one_of(waitable, timeout_q)
    if sig_obj.sender is timer:
        raise TimeoutError(timeout_ms)
    return sig_obj

async def run_process(qproc: QtCore.QProcess, program=None, arguments=None):
    """Start a QProcess and wait for it to finish

    Like QProcess.start(), the executable & arguments can be passed in, or
    set beforehand (``.setProgram()`` & ``.setArguments()``).
    """
    sq = SignalQueue(qproc.finished, qproc.errorOccurred)
    if program is not None:
        qproc.start(program, arguments)
    else:
        qproc.start()
    sig = await sq
    if sig.signal == qproc.errorOccurred:
        raise RuntimeError(f"QProcess failed with error {sig.args[0]}")
    return sig
