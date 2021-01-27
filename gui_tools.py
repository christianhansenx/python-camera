import time
import threading

from PyQt5.QtWidgets import *  # pip install PyQt5
from PyQt5.QtGui import *
from PyQt5.QtCore import *


class GuiMessagebox:

    @staticmethod
    def until(*args, **kwargs):
        message_box_type = "until"
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
            _DummyWindow(app, message_box_type, *args, **kwargs)
        else:
            _MessageWindow(message_box_type, *args, **kwargs)

    @staticmethod
    def yes_no(*args, **kwargs):
        message_box_type = "yes_no"
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
            dummy_window = _DummyWindow(app, message_box_type, *args, **kwargs)
            message_window_pointer = dummy_window.message_window_pointer
        else:
            message_window_pointer = _MessageWindow(message_box_type, *args, **kwargs)
        return message_window_pointer.answer


GUI_STYLES = \
    {
        "statusBar default": {"": {"font": "bold", "color": "gray", "font-size": "24px"}},
        "QGroupBox default": {"": {"border": "2px solid blue"}},
        "QLabel default": {"": {"font-size": "16px"}},
        "QLabel group": {"": {"font-size": "32px", "color": "blue"}},
        "QLabel attention": {"": {"font-size": "42px", "font": "bold", "color": "orange", "padding": "4px"}},
        "QLabel messagebox": {"": {"font-size": "42px", "font": "bold", "color": "white", "background-color": "blue"}},
        "QPushButton default": {
            "": {"font-size": "32px", "font": "bold", "padding": "6px", "background-color": "lightgray"},
            ":hover": {"background-color": "white"}, ":pressed": {"background-color": "gray"}},
        "QPushButton utility button": {"": {"font-size": "18px"}},
        "QPushButton blue": {"": {"background-color": "lightblue"}},
        "QPushButton green": {"": {"background-color": "lightgreen"}},
        "QPushButton yellow": {"": {"background-color": "lightyellow"}},
    }


class GuiStyling:

    def __init__(self, app):
        app.setStyle("Windows") # https://build-system.fman.io/pyqt5-tutorial

    @staticmethod
    def set_style(widget, style_name, style="default"):
        style_collection = {}
        style_names = [style_name + " default"]
        if style != "default":
            style_names.append(style_name + " " + style)
        for full_style_name in style_names:
            for style_list_name in GUI_STYLES[full_style_name]:
                if not style_list_name in style_collection:
                    style_collection[style_list_name] = {}
                style_list = GUI_STYLES[full_style_name][style_list_name]
                style_collection[style_list_name].update(style_list)
        style_string = ""
        for style_list_name in style_collection:
            style_string += style_name + style_list_name + "{"
            for style_set_name in style_collection[style_list_name]:
                style_value = style_collection[style_list_name][style_set_name]
                style_string += " " + style_set_name + ":" + style_value + ";"
            style_string += " }  "
        if style_name == "statusBar":
            # Get style string inside {...}
            _, style_string = style_string.split("{")
            style_string, _ = style_string.split("}")

            widget.statusBar().setStyleSheet(style_string)
        else:
            widget.setStyleSheet(style_string)


class _MessageWindow(QDialog):

    def __init__(self, message_box_type, msg, timeout=0, event=None, function=None, delay=0, question="",
                 default_answer=QMessageBox.No):
        super().__init__()

        # https://pythonspot.com/pyqt5-messagebox
        if message_box_type == "yes_no":
            button_reply = QMessageBox.question(self, msg, question, QMessageBox.Yes | QMessageBox.No, default_answer)
            if button_reply == QMessageBox.Yes:
                self._answer = "yes"
            else:
                self._answer = "no"
            ## self.show()

        else:
            self.setWindowFlag(Qt.FramelessWindowHint, True)
            self.setStyleSheet("background-color: black;")
            self.setFixedHeight(900)
            self.setFixedWidth(1600)
            label = QLabel(msg, self)
            label.setAlignment(Qt.AlignCenter)
            GuiStyling.set_style(label, "QLabel", "messagebox")
            self.layout = QVBoxLayout()
            self.layout.addWidget(label)
            self.setLayout(self.layout)
            self.timeout = timeout
            self.timeout_time = time.monotonic() + timeout
            self.close_event = event
            self.function_completed = False
            self.run_function = False
            if function is not None:
                self._start_function(function)
            self.delay = int(delay * 1000)
            self.message_end = QTimer()
            self.message_end.timeout.connect(self._check_close_event)
            self.message_end.start(self.delay)
            self.exec_()

    @property
    def answer(self):
        return self._answer

    def _start_function(self, function):
        thread_target = self._function_thread
        thread_name = __class__.__name__ + "." + thread_target.__name__
        self._function_thread = threading.Thread(target=thread_target, name=thread_name, args=(function,))
        self._function_thread.setDaemon(True)  # Stop thread when script exits
        self._function_thread.start()

    def _function_thread(self, function):
        while not self.run_function:
            time.sleep(0.1)
        function()
        self.function_completed = True

    def _check_close_event(self):
        if self.delay == 0:
            if not self.run_function:
                self.run_function = True
            if self.function_completed:
                self.close()
            if self.close_event is not None:
                if self.close_event():
                    self.close()
            if self.timeout > 0 and time.monotonic() >= self.timeout_time:
                self.close()
        else:
            self.message_end.stop()
            self.message_end.start(200)
            self.delay = 0


class _DummyWindow(QMainWindow):  # Qt5 main application if no Qt5 framework not already running

    def __init__(self, app, *args, **kwargs):
        super().__init__()  # call QWidget constructor
        self.message_window_pointer = _MessageWindow(*args, **kwargs)


if __name__ == '__main__':

    def dummy_event():
        return False

    def dummy():
        print("function start")
        time.sleep(3)
        print("function end")
        return False

    def main():
        GuiMessagebox.until("CLOSING APPLICATION", timeout=1, event=dummy_event, delay=0)
        print(GuiMessagebox.yes_no("ASK A QUESTION", question="Do you want to answer?"))

    main()
