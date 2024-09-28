import types
from collections import deque
from functools import partial
from inspect import signature

from PyQt5 import QtCore

__all__ = [
    "ReceivedSignal",
    "SignalQueue",
    "one_of",
    "connect_async",
    "start_async"
]

class SignalPlumbing(QtCore.QObject):
    """Internal machinery, created once per thread"""
    _thread_insts = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.waiting = {}

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
            catcher.coro_q.pop(id(coro), None)

        # Run the next step
        try:
            catchers = coro.send(value)
        except StopIteration:
            # This coroutine has finished
            return

        # Hook up what it's waiting for to continue
        for catcher in catchers:
            if not isinstance(catcher, SignalQueue):
                raise TypeError(f"Unexpected {type(catcher)}")
            catcher.coro_q[id(coro)] = coro
        self.waiting[id(coro)] = catchers


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
    """
    def __init__(self, *signals):
        super().__init__()
        self.signals_q = deque()
        self.coro_q = {}
        for signal in signals:
            self.add(signal)

    def add(self, signal):
        signal.connect(partial(self.on_signal, signal))

    def on_signal(self, signal, *args):
        sig_obj = ReceivedSignal(self.sender(), signal, args)
        if self.coro_q:
            # Something is waiting for a signal - deliver it immediately
            k = next(iter(self.coro_q))
            coro = self.coro_q.pop(k)
            SignalPlumbing.forCurrentThread().step_coro(coro, sig_obj)
        else:
            # Nothing waiting, queue the signal until it's requested
            self.signals_q.append(sig_obj)

    def __await__(self):
        if self.signals_q:
            return self.signals_q.popleft()

        sig_obj = yield (self,)
        return sig_obj


class one_of:
    """Wait for a signal on any of the given SignalQueues"""
    def __init__(self, *waitables):
        catchers = []
        for obj in waitables:
            if isinstance(obj, one_of):
                catchers.extend(obj.catchers)
            elif isinstance(obj, SignalQueue):
                catchers.append(obj)
            else:
                raise TypeError(str(type(obj)))
        self.catchers = tuple(catchers)

    def __await__(self):
        for catcher in self.catchers:
            if catcher.signals_q:
                return catcher.signals_q.popleft()

        sig_obj = yield self.catchers
        return sig_obj


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
