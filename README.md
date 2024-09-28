# qt-await

This lets you use Python's `async` & `await` syntax with PyQt or PySide
applications, to wait for Qt signals.

It *doesn't* integrate Qt with asyncio, trio, or code written for those
frameworks.

## Usage

To wait for arbitrary signals, wrap them in a `SignalQueue`.
For example, using the [`QProcess.finished`](https://doc.qt.io/qt-5/qprocess.html#finished)
signal:

```python
from PyQt5 import QtCore, QtWidgets
from qt_await import SignalQueue

class MainWindow(QtWidgets.QMainWindow):
    ...

    async def run_subprocess(self):
        proc = QtCore.QProcess()
        sq = SignalQueue(proc.finished)
        proc.start("sleep", ["2"])
        exit_code, exit_status = await sq
```

There are some helper functions to make common operations easier:

```python
# Pause for 1s (all times are ms, following Qt's convention)
await sleep(1000)

# Pause repeatedly
async for _  in sleep_loop(1000):
    ...

# Wait for something else, with a time limit (also in ms)
await with_timeout(..., 3000)

# Run a QProcess & wait for its finished signal
await run_process(proc, "sleep", ["2"])
```

All this code needs to be in `async def` functions, so there are two extra
functions to get from normal Qt code into async:

- `start_async(f())` starts an async function immediately.
- `connect_async(signal, f)` connects an async function to a PyQt signal, to
  start whenever the signal is emitted.

## Limitations

This is an experiment, which I mostly wrote for fun - use it at your own risk.

This doesn't integrate with asyncio (see [`qasync`](https://pypi.org/project/qasync/)
for that) or trio (see [`qtrio`](https://pypi.org/project/qtrio/#description)),
or any other Python async libraries. It assumes you're doing things the Qt way -
`QProcess` for subprocesses, `QThread` for threads, `QNetworkRequest` for HTTP,
and so on. It aims to fit in with these APIs as much as possible.

Another thing you might want is the [`qt-async-threads`](https://pypi.org/project/qt-async-threads/)
package, which lets you wrap arbitrary slow Python functions in a thread and
`await` their completion, to avoid blocking the event loop.
