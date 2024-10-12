from PyQt5 import QtCore

from .core import SignalQueue, Cancelled


def sleep(ms):
    """Wait for ms (milliseconds) to elapse"""
    timer = QtCore.QTimer()
    timer.setSingleShot(True)
    sq = SignalQueue(timer.timeout, max_buffer_size=1)
    timer.start(ms)
    return sq

async def sleep_loop(ms):
    """Use ``async for _ in sleep_loop(ms):`` to wake up at regular intervals

    If the code in the loop takes longer than the timer interval, the next
    iteration will start straight away, but it won't try to catch up with a backlog.
    """
    timer = QtCore.QTimer()
    sq = SignalQueue(timer.timeout, max_buffer_size=1)
    timer.start(ms)
    while True:
        await sq
        yield

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
    try:
        sig = await sq
    except Cancelled:
        qproc.terminate()
        raise

    if sig.signal == qproc.errorOccurred:
        raise RuntimeError(f"QProcess failed with error {sig.args[0]}")
    return sig
