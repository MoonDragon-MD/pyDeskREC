import PySimpleGUI as sg
import threading
import queue
from config_manager import load_config, save_config
from devices import check_ffmpeg_installed, show_webcam, get_audio_sources, get_video_devices
from screen_recorder import ScreenRecorder

## V 1.0.0 by MoonDragon  - https://github.com/MoonDragon-MD/pyDeskREC

def update_record_button(window, recorder):
    if recorder.recording:
        window['Avvia Registrazione'].update(button_color=('white', 'green'))
    elif recorder.is_waiting:
        window['Avvia Registrazione'].update(button_color=('black', 'yellow'), text="In attesa")
    else:
        window['Avvia Registrazione'].update(button_color=sg.theme_button_color(), text="Avvia Registrazione")

def open_settings(config):
    layout = [
        [sg.Text("Impostazioni")],
        [sg.Text("Periferica Audio:"), sg.InputText(config['SETTINGS']['audio_device'], key='-AUDIO_DEVICE-'), 
         sg.Button('Copia Comando Audio')],
        [sg.Text("Periferica Video:"), sg.InputText(config['SETTINGS']['video_device'], key='-VIDEO_DEVICE-'), 
         sg.Button('Copia Comando Video')],
        [sg.Text("FPS:"), sg.InputText(config['SETTINGS']['fps'], key='-FPS-')],
        [sg.Text("Formato Video:"), sg.Combo(['mp4', 'mkv'], 
                                           default_value=config['SETTINGS']['video_format'],
                                           key='-VIDEO_FORMAT-',
                                           readonly=True)],
        [sg.Text("Cartella di Salvataggio:"), sg.InputText(config['SETTINGS']['output_folder'], key='-OUTPUT_FOLDER-'), 
         sg.FolderBrowse()],
        [sg.Text("Display:"), sg.InputText(config['SETTINGS']['display'], key='-DISPLAY-'), 
         sg.Button('Copia Comando Display')],
        [sg.Button('Salva'), sg.Button('Annulla')]
    ]
    window = sg.Window('Impostazioni', layout, keep_on_top=True)
    
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, 'Annulla'):
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
        elif event == 'Copia Comando Audio':
            sg.clipboard_set("pacmd list-sources | awk '/index:/ {print $0}; /name:/ {print $0}; /device\\.description/ {print $0}'")
        elif event == 'Copia Comando Video':
            sg.clipboard_set("v4l2-ctl --list-devices")
        elif event == 'Copia Comando Display':
            sg.clipboard_set("echo $DISPLAY.0")
    
    window.close()

def open_info():
    layout = [
        [sg.Text("pyDeskREC")],
        [sg.Text("Autore: MoonDragon")],
        [sg.Text("Sito Web: "), sg.InputText("https://github.com/MoonDragon-MD/pyDeskREC", readonly=True)],
        [sg.Text("Versione: 1.0.0")],
        [sg.Button('OK')]
    ]
    window = sg.Window('Info', layout, keep_on_top=True)
    
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, 'OK'):
            break
    window.close()

def main():
    # Inizializzazione
    config, area, display = load_config()
    error_queue = queue.Queue()
    
    # Verifica configurazione iniziale
    if not check_ffmpeg_installed():
        exit(1)
    
    if not config['SETTINGS']['audio_device'] or not config['SETTINGS']['video_device'] or not config['SETTINGS']['display']:
        sg.popup("Configurazione necessaria: Audio Device, Video Device, Display", 
                title="Configurazione necessaria", keep_on_top=True)
    
    layout = [
        [sg.Text('FPS:'), sg.InputText(default_text=config['SETTINGS']['fps'], size=(10, 1), key='-FPS-')],
        [sg.Text('Durata (in minuti):'), sg.InputText(size=(10, 1), key='-DURATION-'), 
         sg.Text('Ora di inizio (HH:MM):'), sg.InputText(size=(10, 1), key='-START_TIME-'),
         sg.Text('Ora di fine (HH:MM):'), sg.InputText(size=(10, 1), key='-END_TIME-')],
        [sg.Text('Countdown (in secondi):'), sg.InputText(size=(10, 1), key='-COUNTDOWN-')],
        [sg.Button('Seleziona Area'), sg.Button('Seleziona Cartella'), 
         sg.FolderBrowse(target='-FOLDER-', key='-FOLDER_BROWSE-'), 
         sg.InputText(default_text=config['SETTINGS']['output_folder'], key='-FOLDER-')],
        [sg.Checkbox('Registra Audio di Sistema', default=True, key='-AUDIO_SYSTEM-'), 
         sg.Checkbox('Registra Microfono', default=False, key='-AUDIO_MIC-')],
        [sg.Checkbox('Webcam', default=False, key='-WEBCAM-')],
        [sg.Button('Avvia Registrazione'), sg.Button('Ferma Registrazione & Reset Area')],
        [sg.Button('Impostazioni'), sg.Button('Info')]
    ]

    # Creazione finestra principale e inizializzazione
    window = sg.Window('pyDeskREC', layout)
    recorder = ScreenRecorder(config, error_queue)
    webcam_thread = None
    webcam_stop_event = threading.Event()

    # Main Loop
    while True:
        event, values = window.read(timeout=20)

        if event == sg.WIN_CLOSED:
            if recorder.recording:
                if sg.popup_yes_no("La registrazione è in corso. Vuoi davvero uscire?", 
                                title="Conferma uscita") == "Yes":
                    recorder.stop_recording()
                    break
            else:
                break

        # Gestione della durata/ora di fine
        if values['-DURATION-'].strip():
            window['-END_TIME-'].update(disabled=True)
        else:
            window['-END_TIME-'].update(disabled=False)

        if values['-END_TIME-'].strip():
            window['-DURATION-'].update(disabled=True)
        else:
            window['-DURATION-'].update(disabled=False)

        if event == 'Seleziona Area':
                try:
                    recorder.choose_area()
                    # Aggiorna immediatamente la GUI
                    window.refresh()
                except Exception as e:
                    print(f"Errore durante la selezione dell'area: {e}")
                    sg.popup_error(f"Errore durante la selezione dell'area: {e}")

        if event == 'Seleziona Cartella':
            recorder.output_folder = values['-FOLDER-']

        if event == 'Avvia Registrazione':
            from config_manager import validate_time
            start_time = validate_time(values['-START_TIME-'])
            end_time = validate_time(values['-END_TIME-'])
        
            try:
                duration = float(values['-DURATION-']) if values['-DURATION-'].strip() else 0
                countdown = int(values['-COUNTDOWN-']) if values['-COUNTDOWN-'].strip() else 0
                if countdown > 3600:
                    sg.popup_error("Il countdown non può superare i 3600 secondi (1 ora).", keep_on_top=True)
                    continue
                fps = int(values['-FPS-']) if values['-FPS-'].strip() else 30
            except ValueError:
                sg.popup_error("Valori numerici non validi", keep_on_top=True)
                continue

            recorder.fps = fps
            recorder.duration_minutes = duration
            recorder.countdown_seconds = countdown
            recorder.record_system_audio = values['-AUDIO_SYSTEM-']
            recorder.record_microphone = values['-AUDIO_MIC-']

            recorder.start_recording(start_time, end_time)

        if event == 'Ferma Registrazione & Reset Area':
            recorder.stop_recording()

        if event == 'Impostazioni':
            open_settings(config)

        if event == 'Info':
            open_info()

        if values['-WEBCAM-'] and not webcam_thread:
            if not config['SETTINGS']['video_device']:
                sg.popup_error("Configura prima un dispositivo video nelle impostazioni.", keep_on_top=True)
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
            sg.popup_scrolled(f"Errore di ffmpeg: {error_message}", 
                            title="Errore di ffmpeg", 
                            size=(80, 20), 
                            no_titlebar=False, 
                            keep_on_top=True)

    # Cleanup finale
    if webcam_thread:
        webcam_stop_event.set()
        webcam_thread.join()
    if recorder.process:
        recorder.stop_recording()
    window.close()

if __name__ == "__main__":
    main()
