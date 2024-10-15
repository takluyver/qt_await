import codecs

from qtpy import QtCore

from .core import SignalQueue, Cancelled


async def sleep(ms):
    """Wait for ms (milliseconds) to elapse"""
    timer = QtCore.QTimer()
    timer.setSingleShot(True)
    sq = SignalQueue(timer.timeout, max_buffer_size=1)
    timer.start(ms)
    await sq

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

async def read_streaming_bytes(dev: QtCore.QIODevice, maxSize=4096):
    """Read bytes from a QIODevice as they're reaady

    This is used with an 'async for' loop, yielding bytes objects.
    """
    sig_q = SignalQueue(dev.readyRead, dev.readChannelFinished)
    finished = False
    while True:
        while b := dev.read(maxSize):
            yield b

        if finished:
            return

        sig = await sig_q
        if sig.signal == dev.readChannelFinished:
            # There might still be buffered data to read
            finished = True

async def read_streaming_text(dev, maxSize=4096, encoding='utf-8', errors='strict'):
    """Read data from a QIODevice as it's ready and decode it to strings

    This is used with an 'async for' loop, yielding str objects.
    """
    inc_decoder = codecs.getincrementaldecoder(encoding)(errors=errors)
    async for b in read_streaming_bytes(dev, maxSize):
        yield inc_decoder.decode(b)

    if s := inc_decoder.decode(b'', final=True):
        yield s
