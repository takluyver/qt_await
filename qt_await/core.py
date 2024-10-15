import inspect
import traceback
import types
from collections import deque
from functools import partial
from inspect import signature

from qtpy import QtCore

__all__ = [
    "ReceivedSignal",
    "SignalQueue",
    "with_timeout",
    "connect_async",
    "start_async"
]


class SignalPlumbing(QtCore.QObject):
    """Internal machinery, created once per thread"""
    _thread_insts = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.waiting = {}  # id(coro): tuple(things that can wake it up)

    @classmethod
    def forThread(cls, thread):
        # The id() of the main thread is inconsistent - I think this is specific
        # to the main thread because it's started outside Qt. So use a special
        # ID to find the thread-local instance of it for this class.
        if thread == QtCore.QCoreApplication.instance().thread():
            tid = "main"
        else:
            tid = id(thread)
        if tid not in cls._thread_insts:
            cls._thread_insts[tid] = SignalPlumbing()
        return cls._thread_insts[tid]

    @classmethod
    def forCurrentThread(cls):
        return cls.forThread(QtCore.QThread.currentThread())

    def start_coro(self, coro: types.CoroutineType):
        self.waiting[id(coro)] = ()
        self.step_coro(coro, None)

    def step_coro(self, coro, value):
        # Unhook the coroutine from anything else it was waiting for
        for catcher in self.waiting.pop(id(coro)):
            catcher.waiters.pop(id(coro), None)

        # Run the next step
        try:
            catchers = coro.send(value)
        except StopIteration:
            # This coroutine has finished normally
            return
        except BaseException as e:
            # This coroutine errored out
            print("Uncaught exception in", coro.__qualname__)
            traceback.print_exception(e)
            return

        # Hook up what it's waiting for to continue
        for catcher in catchers:
            if isinstance(catcher, SignalQueue):
                catcher.waiters[id(coro)] = coro
            else:
                raise TypeError(f"Unexpected {type(catcher)}")

        self.waiting[id(coro)] = catchers


class Cancelled(BaseException):
    """Raised inside tasks when they are cancelled by a timeout"""
    pass


class ReceivedSignal:
    """Received signal object - can be unpacked to the signal arguments"""
    def __init__(self, sender, signal, args):
        self.sender = sender
        self.signal = signal
        self.args = args

    def __len__(self):
        return len(self.args)

    def __getitem__(self, index):
        return self.args[index]

    def __iter__(self):
        return iter(self.args)


class SignalQueue(QtCore.QObject):
    """Capture emitted signals and return them via await

    ``await`` an instance of SignalQueue to get the next signal it captures.
    When a signal is ready, the caller gets back a ReceivedSignal object.

    By default the queue will keep any amount of signals that arrive before you
    await them. If max_buffer_size is set, new signals will replace older ones
    once the buffer fills up. Either way can be tricky.
    """
    def __init__(self, *signals, max_buffer_size=None):
        super().__init__()
        self.signals_q = deque(maxlen=max_buffer_size)
        self.waiters = {}
        for signal in signals:
            self.add(signal)

    def add(self, signal):
        signal.connect(partial(self.on_signal, signal))

    def on_signal(self, signal, *args):
        sig_obj = ReceivedSignal(self.sender(), signal, args)
        if self.waiters:
            # Something is waiting for a signal - deliver it immediately
            k = next(iter(self.waiters))
            coro = self.waiters.pop(k)
            SignalPlumbing.forCurrentThread().step_coro(coro, sig_obj)
        else:
            # Nothing waiting, queue the signal until it's requested
            self.signals_q.append(sig_obj)

    def __await__(self):
        if self.signals_q:
            return self.signals_q.popleft()

        sig_obj = yield (self,)
        return sig_obj


class with_timeout:
    """Run a coroutine with a time limit

    The timeout is specified in ms, following Qt conventions.
    If the timeout expires, TimeoutError is normally raised to the caller.
    In the inner coroutine, Cancelled is raised. If that triggers another
    exception, the caller will see that instead of TimeoutError.
    """
    def __init__(self, awaitable, timeout_ms):
        if inspect.iscoroutine(awaitable):
            self.coro = awaitable
        elif isinstance(awaitable, SignalQueue):
            self.coro = awaitable.__await__()
        else:
            raise TypeError(
                f"Expected coroutine or SignalQueue, not {type(awaitable)}"
            )
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(timeout_ms)

    def __await__(self):
        timeout_q = SignalQueue(self.timer.timeout)
        self.timer.start()

        signal = None  # To start coroutine

        while True:
            try:
                sig_qs = self.coro.send(signal)
            except StopIteration as si:
                # Coroutine finished successfully
                self.timer.stop()
                return si.value
            except:
                # Error in coroutine
                self.timer.stop()
                raise

            signal = yield (sig_qs + (timeout_q,))
            if signal.signal == self.timer.timeout:
                try:
                    self.coro.throw(Cancelled("Cancelled by timeout"))
                except (Cancelled, StopIteration):
                    pass
                raise TimeoutError(f"Timeout expired ({self.timer.interval()} ms)")


def connect_async(signal, async_slot):
    """Connect a Qt signal to an ``async def`` function slot"""
    nargs = len(signature(async_slot).parameters)
    slot_owner: QtCore.QObject = async_slot.__self__
    plumbing = SignalPlumbing.forThread(slot_owner.thread())

    def start_slot(*args):
        args = args[:nargs]
        coro = async_slot(*args)
        plumbing.start_coro(coro)

    signal.connect(start_slot)


def start_async(coro):
    """Start running an ``async def`` function with Qt"""
    return SignalPlumbing.forCurrentThread().start_coro(coro)
