import inspect
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

class Result:
    def unwrap(self):
        raise NotImplementedError

    def send(self, coro):
        raise NotImplementedError

class Value(Result):
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return f"Value({self.value!r})"

    def unwrap(self):
        return self.value

    def send(self, coro):
        return coro.send(self.value)

class Error(Result):
    def __init__(self, exc):
        self.exc = exc

    def __repr__(self):
        return f"Error({self.exc!r})"

    def unwrap(self):
        raise self.exc

    def send(self, coro):
        return coro.throw(self.exc)

class Task:
    _result = None

    def __init__(self, inner_coro):
        self.inner_coro = inner_coro
        self.waiters = {}  # coroutines waiting for this

    def __await__(self):
        if self._result is None:
            yield self

        return self._result.unwrap()

    def done(self):
        return self._result is not None

    def set(self, res: Result):
        self._result = res
        if self.waiters:
            k = next(iter(self.waiters))
            coro = self.waiters.pop(k)
            res.send(coro)

    def result(self):
        return self._result.unwrap()

class SignalPlumbing(QtCore.QObject):
    """Internal machinery, created once per thread"""
    _thread_insts = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.waiting = {}  # id(coro): tuple(things that can wake it up)
        self.tasks = {}  # id(coro): Task

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
        self.tasks[id(coro)] = t = Task(coro)
        self.waiting[id(coro)] = ()
        self.step_coro(coro, Value(None))
        return t

    def step_coro(self, coro, result: Result):
        # Unhook the coroutine from anything else it was waiting for
        for catcher in self.waiting.pop(id(coro)):
            catcher.waiters.pop(id(coro), None)

        # Run the next step
        try:
            catchers = result.send(coro)
        except StopIteration as si:
            # This coroutine has finished normally
            task = self.tasks.pop(id(coro))
            self.task_finished(task, Value(si.value))
            return
        except BaseException as e:
            # This coroutine errored out
            task = self.tasks.pop(id(coro))
            self.task_finished(task, Error(e))
            # TODO: show traceback for top-level tasks?
            return

        # Hook up what it's waiting for to continue
        for catcher in catchers:
            if isinstance(catcher, (Task, SignalQueue)):
                catcher.waiters[id(coro)] = coro
            else:
                raise TypeError(f"Unexpected {type(catcher)}")

        self.waiting[id(coro)] = catchers

    def task_finished(self, task: Task, result: Result):
        for waiter in task.waiters.values():
            QtCore.QTimer.singleShot(0, lambda: self.step_coro(waiter, result))


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
            SignalPlumbing.forCurrentThread().step_coro(coro, Value(sig_obj))
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
            elif inspect.iscoroutine(obj):
                task = SignalPlumbing.forCurrentThread().start_coro(obj)
                catchers.append(task)
            else:
                raise TypeError(str(type(obj)))
        self.catchers = tuple(catchers)

    def __await__(self):
        for catcher in self.catchers:
            if isinstance(catcher, SignalQueue):
                if catcher.signals_q:
                    return catcher.signals_q.popleft()
            else: # Task
                if catcher.done():
                    return catcher.result()

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
