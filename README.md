# pyDeskREC - Screen Recorder Utility


### Description:


pyDeskREC is a screen recording utility with a graphical user interface built in Python using PySimpleGUI.


### Functions:


  Select the screen area to be recorded.

  Set recording parameters such as FPS, duration, start/end time, and countdown.

  Record system audio and microphone.

  View the webcam.

  Manage settings such as audio/video devices, display settings, etc.



### Main Features:


  Video recording in MP4 or MKV format using FFmpeg.

  Persistent configuration via ini file for audio, video, fps, and video save folder.

  Customizable countdown before recording starts.

  Scheduled start and stop of recording based on system time or specified duration.

  Support for system audio and microphone recording.

  Dynamic display selection for multi-monitor configurations.



### Prerequisites:


  Python 3.x

  PySimpleGUI (for the graphical user interface)

  OpenCV (for webcam management)

  FFmpeg (for screen recording and audio)

  v4l2-ctl (for webcam management)



### Installation:

     pip install PySimpleGUI pyautogui opencv-python numpy


If you want the unsubscribed version of PySimpleGUI, use this command: 

     python -m pip install PySimpleGUI==4.60.5.0

Make sure FFmpeg is installed, for example, with


     sudo apt-get install ffmpeg

### Usage:

  Run 

    python3 RegisterScreen.py 

  to start the application.

  Configure the recording options via the GUI.

  Use the “Select Area” button to choose the part of the screen to record. (Otherwise it will record full screen).

  If you want to set the various timers

  Press “Start Recording” to start video capture.

### Screenshots:
eng:
![alt text](https://github.com/MoonDragon-MD/pyDeskREC/blob/main/img/Screenshot-eng.jpg?raw=true)

ita:
![alt text](https://github.com/MoonDragon-MD/pyDeskREC/blob/main/img/Screenshot.jpg?raw=true)

### Notes:

Some features, such as the transparency of the area selection window, may not work on all operating systems or desktop environments.

To record audio, make sure pulseaudio or another FFmpeg-compatible audio system is in use. (If so, modify the program to suit your own).

The mkv format in case the program freezes or the pc closes prematurely allows you to see the video recorded up to that moment, the mp4 format does not, it must be stopped with the appropriate button.

The time format is 24-hour

### Known issues:

If the end time is set, when it finishes recording it may give this error “RuntimeError: Calling Tcl from different apartment” but the file is still saved, I will fix it as soon as I can.
