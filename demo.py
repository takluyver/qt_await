from PyQt5 import QtCore, QtWidgets, QtGui

from qt_await import (
    connect_async, start_async, with_timeout, sleep_loop, run_process
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
        self.write_cursor.insertText(text)
        vsb = self.output.verticalScrollBar()
        vsb.setValue(vsb.maximum())  # Scroll to end

    async def run_process(self):
        proc = QtCore.QProcess(self)
        await run_process(proc, "date", [])
        out_s = bytes(proc.readAllStandardOutput()).decode()
        self.write_output(f"date output: {out_s}")

        proc = QtCore.QProcess(self)
        ec, _ = await with_timeout(run_process(proc, "sleep", ["2"]), 5000)
        self.write_output(f"sleep exited with {ec}")

    async def count_up(self):
        async for _ in sleep_loop(1000):
            v = self.counter_sb.value()
            self.counter_sb.setValue(v + 1)

if __name__=="__main__":
    qapp = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    qapp.exec()
