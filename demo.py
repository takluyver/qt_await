import time

from PyQt5 import QtCore, QtNetwork, QtWidgets, QtGui

from qt_await import (
    connect_async, start_async, with_timeout, sleep_loop, run_process, SignalQueue
)

class MainWindow(QtWidgets.QMainWindow):
    bridge_client = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        frame = QtWidgets.QFrame()
        hbox = QtWidgets.QHBoxLayout()
        frame.setLayout(hbox)
        self.setCentralWidget(frame)

        buttons_vbox = QtWidgets.QVBoxLayout()
        hbox.addLayout(buttons_vbox)

        button_proc = QtWidgets.QPushButton("QProcess")
        buttons_vbox.addWidget(button_proc)
        connect_async(button_proc.clicked, self.run_process)

        button_http = QtWidgets.QPushButton("HTTP request")
        buttons_vbox.addWidget(button_http)
        connect_async(button_http.clicked, self.http_request)

        self.counter_sb = QtWidgets.QSpinBox()
        start_async(self.count_up())
        buttons_vbox.addWidget(self.counter_sb)

        self.output = QtWidgets.QPlainTextEdit()
        self.output.document().setDefaultFont(QtGui.QFont("monospace"))
        self.output.setReadOnly(True)
        self.write_cursor = self.output.textCursor()
        hbox.addWidget(self.output)

    def write_output(self, text):
        self.write_cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        self.write_cursor.insertText(text + '\n')
        vsb = self.output.verticalScrollBar()
        vsb.setValue(vsb.maximum())  # Scroll to end

    async def run_process(self):
        proc = QtCore.QProcess(self)
        await run_process(proc, "date", [])
        out_s = bytes(proc.readAllStandardOutput()).decode().strip()
        self.write_output(f"date output: {out_s}")

        proc = QtCore.QProcess(self)
        ec, _ = await with_timeout(run_process(proc, "sleep", ["2"]), 5000)
        self.write_output(f"sleep exited with {ec}")

    async def http_request(self):
        mgr = QtNetwork.QNetworkAccessManager()
        req = QtNetwork.QNetworkRequest(QtCore.QUrl("https://pypi.org/"))
        reply = mgr.get(req)

        t0 = time.perf_counter()
        await SignalQueue(reply.finished)
        t1 = time.perf_counter()

        status = reply.attribute(QtNetwork.QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        content_type = reply.header(QtNetwork.QNetworkRequest.KnownHeaders.ContentTypeHeader)
        self.write_output(f"HTTP response {status} in {t1 - t0:.3f}s")
        self.write_output(f"  mime type {content_type}")

    async def count_up(self):
        async for _ in sleep_loop(1000):
            v = self.counter_sb.value()
            self.counter_sb.setValue(v + 1)

if __name__=="__main__":
    qapp = QtWidgets.QApplication([])
    window = MainWindow()
    window.resize(700, 400)
    window.show()
    qapp.exec()
