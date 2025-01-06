import PySimpleGUI as sg
import tkinter as tk
import pyautogui
import cv2
import numpy as np
import os
from datetime import datetime, timedelta
import threading
import time
import subprocess
import queue
import configparser

CONFIG_FILE = "pyDeskREC.ini"

def load_config():
    config = configparser.ConfigParser()
    default_settings = {
        'audio_device': '',
        'video_device': '',
        'fps': '30',
        'output_folder': os.path.expanduser("~/Video"),
        'video_format': 'mp4',
        'area': '',
        'display': ''
    }

    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
        if not config.has_section('SETTINGS'):
            config['SETTINGS'] = default_settings
        else:
            # Aggiorna le Settings esistenti
            current_settings = dict(config['SETTINGS'])
            for key, value in default_settings.items():
                if key not in current_settings:
                    config['SETTINGS'][key] = value
        save_config(config)
    else:
        config['SETTINGS'] = default_settings
        save_config(config)

    # Carica le coordinate dell'area
    area_string = config['SETTINGS']['area']
    area = tuple(map(int, area_string.split(','))) if area_string else None

    # Carica display
    display_value = config['SETTINGS']['display']
    
    return config, area, display_value

def save_config(config):
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)

def get_video_devices():
    try:
        result = subprocess.run(['v4l2-ctl', '--list-devices'], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE, 
                              text=True)
        devices = result.stdout.split('\n')
        video_devices = [devices[i-1].strip() 
                        for i in range(1, len(devices)) 
                        if '/dev/video' in devices[i]]
        return video_devices
    except Exception as e:
        print(f"Error retrieving video devices: {e}")
        return []

def get_audio_sources():
    try:
        result = subprocess.run("pacmd list-sources | awk '/index:/ {print $0}; /name:/ {print $0}; /device\\.description/ {print $0}'", 
                              shell=True, 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE, 
                              text=True)
        sources = result.stdout.split('\n')
        audio_sources = [sources[i+1].strip().split("<")[1].strip(">").strip() 
                        for i in range(len(sources)) 
                        if "device.description" in sources[i]]
        return [source for source in audio_sources if "monitor" in source] or audio_sources
    except Exception as e:
        print(f"Error retrieving audio sources: {e}")
        return []

def check_ffmpeg_installed():
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE, 
                              text=True, 
                              timeout=5)
        if result.returncode != 0:
            sg.popup_error("FFmpeg is not installed or is not in the PATH.", keep_on_top=True)
            return False
        return True
    except Exception as e:
        sg.popup_error(f"Error verifying FFmpeg: {e}", keep_on_top=True)
        return False

config, area, display = load_config()  # Separate return values

if not config['SETTINGS']['audio_device'] or not config['SETTINGS']['video_device'] or not config['SETTINGS']['display']:
    sg.popup("At least one of the parameters (Audio Device, Video Device, Display) is not set. Go to Settings to configure them.", title="Required configuration", keep_on_top=True)
if not check_ffmpeg_installed():
    exit(1)
            
class ScreenRecorder:
    def __init__(self, error_queue):
        self.output_folder = config['SETTINGS']['output_folder']
        self.fps = int(config['SETTINGS']['fps'])
        self.duration_minutes = 0
        self.countdown_seconds = 0
        self.record_system_audio = True
        self.record_microphone = False
        self.recording = False
        self.is_waiting = False
        self.start_time = None
        self.end_time = None
        self.area = area  # Use the area loaded from the configuration file
        self.display = config['SETTINGS']['display']  # Use display from configuration file
        self.process = None
        self.record_thread = None
        self.error_queue = error_queue
        self.manual_audio_source = config['SETTINGS']['audio_device']
        self.manual_video_device = config['SETTINGS']['video_device']
        self.video_format = config['SETTINGS']['video_format']

    def get_display_value(self):
        # Check if the display value is already in the configuration file
        if self.display:
            return self.display

        try:
            result = subprocess.run(['sh', '-c', 'echo $DISPLAY'], 
                                    stdout=subprocess.PIPE, 
                                    stderr=subprocess.PIPE, 
                                    text=True, 
                                    check=True)
            display_value = result.stdout.strip()
            if display_value:
                print(f"Display found: {display_value}")
                self.config['SETTINGS']['display'] = display_value  # Save to configuration
                save_config(self.config)  # Save the new value
                return display_value
            else:
                print("No DISPLAY value found, using fallback ':0.0'.")
                self.config['SETTINGS']['display'] = ':0.0'  # Save fallback in configuration
                save_config(self.config)
                return ':0.0'
        except subprocess.CalledProcessError as e:
            print(f"Error executing command: {e}. Using fallback ':0.0'.")
            self.config['SETTINGS']['display'] = ':0.0'  # Save fallback in configuration
            save_config(self.config)
            return ':0.0'

    def choose_area(self):
        sg.popup("Select the area of ​​the screen to record.", keep_on_top=True)
    
        root = tk.Tk()
        root.overrideredirect(1)
        root.wait_visibility(root)
        try:
            root.wm_attributes("-alpha", 0.5)
        except tk.TclError:
            print("Transparency is not supported.")
        root.attributes('-topmost', True)
        root.geometry(f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}+0+0")

        canvas = tk.Canvas(root, cursor="crosshair", bg="black")
        canvas.pack(fill=tk.BOTH, expand=True)

        start_x, start_y = None, None
        rect = None

        def on_press(event):
            nonlocal start_x, start_y, rect
            start_x, start_y = event.x, event.y
            if rect:
                canvas.delete(rect)
            rect = canvas.create_rectangle(start_x, start_y, start_x, start_y, outline="red", width=2)

        def on_drag(event):
            if rect:
                canvas.coords(rect, start_x, start_y, event.x, event.y)

        def on_release(event):
            nonlocal start_x, start_y
            end_x, end_y = event.x, event.y
            root.quit()
            root.destroy()
    
            # Save area as offset and size
            self.area = (
                min(start_x, end_x), min(start_y, end_y),  # Offset (X, Y)
                abs(start_x - end_x), abs(start_y - end_y)  # Dimensions (width, height)
            )

            if self.area[2] > 0 and self.area[3] > 0:
                sg.popup(f"Selected area: {self.area}", keep_on_top=True)
                # Convert to string for saving
                area_string = ','.join(map(str, self.area))
                config['SETTINGS']['area'] = area_string
                save_config(config)
            else:
                self.area = None
                sg.popup("No area selected. Full screen recording.", keep_on_top=True)
                # Save the area in the configuration file
                area_string = ''
                config['SETTINGS']['area'] = area_string
                save_config(config)
                screen_size = pyautogui.size()
                self.area = (0, 0, screen_size.width, screen_size.height)

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)

        root.mainloop

    def setup_ffmpeg_command(self, output_file):
        try:
            # FFmpeg Basic Command
            cmd = [
                'ffmpeg',
                '-f', 'x11grab',              # Use X11 screen grab
                '-r', str(self.fps),          # FPS
                '-thread_queue_size', '4096'  # Increase the size of the queue
            ]

            # If area is specified, use coordinates
            if self.area:
                # Ensures that self.area is a tuple of integers
               if all(isinstance(val, int) for val in self.area):
                    offset_x, offset_y, width, height = self.area
               else:
                    # If not all values ​​are integers, use full screen
                    screen_size = pyautogui.size()
                    offset_x, offset_y, width, height = 0, 0, screen_size.width, screen_size.height
                    print(f"Area non valida, usando schermo intero: {offset_x}, {offset_y}, {width}, {height}")

                # Verify that the coordinates are correct (positive width and height)
               if width <= 0 or height <= 0:
                    raise ValueError("The selected area is invalid (width or height <= 0)")
        
                # Add area to ffmpeg  
               cmd.extend(['-video_size', f"{width}x{height}", '-i', f"{self.display}+{offset_x},{offset_y}"])
            else:
                # If the area is not defined, use full screen
                cmd.extend(['-i', f"{self.display}"])

            # Audio Management
            if self.record_system_audio:
                if self.manual_audio_source:
                    cmd.extend(['-f', 'pulse', '-i', self.manual_audio_source])
                else:
                    cmd.extend(['-f', 'pulse', '-i', 'default'])

            if self.record_microphone:
                cmd.extend(['-f', 'pulse', '-i', 'default'])

            # Codec configuration based on format
            if self.video_format == 'mkv':
                cmd.extend([
                    '-c:v', 'libx264',
                    '-preset', 'veryfast',
                    '-crf', '23',
                    '-maxrate', '1M',
                    '-bufsize', '2M',
                    '-pix_fmt', 'yuv420p',
                    '-g', '50',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-ac', '2',
                    '-ar', '44100'
                ])
            else:  # mp4
                cmd.extend([
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-movflags', '+faststart',
                    '-c:a', 'aac',
                    '-strict', 'experimental'
                ])

            # Add output file
            cmd.append(output_file)

            print(f"Generated FFmpeg command: {' '.join(cmd)}")  # Debug logging
            return cmd

        except Exception as e:
            print(f"Errore nella configurazione di FFmpeg: {e}")  # Debug logging
            raise

    def start_recording(self, start_time=None, end_time=None):
        print(f"Area corrente: {self.area}")  # Debug
        if self.is_waiting or self.recording:
            print("Registration already in progress or pending")  # Debug logging
            return

        if not self.area:
            # Read area from configuration file
            area_string = config['SETTINGS']['area']
            if area_string:
                self.area = tuple(map(int, area_string.split(',')))
            else:
                # If the area is empty, use full screen
                screen_size = pyautogui.size()
                self.area = (0, 0, screen_size.width, screen_size.height)
    
        print(f"Area selected for registration: {self.area}")  # Debug logging

        try:
            # Countdown
            if self.countdown_seconds > 0:
                self.countdown(self.countdown_seconds)
            
            # Ora di inizio
            if start_time:
                self.is_waiting = True
                delay = (start_time - datetime.now()).total_seconds()
                if delay > 0:
                    threading.Timer(delay, self._start_recording_now, args=(end_time,)).start()
                    return  # Come back soon, recording will start after the timer

            # Start recording if there is no start timer
            self._start_recording_now(end_time)

        except Exception as e:
            self.recording = False
            self.is_waiting = False
            error_msg = f"Error starting recording: {str(e)}"
            print(error_msg)  # Debug logging
            self.error_queue.put(error_msg)
            sg.popup_error(error_msg, keep_on_top=True)

    def _start_recording_now(self, end_time):
        try:
            if not os.path.exists(self.output_folder):
                os.makedirs(self.output_folder)
        
            now = datetime.now()
            extension = '.mkv' if self.video_format == 'mkv' else '.mp4'
            output_file = f"{self.output_folder}/registration_{now.strftime('%Y-%m-%d_%H-%M-%S')}{extension}"
    
            cmd = self.setup_ffmpeg_command(output_file)
            print(f"Executing the command: {' '.join(cmd)}")  # Debug logging
    
            self.recording = True
            self.is_waiting = False
            self.start_time = time.time()
    
            self.process = subprocess.Popen(cmd, 
                                          stdout=subprocess.PIPE, 
                                          stderr=subprocess.PIPE, 
                                          text=True)
        
            if self.process.poll() is not None:
                raise Exception("FFmpeg failed to start")
        
            self.record_thread = threading.Thread(target=self.wait_for_ffmpeg)
            self.record_thread.start()
            print(f"Registration thread started: {self.record_thread.is_alive()}")  # Debug    
            sg.popup_quick_message("Recording started", background_color='green', text_color='white')
    
            # Timer by duration or end time
            if self.duration_minutes > 0:
                threading.Timer(self.duration_minutes * 60, self.stop_recording).start()
            elif end_time:
                delay = (end_time - datetime.now()).total_seconds()
                if delay > 0:
                    threading.Timer(delay, self.stop_recording).start()

        except Exception as e:
            self.recording = False
            error_msg = f"Error starting recording: {str(e)}"
            print(error_msg)  # Debug logging
            self.error_queue.put(error_msg)
            sg.popup_error(error_msg, keep_on_top=True)

    def stop_recording(self):
        try:
            if self.process and self.recording:
                # If recording is in progress, stop it.
                print("Stopping the recording...")
                self.process.terminate()
                self.process.wait()
                self.recording = False
                self.is_waiting = False
                sg.popup("Registration finished.", keep_on_top=True)

            # Regardless of the registration status, reset the area
            self.area = None  # Reset dell'area
            config['SETTINGS']['area'] = ''  # Set the area to empty string in the config file
            save_config(config)

            print("Area reset.")
        except Exception as e:
            print(f"Error while resetting area: {e}")
            sg.popup_error(f"Error while resetting area: {e}")

    def countdown(self, seconds):
        for i in range(seconds, 0, -1):
            sg.popup_auto_close(f"Registration starts in {i} seconds...", 
                              auto_close_duration=1, keep_on_top=True)
            time.sleep(1)

    def wait_for_ffmpeg(self):
        stdout, stderr = self.process.communicate()
        if stderr:
            error_message = "\n".join(stderr.split("\n")[:20])
            self.error_queue.put(error_message)
            with open("ffmpeg_error.log", "w") as f:
                f.write(stderr)
        else:
            print("FFmpeg has finished recording.")

# Error queue definition and main layout
error_queue = queue.Queue()
			
def show_webcam(stop_event):
    video_device = config['SETTINGS']['video_device']
    if not video_device:
        sg.popup_error("No video device found. Go to Settings to select your video device.", keep_on_top=True)
        return

    cmd = ['ffplay', '-f', 'video4linux2', '-i', video_device]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    while not stop_event.is_set():
        time.sleep(0.1)
    
    process.terminate()
    process.wait()

def open_settings():
    layout = [
        [sg.Text("Settings")],
        [sg.Text("Audio Peripheral:"), sg.InputText(config['SETTINGS']['audio_device'], key='-AUDIO_DEVICE-'), 
         sg.Button('Copy Audio Command')],
        [sg.Text("Video Peripheral:"), sg.InputText(config['SETTINGS']['video_device'], key='-VIDEO_DEVICE-'), 
         sg.Button('Copy Video Command')],
        [sg.Text("FPS:"), sg.InputText(config['SETTINGS']['fps'], key='-FPS-')],
        [sg.Text("Video Format:"), sg.Combo(['mp4', 'mkv'], 
                                           default_value=config['SETTINGS']['video_format'],
                                           key='-VIDEO_FORMAT-',
                                           readonly=True)],
        [sg.Text("Save Folder:"), sg.InputText(config['SETTINGS']['output_folder'], key='-OUTPUT_FOLDER-'), 
         sg.FolderBrowse()],
        [sg.Text("Display:"), sg.InputText(config['SETTINGS']['display'], key='-DISPLAY-'), sg.Button('Copy Display Command') ],
        [sg.Button('Salva'), sg.Button('Cancel')]
    ]
    window = sg.Window('Settings', layout, keep_on_top=True)
    
    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == 'Cancel':
            break
        elif event == 'Salva':
            config['SETTINGS']['audio_device'] = values['-AUDIO_DEVICE-']
            config['SETTINGS']['video_device'] = values['-VIDEO_DEVICE-']
            config['SETTINGS']['fps'] = values['-FPS-']
            config['SETTINGS']['output_folder'] = values['-OUTPUT_FOLDER-']
            config['SETTINGS']['video_format'] = values['-VIDEO_FORMAT-']
            config['SETTINGS']['display'] = values['-DISPLAY-']
            save_config(config)
            break
        elif event == 'Copy Audio Command':
            sg.clipboard_set("pacmd list-sources | awk '/index:/ {print $0}; /name:/ {print $0}; /device\\.description/ {print $0}'")
        elif event == 'Copy Video Command':
            sg.clipboard_set("v4l2-ctl --list-devices")
        elif event == 'Copy Display Command':
            sg.clipboard_set("echo $DISPLAY.0")
    
    window.close()

def open_info():
    layout = [
        [sg.Text("pyDeskREC")],
        [sg.Text("Author: MoonDragon")],
        [sg.Text("Website: "), sg.InputText("https://github.com/MoonDragon-MD/pyDeskREC", readonly=True)],
        [sg.Text("Versione: 0.9.3")],
        [sg.Button('OK')]
    ]
    window = sg.Window('Info', layout, keep_on_top=True)
    
    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == 'OK':
            break
    
    window.close()

def update_record_button(window, recorder):
    if recorder.recording:
        window['Start Recording'].update(button_color=('white', 'green'))
    elif recorder.is_waiting:
        window['Start Recording'].update(button_color=('black', 'yellow'), text="In attesa")
    else:
        window['Start Recording'].update(button_color=sg.theme_button_color(), text="Start Recording")

def validate_time(time_str):
    try:
        if not time_str:
            return None
        time_obj = datetime.strptime(time_str, "%H:%M")
        return datetime.now().replace(hour=time_obj.hour, 
                                    minute=time_obj.minute, 
                                    second=0, 
                                    microsecond=0)
    except ValueError:
        return None


layout = [
    [sg.Text('FPS:'), sg.InputText(default_text=config['SETTINGS']['fps'], size=(10, 1), key='-FPS-')],
    [sg.Text('Duration (in minutes):'), sg.InputText(default_text='', size=(10, 1), key='-DURATION-'), 
     sg.Text('Start time (HH:MM):'), sg.InputText(default_text='', size=(10, 1), key='-START_TIME-'),
     sg.Text('End time (HH:MM):'), sg.InputText(default_text='', size=(10, 1), key='-END_TIME-')],
    [sg.Text('Countdown (in seconds):'), sg.InputText(default_text='', size=(10, 1), key='-COUNTDOWN-')],
    [sg.Button('Select Area'), sg.Button('Select Folder'), 
     sg.FolderBrowse(target='-FOLDER-', key='-FOLDER_BROWSE-'), 
     sg.InputText(default_text=config['SETTINGS']['output_folder'], key='-FOLDER-')],
    [sg.Checkbox('Record System Audio', default=True, key='-AUDIO_SYSTEM-'), 
     sg.Checkbox('Record Microphone', default=False, key='-AUDIO_MIC-')],
    [sg.Checkbox('Webcam', default=False, key='-WEBCAM-')],
    [sg.Button('Start Recording'), sg.Button('Stop Recording & Reset Area')],
    [sg.Button('Settings'), sg.Button('Info')]
]

# Main window creation and initialization
window = sg.Window('pyDeskREC', layout)
recorder = ScreenRecorder(error_queue)
webcam_thread = None
webcam_stop_event = threading.Event()
webcam_window_open = False

# Main Loop
while True:
    event, values = window.read(timeout=20)

    if event == sg.WIN_CLOSED:
        if recorder.recording:
            if sg.popup_yes_no("Registration is in progress. Do you really want to leave?", 
                             title="Confirm exit") == "Yes":
                recorder.stop_recording()
                break
        else:
            break

    if values['-DURATION-'].strip():
        window['-END_TIME-'].update(disabled=True)
    else:
        window['-END_TIME-'].update(disabled=False)

    if values['-END_TIME-'].strip():
        window['-DURATION-'].update(disabled=True)
    else:
        window['-DURATION-'].update(disabled=False)

    if event == 'Select Area':
        recorder.choose_area()

    if event == 'Select Folder':
        recorder.output_folder = values['-FOLDER-']

    if event == 'Start Recording':
        start_time = validate_time(values['-START_TIME-'])
        end_time = validate_time(values['-END_TIME-'])
    
        try:
            duration = float(values['-DURATION-']) if values['-DURATION-'].strip() else 0
            countdown = int(values['-COUNTDOWN-']) if values['-COUNTDOWN-'].strip() else 0
            if countdown > 3600:
                sg.popup_error("The countdown cannot exceed 3600 seconds (1 hour).", keep_on_top=True)
                continue
            fps = int(values['-FPS-']) if values['-FPS-'].strip() else 30
        except ValueError:
            sg.popup_error("Invalid numeric values", keep_on_top=True)
            continue

        recorder.fps = fps
        recorder.duration_minutes = duration
        recorder.countdown_seconds = countdown
        recorder.record_system_audio = values['-AUDIO_SYSTEM-']
        recorder.record_microphone = values['-AUDIO_MIC-']

        recorder.start_recording(start_time, end_time)

    if event == 'Stop Recording & Reset Area':
        recorder.stop_recording()

    if event == 'Settings':
        open_settings()

    if event == 'Info':
        open_info()

    if values['-WEBCAM-'] and not webcam_thread:
        if not config['SETTINGS']['video_device']:
            sg.popup_error("Please set up a video device in the Settings.", keep_on_top=True)
            window['-WEBCAM-'].update(False)
            continue
        webcam_stop_event.clear()
        webcam_thread = threading.Thread(target=show_webcam, args=(webcam_stop_event,), daemon=True)
        webcam_thread.start()
    elif not values['-WEBCAM-'] and webcam_thread:
        webcam_stop_event.set()
        webcam_thread.join()
        webcam_thread = None

    update_record_button(window, recorder)

    if not error_queue.empty():
        error_message = error_queue.get()
        sg.popup_scrolled(f"ffmpeg error: {error_message}", 
                         title="ffmpeg error", 
                         size=(80, 20), 
                         no_titlebar=False, 
                         keep_on_top=True)
                         
    if event == sg.WIN_CLOSED:
        close_application()
        break      
        
def cleanup():
    if webcam_thread:
        webcam_stop_event.set()
        webcam_thread.join()
    if recorder.process:
        recorder.process.terminate()
        recorder.process.wait()

def close_application():
    if recorder.recording:
        recorder.stop_recording()
    cleanup()  # Make sure your webcam and processes are stopped properly
    window.close()  # Now close the window
