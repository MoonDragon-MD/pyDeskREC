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
            # Aggiorna le impostazioni esistenti
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
        print(f"Errore nel recupero dei dispositivi video: {e}")
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
        print(f"Errore nel recupero delle sorgenti audio: {e}")
        return []

def check_ffmpeg_installed():
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE, 
                              text=True, 
                              timeout=5)
        if result.returncode != 0:
            sg.popup_error("FFmpeg non è installato o non è nel PATH.", keep_on_top=True)
            return False
        return True
    except Exception as e:
        sg.popup_error(f"Errore nella verifica di FFmpeg: {e}", keep_on_top=True)
        return False

config, area, display = load_config()  # Separare i valori restituiti

if not config['SETTINGS']['audio_device'] or not config['SETTINGS']['video_device'] or not config['SETTINGS']['display']:
    sg.popup("Almeno uno dei parametri (Audio Device, Video Device, Display) non è impostato. Vai in Impostazioni per configurarli.", title="Configurazione necessaria", keep_on_top=True)
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
        self.area = area  # Usa l'area caricata dal file di configurazione
        self.display = config['SETTINGS']['display']  # Usa il display dal file di configurazione
        self.process = None
        self.record_thread = None
        self.error_queue = error_queue
        self.manual_audio_source = config['SETTINGS']['audio_device']
        self.manual_video_device = config['SETTINGS']['video_device']
        self.video_format = config['SETTINGS']['video_format']

    def get_display_value(self):
        # Verifica se il valore di display è già nel file di configurazione
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
                print(f"Display trovato: {display_value}")
                self.config['SETTINGS']['display'] = display_value  # Salva nella configurazione
                save_config(self.config)  # Salva il nuovo valore
                return display_value
            else:
                print("Nessun valore DISPLAY trovato, utilizzando fallback ':0.0'.")
                self.config['SETTINGS']['display'] = ':0.0'  # Salva il fallback nella configurazione
                save_config(self.config)
                return ':0.0'
        except subprocess.CalledProcessError as e:
            print(f"Errore nell'esecuzione del comando: {e}. Utilizzando fallback ':0.0'.")
            self.config['SETTINGS']['display'] = ':0.0'  # Salva il fallback nella configurazione
            save_config(self.config)
            return ':0.0'

    def choose_area(self):
        sg.popup("Seleziona l'area dello schermo da registrare.", keep_on_top=True)
    
        root = tk.Tk()
        root.overrideredirect(1)
        root.wait_visibility(root)
        try:
            root.wm_attributes("-alpha", 0.5)
        except tk.TclError:
            print("La trasparenza non è supportata.")
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
    
            # Salva l'area come offset e dimensioni
            self.area = (
                min(start_x, end_x), min(start_y, end_y),  # Offset (X, Y)
                abs(start_x - end_x), abs(start_y - end_y)  # Dimensioni (width, height)
            )

            if self.area[2] > 0 and self.area[3] > 0:
                sg.popup(f"Area selezionata: {self.area}", keep_on_top=True)
                # Converti in stringa per il salvataggio
                area_string = ','.join(map(str, self.area))
                config['SETTINGS']['area'] = area_string
                save_config(config)
            else:
                self.area = None
                sg.popup("Nessuna area selezionata. Registrazione a tutto schermo.", keep_on_top=True)
                # Salva l'area nel file di configurazione
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
            # Comando base di FFmpeg
            cmd = [
                'ffmpeg',
                '-f', 'x11grab',              # Usa il grab dello schermo X11
                '-r', str(self.fps),          # FPS
                '-thread_queue_size', '4096'  # Aumenta la dimensione della coda
            ]

            # Se l'area è specificata, utilizza le coordinate
            if self.area:
                # Assicura che self.area sia una tupla di interi
               if all(isinstance(val, int) for val in self.area):
                    offset_x, offset_y, width, height = self.area
               else:
                    # Se non tutti i valori sono interi, usa lo schermo intero
                    screen_size = pyautogui.size()
                    offset_x, offset_y, width, height = 0, 0, screen_size.width, screen_size.height
                    print(f"Area non valida, usando schermo intero: {offset_x}, {offset_y}, {width}, {height}")

                # Verifica che le coordinate siano corrette (larghezza e altezza positive)
               if width <= 0 or height <= 0:
                    raise ValueError("L'area selezionata non è valida (larghezza o altezza <= 0)")
        
                # Aggiungi area a ffmpeg  
               cmd.extend(['-video_size', f"{width}x{height}", '-i', f"{self.display}+{offset_x},{offset_y}"])
            else:
                # Se l'area non è definita, utilizza lo schermo intero
                cmd.extend(['-i', f"{self.display}"])

            # Gestione audio
            if self.record_system_audio:
                if self.manual_audio_source:
                    cmd.extend(['-f', 'pulse', '-i', self.manual_audio_source])
                else:
                    cmd.extend(['-f', 'pulse', '-i', 'default'])

            if self.record_microphone:
                cmd.extend(['-f', 'pulse', '-i', 'default'])

            # Configurazione codec in base al formato
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

            # Aggiungi il file di output
            cmd.append(output_file)

            print(f"Comando FFmpeg generato: {' '.join(cmd)}")  # Debug logging
            return cmd

        except Exception as e:
            print(f"Errore nella configurazione di FFmpeg: {e}")  # Debug logging
            raise

    def start_recording(self, start_time=None, end_time=None):
        print(f"Area corrente: {self.area}")  # Debug
        if self.is_waiting or self.recording:
            print("Registrazione già in corso o in attesa")  # Debug logging
            return

        if not self.area:
            # Leggi l'area dal file di configurazione
            area_string = config['SETTINGS']['area']
            if area_string:
                self.area = tuple(map(int, area_string.split(',')))
            else:
                # Se l'area è vuota, usa lo schermo intero
                screen_size = pyautogui.size()
                self.area = (0, 0, screen_size.width, screen_size.height)
    
        print(f"Area selezionata per la registrazione: {self.area}")  # Debug logging

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
                    return  # Torna subito, la registrazione partirà dopo il timer

            # Inizia la registrazione se non c'è un timer di inizio
            self._start_recording_now(end_time)

        except Exception as e:
            self.recording = False
            self.is_waiting = False
            error_msg = f"Errore nell'avvio della registrazione: {str(e)}"
            print(error_msg)  # Debug logging
            self.error_queue.put(error_msg)
            sg.popup_error(error_msg, keep_on_top=True)

    def _start_recording_now(self, end_time):
        try:
            if not os.path.exists(self.output_folder):
                os.makedirs(self.output_folder)
        
            now = datetime.now()
            extension = '.mkv' if self.video_format == 'mkv' else '.mp4'
            output_file = f"{self.output_folder}/registrazione_{now.strftime('%Y-%m-%d_%H-%M-%S')}{extension}"
    
            cmd = self.setup_ffmpeg_command(output_file)
            print(f"Esecuzione comando: {' '.join(cmd)}")  # Debug logging
    
            self.recording = True
            self.is_waiting = False
            self.start_time = time.time()
    
            self.process = subprocess.Popen(cmd, 
                                          stdout=subprocess.PIPE, 
                                          stderr=subprocess.PIPE, 
                                          text=True)
        
            if self.process.poll() is not None:
                raise Exception("FFmpeg non è riuscito ad avviarsi")
        
            self.record_thread = threading.Thread(target=self.wait_for_ffmpeg)
            self.record_thread.start()
            print(f"Thread di registrazione avviato: {self.record_thread.is_alive()}")  # Debug    
            sg.popup_quick_message("Registrazione avviata", background_color='green', text_color='white')
    
            # Timer per durata o ora di fine
            if self.duration_minutes > 0:
                threading.Timer(self.duration_minutes * 60, self.stop_recording).start()
            elif end_time:
                delay = (end_time - datetime.now()).total_seconds()
                if delay > 0:
                    threading.Timer(delay, self.stop_recording).start()

        except Exception as e:
            self.recording = False
            error_msg = f"Errore nell'avvio della registrazione: {str(e)}"
            print(error_msg)  # Debug logging
            self.error_queue.put(error_msg)
            sg.popup_error(error_msg, keep_on_top=True)

    def stop_recording(self):
        try:
            if self.process and self.recording:
                # Se la registrazione è in corso, fermala
                print("Fermando la registrazione...")
                self.process.terminate()
                self.process.wait()
                self.recording = False
                self.is_waiting = False
                sg.popup("Registrazione terminata.", keep_on_top=True)

            # Indipendentemente dallo stato della registrazione, resetta l'area
            self.area = None  # Reset dell'area
            config['SETTINGS']['area'] = ''  # Imposta l'area a stringa vuota nel file di configurazione
            save_config(config)

            print("Area resettata.")
        except Exception as e:
            print(f"Errore durante il reset dell'area: {e}")
            sg.popup_error(f"Errore durante il reset dell'area: {e}")

    def countdown(self, seconds):
        for i in range(seconds, 0, -1):
            sg.popup_auto_close(f"Registrazione inizia tra {i} secondi...", 
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
            print("FFmpeg ha terminato la registrazione.")

# Definizione della coda degli errori e layout principale
error_queue = queue.Queue()
			
def show_webcam(stop_event):
    video_device = config['SETTINGS']['video_device']
    if not video_device:
        sg.popup_error("Non è stato trovato alcun dispositivo video. Vai su Impostazioni per selezionare il dispositivo video.", keep_on_top=True)
        return

    cmd = ['ffplay', '-f', 'video4linux2', '-i', video_device]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    while not stop_event.is_set():
        time.sleep(0.1)
    
    process.terminate()
    process.wait()

def open_settings():
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
        [sg.Text("Display:"), sg.InputText(config['SETTINGS']['display'], key='-DISPLAY-'), sg.Button('Copia Comando Display') ],
        [sg.Button('Salva'), sg.Button('Annulla')]
    ]
    window = sg.Window('Impostazioni', layout, keep_on_top=True)
    
    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == 'Annulla':
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
        window['Avvia Registrazione'].update(button_color=('white', 'green'))
    elif recorder.is_waiting:
        window['Avvia Registrazione'].update(button_color=('black', 'yellow'), text="In attesa")
    else:
        window['Avvia Registrazione'].update(button_color=sg.theme_button_color(), text="Avvia Registrazione")

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
    [sg.Text('Durata (in minuti):'), sg.InputText(default_text='', size=(10, 1), key='-DURATION-'), 
     sg.Text('Ora di inizio (HH:MM):'), sg.InputText(default_text='', size=(10, 1), key='-START_TIME-'),
     sg.Text('Ora di fine (HH:MM):'), sg.InputText(default_text='', size=(10, 1), key='-END_TIME-')],
    [sg.Text('Countdown (in secondi):'), sg.InputText(default_text='', size=(10, 1), key='-COUNTDOWN-')],
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
recorder = ScreenRecorder(error_queue)
webcam_thread = None
webcam_stop_event = threading.Event()
webcam_window_open = False

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

    if values['-DURATION-'].strip():
        window['-END_TIME-'].update(disabled=True)
    else:
        window['-END_TIME-'].update(disabled=False)

    if values['-END_TIME-'].strip():
        window['-DURATION-'].update(disabled=True)
    else:
        window['-DURATION-'].update(disabled=False)

    if event == 'Seleziona Area':
        recorder.choose_area()

    if event == 'Seleziona Cartella':
        recorder.output_folder = values['-FOLDER-']

    if event == 'Avvia Registrazione':
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
        open_settings()

    if event == 'Info':
        open_info()

    if values['-WEBCAM-'] and not webcam_thread:
        if not config['SETTINGS']['video_device']:
            sg.popup_error("Configura prima un dispositivo video nelle impostazioni.", keep_on_top=True)
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
        sg.popup_scrolled(f"Errore di ffmpeg: {error_message}", 
                         title="Errore di ffmpeg", 
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
    cleanup()  # Assicurati che la webcam e i processi siano fermati correttamente
    window.close()  # Ora chiudi la finestra
