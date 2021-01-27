import os
import sys
import threading
import queue
import time
import subprocess

import numpy as np  # pip install numpy
import cv2  # pip install OpenCV-python

from PyQt5.QtWidgets import *  # pip install PyQt5
from PyQt5.QtGui import *
from PyQt5.QtCore import *

# Local imports
script_path_file = __file__
script_path = os.path.dirname(script_path_file)
sys.path.append(script_path)
from gui_tools import GuiMessagebox
from gui_tools import GuiStyling


LIVE_STREAM_FRAME_INTERVAL_TIME = 20  # milliseconds
APPLICATION_CLOSE_DOWN_TIMEOUT = 5  # seconds

APPLICATION_ICON = "photo_camera_icon.png"


class PhotoCapture:

    def __init__(self, camera_name, camera_name_suffix, configuration, camera_gui_frame_width, photo_file):

        camera_live_view_name = camera_name + camera_name_suffix
        data_to_gui = queue.Queue()  # Thread safe data packets transfer to gui
        data_from_gui = queue.Queue()  # Thread safe data packets transfer from gui
        camera = _LiveCamera(data_to_gui, data_from_gui)
        data_from_gui.put({"SETTINGS": {"NAME": camera_name, "CONFIG": configuration}})
        data_from_gui.put("START")
        app = QApplication(sys.argv)
        _ = _Window(app, camera_live_view_name, camera_gui_frame_width, data_to_gui, data_from_gui, camera, photo_file)
        # sys.exit(app.exec())  # does not work with ACQUA
        app.exec()


class _Window(QMainWindow):

    def __init__(self, app, camera_live_view_name, camera_gui_frame_width, data_to_gui, data_from_gui, camera, file):
        super().__init__()  # call QWidget constructor
        self.data_to_gui = data_to_gui
        self.data_from_gui = data_from_gui
        self.camera = camera
        self._forced_close = False
        self._take_photo_flag = True
        self._show_photo = False
        self._photo = None
        GuiStyling(app)
        self._photo_file = file
        self._first_camera_frame = True
        self._first_update_after_first_camera_frame = False

        self.setWindowTitle("Photo Capture")
        self.setWindowIcon(QIcon(APPLICATION_ICON))
        self.setWindowFlags(Qt.Window | Qt.MSWindowsFixedSizeDialogHint)

        self.statusBar().setSizeGripEnabled(False)
        GuiStyling.set_style(self, "statusBar")


        self.buttons = {}
        self._ui_layout(title=camera_live_view_name)
        self.show()
        self.camera_gui_frame_width = camera_gui_frame_width
        self.camera_frame_timer = QTimer()
        self.camera_frame_timer.timeout.connect(self._camera_frame_update)
        self.camera_resolution = 0, 0
        self._camera_resolution_change = True
        self.camera_frame_timer.start(int(LIVE_STREAM_FRAME_INTERVAL_TIME/5))

    def closeEvent(self, event):
        do_exit = True
        if not self._forced_close:
            answer = GuiMessagebox.yes_no("NO PHOTO CAPTURED", question="No photo saved.\n\nDo you want to quit anyway?")
            if answer == "no":
                do_exit = False
        if do_exit:
            self.data_from_gui.put("QUIT")
            timeout = APPLICATION_CLOSE_DOWN_TIMEOUT
            close_event = self.camera.thread_has_ended
            GuiMessagebox.until("CLOSING PHOTO CAPTURE APPLICATION", timeout=timeout, event=close_event, delay=0.5)
        else:
            event.ignore()

    def _ui_layout(self, title):
        self.layout_main = QHBoxLayout()

        self._layout_camera_main(self.layout_main, title)
        self._layout_control_buttons(self.layout_main)

        widget_main = QWidget()
        widget_main.setLayout(self.layout_main)
        self.setCentralWidget(widget_main)

    def _layout_camera_main(self, master, title):
        layout_camera_main = QVBoxLayout()

        label_camera_title = QLabel(title, self)
        GuiStyling.set_style(label_camera_title, "QLabel", "group")
        layout_camera_main.addWidget(label_camera_title)

        self._label_cam = QLabel("", self)
        layout_camera_main.addWidget(self._label_cam)

        master.addLayout(layout_camera_main)

    def _layout_control_buttons(self, master):
        layout_controls = QVBoxLayout()
        self._button_take_photo = self._add_push_button(layout_controls, "Take Photo", "blue")
        self._button_take_photo.setEnabled(False)
        self._button_save_photo = self._add_push_button(layout_controls, "Save Photo", "green")
        self._button_save_photo.setEnabled(False)
        self._button_live_view = self._add_push_button(layout_controls, "Discard Photo", "yellow")
        self._button_live_view.setEnabled(False)
        self._button_reconnect = self._add_push_button(layout_controls, "Re-connect Camera", "utility button")
        self._button_reconnect.setEnabled(False)
        self._add_push_button(layout_controls, "IP Camera Utility", "utility button")
        master.addLayout(layout_controls)

    def _camera_frame_update(self):

        if self._first_update_after_first_camera_frame:  # Update window when widgets are finally update
            # Center window on desktop: https://pythonprogramminglanguage.com/pyqt5-center-window
            qt_rectangle = self.frameGeometry()
            center_point = QDesktopWidget().availableGeometry().center()
            qt_rectangle.moveCenter(center_point)
            self.move(qt_rectangle.topLeft())
            self._first_update_after_first_camera_frame = False

        if not self.data_to_gui.empty():  # if data to gui arrived
            image_frame = None
            busy = True
            video_frame = False

            ## while not self.data_to_gui.empty():
            input_data = self.data_to_gui.get_nowait()
            if "VIDEO FRAME" in input_data:
                image_frame = input_data["VIDEO FRAME"]
                video_frame = True
            elif "TEXT FRAME" in input_data:
                image_frame = input_data["TEXT FRAME"]
            if "BUSY" in input_data:
                busy = input_data["BUSY"]

            ## button_id = self._get_widget_id(self.buttons, "Re-connect Camera")
            ## button_id.setEnabled(not busy)
            self._button_reconnect.setEnabled(not busy)

            if self._show_photo:
                self._button_save_photo.setEnabled(True)
                self._button_live_view.setEnabled(True)
            else:
                self._button_save_photo.setEnabled(False)
                if image_frame is not None:
                    height, width, channel = image_frame.shape
                    step = channel * width
                    qt_image = QImage(image_frame.data, width, height, step, QImage.Format_RGB888)
                    self._photo = qt_image
                    qt_image_scaled = qt_image.scaled(self.camera_gui_frame_width, 64000, Qt.KeepAspectRatio)
                    self._label_cam.setPixmap(QPixmap.fromImage(qt_image_scaled))
                    if self._first_camera_frame:
                        self._first_camera_frame = False
                        self._first_update_after_first_camera_frame = True
                if video_frame:
                    if self._take_photo_flag:
                        self._take_photo_flag = False
                        print("Taking Photo")
                        self._show_photo = True
                    else:
                        self._button_take_photo.setEnabled(True)
                else:
                    self._button_take_photo.setEnabled(False)
                    height, width = 0, 0
                if self.camera_resolution[0] != width or self.camera_resolution[1] != height:
                    self._camera_resolution_change = True
                    self.camera_resolution = width, height
                if self._camera_resolution_change:
                    self._camera_resolution_change = False
                    if not video_frame:
                        status = "Camera Disconnected"
                    else:
                        status = "Camera Resolution (width x height): %i x %i" % (self.camera_resolution[0], self.camera_resolution[1])
                    print(status)
                    self.statusBar().showMessage(status)

                    # Auto resize parent chain of camera view label
                    widget = self._label_cam.parent()
                    while widget:
                        widget.adjustSize()
                        widget = widget.parent()

    def _add_push_button(self, layout, button_text, style="default"):
        button = QPushButton(button_text, self)
        self.buttons[str(button)] = {"name": button_text, "id": button}
        GuiStyling.set_style(button, "QPushButton", style)
        button.clicked.connect(self._button_pushed)
        layout.addWidget(button)
        return button

    def _button_pushed(self):
        button_id = self.sender()
        button_id_str = str(button_id)
        button = self.buttons[button_id_str]
        button_name = button["name"]
        if button_name == "IP Camera Utility":
            app = "IPUtility.exe"
            print("Executing %s" % app)
            subprocess.Popen([app], shell=True, creationflags=subprocess.SW_HIDE)
            ## os.startfile(app)
        elif button_name == "Re-connect Camera":
            button_id.setEnabled(False)
            self.data_from_gui.put(["STOP", "START"])
        elif button_name == "Take Photo":
            button_id.setEnabled(False)
            self._button_live_view.setEnabled(True)
            self._take_photo_flag = True
        elif button_name == "Discard Photo":
            self._show_photo = False
            self._button_live_view.setEnabled(False)
        elif button_name == "Save Photo":
            do_exit = True
            image_saved = self._photo.save(self._photo_file)
            if not image_saved:
                question = "Failed to save photo to file:\n%s\n\nDo you want to quit anyway?" % self._photo_file
                answer = GuiMessagebox.yes_no("COULD NOT SAVE PHOTO", question=question)
                if answer == "no":
                    do_exit = False
            if do_exit:
                self._forced_close = True
                self.close()

    def _get_widget_id(self, widget_collection, widget_name):
        widget_id = None
        for widget_id_str in widget_collection:
            widget = widget_collection[widget_id_str]
            if widget_name == widget["name"]:
                widget_id = widget["id"]
                break
        return widget_id


class _LiveCamera:

    def __init__(self, data_to_gui, data_from_gui):
        self.thread_ended = False
        self.quit = False
        self.capture = None
        self.data_to_gui = data_to_gui
        self.data_from_gui = data_from_gui
        self.frame_width_error = 1200
        self.frame_aspect_ratio = 16/9  # Just a temporary value until first frame has been captured
        thread_target = self._camera_thread
        thread_name = __class__.__name__ + "." + thread_target.__name__
        self.camera_thread = threading.Thread(target=thread_target, name=thread_name)
        self.camera_thread.setDaemon(True)  # stop thread when script exits
        self.camera_thread.start()

    def thread_has_ended(self):
        return self.thread_ended

    def _settings(self, settings):
        self.camera = settings["CONFIG"]

    def _start(self):
        if "IP" in self.camera:
            self.stream = self.camera["Protocol"] + self.camera["Username"] + ":" + self.camera["Password"]
            self.stream += "@" + self.camera["IP"] + self.camera["Path"]
        else:
            self.stream = self.camera["USB ID"]
        print("Connecting to camera: %s" % self.stream)
        if "USB ID" in self.camera:
            self.capture = cv2.VideoCapture(self.stream, cv2.CAP_DSHOW)
        else:
            self.capture = cv2.VideoCapture(self.stream)
        return self.capture

    def _stop(self):
        if self.capture is not None:
            # self.data_to_gui.put({"CONNECTED": False})
            print("Disconnecting Camera")
            try:
                self.capture.release()
            except:
                print("ERROR: Could not disconnect from camera")

    def _camera_thread(self):
        camera_running = False
        while not self.quit: # loop until the script is terminated
            if not self.data_from_gui.empty(): # if data from gui arrived
                input_data = self.data_from_gui.get_nowait()
                if "QUIT" in input_data:
                    camera_running = False
                    self._stop()
                    self.quit = True
                if "STOP" in input_data:
                    self._image_text("DISCONNECTING CAMERA", True)
                    camera_running = False
                    self._stop()
                if "START" in input_data:
                    self._image_text("CONNECTING TO CAMERA", True)
                    capture = self._start()
                    camera_running = True
                    camera_connecting = True
                if "SETTINGS" in input_data:
                    settings = input_data["SETTINGS"]
                    self._settings(settings)
            else:
                time.sleep(int(LIVE_STREAM_FRAME_INTERVAL_TIME/1000))
            if camera_running:
                status_ok, image = capture.read()
                if status_ok:
                    frame_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                    height, width, channel = frame_image.shape
                    self.frame_aspect_ratio = width / height
                    self.data_to_gui.put({"VIDEO FRAME": frame_image, "BUSY": False})
                else:
                    if camera_connecting:
                        self._image_text("COULD NOT CONNECT TO CAMERA", False)
                    else:
                        self._image_text("LOST CONNECTION TO CAMERA", False)
                    camera_running = False
                    self._stop()
                if camera_connecting:
                    camera_connecting = False
        print("Camera Thread Loop Ended")
        self.thread_ended = True

    def _image_text(self, text, busy):
        width = self.frame_width_error
        height = int(width / self.frame_aspect_ratio)
        text_image = np.zeros((height, width, 3), np.uint8)  # Black frame
        font = cv2.FONT_HERSHEY_SIMPLEX
        org = (20, int(height/2))
        font_scale = (width / 960)
        color = (255, 255, 0)  # Yellow
        thickness = 2
        text_image = cv2.putText(text_image, text, org, font, font_scale, color, thickness, cv2.LINE_AA)
        self.data_to_gui.put({"TEXT FRAME": text_image, "BUSY": busy})


if __name__ == '__main__':

    # Camera configurations (Axis cameras: https://www.ispyconnect.com/man.aspx?n=axis)
    # Example: rtsp://root:Axis2020@192.168.10.171/axis-media/media.amp
    CAMERA_TEST_CONFIGURATIONS = \
        {
            "Axis IP Camera":
                {
                    "IP": "192.168.10.171",  # IP Camera
                    "Username": "root",
                    "Password": "Axis2020",
                    "Protocol": "rtsp://",
                    "Path": "/axis-media/media.amp"
                },
            "USB Camera":
                {
                    "USB ID": 0  # Web Camera connected to USB (or Laptop internal)
                },
        }
    CAMERA_TEST_NAME_SUFFIX = " Camera #1"
    CAMERA_TEST_GUI_FRAME_WIDTH = 1200  # This is the resolution on PC monitor (not the photo resolution)

    configuration = CAMERA_TEST_CONFIGURATIONS["Axis IP Camera"]
    photo_file = "photo.png"
    camera_location = "Kitchen"
    PhotoCapture(camera_location, CAMERA_TEST_NAME_SUFFIX, configuration, CAMERA_TEST_GUI_FRAME_WIDTH, photo_file)
