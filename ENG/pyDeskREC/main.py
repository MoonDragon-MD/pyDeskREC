import PySimpleGUI as sg
import threading
import queue
from config_manager import load_config, save_config
from devices import check_ffmpeg_installed, show_webcam, get_audio_sources, get_video_devices
from screen_recorder import ScreenRecorder

## V 1.0.0 by MoonDragon  - https://github.com/MoonDragon-MD/pyDeskREC

def update_record_button(window, recorder):
    if recorder.recording:
        window['Start Recording'].update(button_color=('white', 'green'))
    elif recorder.is_waiting:
        window['Start Recording'].update(button_color=('black', 'yellow'), text="Waiting")
    else:
        window['Start Recording'].update(button_color=sg.theme_button_color(), text="Start Recording")

def open_settings(config):
    layout = [
        [sg.Text("Settings")],
        [sg.Text("Audio Device:"), sg.InputText(config['SETTINGS']['audio_device'], key='-AUDIO_DEVICE-'), 
         sg.Button('Copy Audio Command')],
        [sg.Text("Video Device:"), sg.InputText(config['SETTINGS']['video_device'], key='-VIDEO_DEVICE-'), 
         sg.Button('Copy Video Command')],
        [sg.Text("FPS:"), sg.InputText(config['SETTINGS']['fps'], key='-FPS-')],
        [sg.Text("Video Format:"), sg.Combo(['mp4', 'mkv'], 
                                           default_value=config['SETTINGS']['video_format'],
                                           key='-VIDEO_FORMAT-',
                                           readonly=True)],
        [sg.Text("Output Folder:"), sg.InputText(config['SETTINGS']['output_folder'], key='-OUTPUT_FOLDER-'), 
         sg.FolderBrowse()],
        [sg.Text("Display:"), sg.InputText(config['SETTINGS']['display'], key='-DISPLAY-'), 
         sg.Button('Copy Display Command')],
        [sg.Button('Save'), sg.Button('Cancel')]
    ]
    window = sg.Window('Settings', layout, keep_on_top=True)
    
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, 'Cancel'):
            break
        elif event == 'Save':
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
        [sg.Text("Version: 1.0.0")],
        [sg.Button('OK')]
    ]
    window = sg.Window('Info', layout, keep_on_top=True)
    
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, 'OK'):
            break
    window.close()

def main():
    # Initialization
    config, area, display = load_config()
    error_queue = queue.Queue()
    
    # Initial configuration check
    if not check_ffmpeg_installed():
        exit(1)
    
    if not config['SETTINGS']['audio_device'] or not config['SETTINGS']['video_device'] or not config['SETTINGS']['display']:
        sg.popup("Configuration needed: Audio Device, Video Device, Display", 
                title="Configuration Needed", keep_on_top=True)
    
    layout = [
        [sg.Text('FPS:'), sg.InputText(default_text=config['SETTINGS']['fps'], size=(10, 1), key='-FPS-')],
        [sg.Text('Duration (in minutes):'), sg.InputText(size=(10, 1), key='-DURATION-'), 
         sg.Text('Start Time (HH:MM):'), sg.InputText(size=(10, 1), key='-START_TIME-'),
         sg.Text('End Time (HH:MM):'), sg.InputText(size=(10, 1), key='-END_TIME-')],
        [sg.Text('Countdown (in seconds):'), sg.InputText(size=(10, 1), key='-COUNTDOWN-')],
        [sg.Button('Select Area'), sg.Button('Select Folder'), 
         sg.FolderBrowse(target='-FOLDER-', key='-FOLDER_BROWSE-'), 
         sg.InputText(default_text=config['SETTINGS']['output_folder'], key='-FOLDER-')],
        [sg.Checkbox('Record System Audio', default=True, key='-AUDIO_SYSTEM-'), 
         sg.Checkbox('Record Microphone', default=False, key='-AUDIO_MIC-')],
        [sg.Checkbox('Webcam', default=False, key='-WEBCAM-')],
        [sg.Button('Start Recording'), sg.Button('Stop Recording & Reset Area')],
        [sg.Button('Settings'), sg.Button('Info')]
    ]

    # Create main window and initialization
    window = sg.Window('pyDeskREC', layout)
    recorder = ScreenRecorder(config, error_queue)
    webcam_thread = None
    webcam_stop_event = threading.Event()

    # Main Loop
    while True:
        event, values = window.read(timeout=20)

        if event == sg.WIN_CLOSED:
            if recorder.recording:
                if sg.popup_yes_no("Recording is in progress. Do you really want to exit?", 
                                title="Confirm Exit") == "Yes":
                    recorder.stop_recording()
                    break
            else:
                break

        # Handle duration/end time
        if values['-DURATION-'].strip():
            window['-END_TIME-'].update(disabled=True)
        else:
            window['-END_TIME-'].update(disabled=False)

        if values['-END_TIME-'].strip():
            window['-DURATION-'].update(disabled=True)
        else:
            window['-DURATION-'].update(disabled=False)

        if event == 'Select Area':
                try:
                    recorder.choose_area()
                    # Immediately update GUI
                    window.refresh()
                except Exception as e:
                    print(f"Error selecting area: {e}")
                    sg.popup_error(f"Error selecting area: {e}")

        if event == 'Select Folder':
            recorder.output_folder = values['-FOLDER-']

        if event == 'Start Recording':
            from config_manager import validate_time
            start_time = validate_time(values['-START_TIME-'])
            end_time = validate_time(values['-END_TIME-'])
        
            try:
                duration = float(values['-DURATION-']) if values['-DURATION-'].strip() else 0
                countdown = int(values['-COUNTDOWN-']) if values['-COUNTDOWN-'].strip() else 0
                if countdown > 3600:
                    sg.popup_error("Countdown cannot exceed 3600 seconds (1 hour).", keep_on_top=True)
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
            open_settings(config)

        if event == 'Info':
            open_info()

        if values['-WEBCAM-'] and not webcam_thread:
            if not config['SETTINGS']['video_device']:
                sg.popup_error("Configure a video device in settings first.", keep_on_top=True)
                window['-WEBCAM-'].update(False)
                continue
            webcam_stop_event.clear()
            webcam_thread = threading.Thread(target=show_webcam, args=(config, webcam_stop_event), daemon=True)
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

    # Final cleanup
    if webcam_thread:
        webcam_stop_event.set()
        webcam_thread.join()
    if recorder.process:
        recorder.stop_recording()
    window.close()

if __name__ == "__main__":
    main()