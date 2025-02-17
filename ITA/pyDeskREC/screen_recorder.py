import os
import time
import subprocess
import threading
from datetime import datetime
import tkinter as tk
import PySimpleGUI as sg
import pyautogui
from config_manager import save_config

## V 1.0.0 by MoonDragon  - https://github.com/MoonDragon-MD/pyDeskREC

class ScreenRecorder:
    def __init__(self, config, error_queue):
        self.config = config
        self.output_folder = config['SETTINGS']['output_folder']
        self.fps = int(config['SETTINGS']['fps'])
        self.duration_minutes = 0
        self.countdown_seconds = 0
        self.record_system_audiso = True
        self.record_microphone = False
        self.recording = False
        self.is_waiting = False
        self.start_time = None
        self.end_time = None
        self.area = None
        self.display = config['SETTINGS']['display']
        self.process = None
        self.record_thread = None
        self.error_queue = error_queue
        self.manual_audio_source = config['SETTINGS']['audio_device']
        self.manual_video_device = config['SETTINGS']['video_device']
        self.video_format = config['SETTINGS']['video_format']

    def choose_area(self):
        """Gestisce la selezione dell'area dello schermo"""
        print("Seleziona l'area dello schermo da registrare.")
        
        # Creiamo una variabile per gestire il completamento
        selection_done = threading.Event()
        selected_area = [None]  # Lista per memorizzare l'area selezionata
        
        def selection_thread():
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
                
                # Calcola l'area
                area = (
                    min(start_x, end_x), min(start_y, end_y),
                    abs(start_x - end_x), abs(start_y - end_y)
                )
                
                selected_area[0] = area
                root.quit()
                root.destroy()
                selection_done.set()

            def on_escape(event):
                root.quit()
                root.destroy()
                selection_done.set()

            canvas.bind("<ButtonPress-1>", on_press)
            canvas.bind("<B1-Motion>", on_drag)
            canvas.bind("<ButtonRelease-1>", on_release)
            root.bind("<Escape>", on_escape)

            try:
                root.mainloop()
            except:
                if root:
                    root.destroy()
                selection_done.set()

        # Avvia il thread di selezione
        select_thread = threading.Thread(target=selection_thread)
        select_thread.daemon = True
        select_thread.start()

        # Aspetta che la selezione sia completata (con timeout)
        selection_done.wait(timeout=60)  # Timeout di 60 secondi

        # Gestisce il risultato della selezione
        if selected_area[0]:
            self.area = selected_area[0]
            print(f"Area selezionata: {self.area}")
            area_string = ','.join(map(str, self.area))
            self.config['SETTINGS']['area'] = area_string
            save_config(self.config)
        else:
            print("Nessuna area selezionata o selezione annullata. Uso schermo intero.")
            screen_size = pyautogui.size()
            self.area = (0, 0, screen_size.width, screen_size.height)
            self.config['SETTINGS']['area'] = ''
            save_config(self.config)

        return True

    def setup_ffmpeg_command(self, output_file):
        try:
            cmd = [
                'ffmpeg',
                '-f', 'x11grab',
                '-r', str(self.fps),
                '-thread_queue_size', '4096'
            ]

            if self.area:
                if all(isinstance(val, int) for val in self.area):
                    offset_x, offset_y, width, height = self.area
                else:
                    screen_size = pyautogui.size()
                    offset_x, offset_y, width, height = 0, 0, screen_size.width, screen_size.height
                    print(f"Area non valida, usando schermo intero: {offset_x}, {offset_y}, {width}, {height}")

                if width <= 0 or height <= 0:
                    raise ValueError("L'area selezionata non è valida (larghezza o altezza <= 0)")
        
                cmd.extend(['-video_size', f"{width}x{height}", '-i', f"{self.display}+{offset_x},{offset_y}"])
            else:
                cmd.extend(['-i', f"{self.display}"])

            if self.record_system_audio:
                if self.manual_audio_source:
                    cmd.extend(['-f', 'pulse', '-i', self.manual_audio_source])
                else:
                    cmd.extend(['-f', 'pulse', '-i', 'default'])

            if self.record_microphone:
                cmd.extend(['-f', 'pulse', '-i', 'default'])

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

            cmd.append(output_file)
            print(f"Comando FFmpeg generato: {' '.join(cmd)}")
            return cmd

        except Exception as e:
            print(f"Errore nella configurazione di FFmpeg: {e}")
            raise

    def start_recording(self, start_time=None, end_time=None):
        print(f"Area corrente: {self.area}")
        if self.is_waiting or self.recording:
            print("Registrazione già in corso o in attesa")
            return

        if not self.area:
            area_string = self.config['SETTINGS']['area']
            if area_string:
                self.area = tuple(map(int, area_string.split(',')))
            else:
                screen_size = pyautogui.size()
                self.area = (0, 0, screen_size.width, screen_size.height)
    
        print(f"Area selezionata per la registrazione: {self.area}")

        try:
            if self.countdown_seconds > 0:
                self.countdown(self.countdown_seconds)
            
            if start_time:
                self.is_waiting = True
                delay = (start_time - datetime.now()).total_seconds()
                if delay > 0:
                    threading.Timer(delay, self._start_recording_now, args=(end_time,)).start()
                    return

            self._start_recording_now(end_time)

        except Exception as e:
            self.recording = False
            self.is_waiting = False
            error_msg = f"Errore nell'avvio della registrazione: {str(e)}"
            print(error_msg)
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
            print(f"Esecuzione comando: {' '.join(cmd)}")
    
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
            print(f"Thread di registrazione avviato: {self.record_thread.is_alive()}")
            sg.popup_quick_message("Registrazione avviata", background_color='green', text_color='white')
            
            if self.duration_minutes > 0:
                threading.Timer(self.duration_minutes * 60, self.stop_recording).start()
            elif end_time:
                delay = (end_time - datetime.now()).total_seconds()
                if delay > 0:
                    threading.Timer(delay, self.stop_recording).start()

        except Exception as e:
            self.recording = False
            error_msg = f"Errore nell'avvio della registrazione: {str(e)}"
            print(error_msg)
            self.error_queue.put(error_msg)
            sg.popup_error(error_msg, keep_on_top=True)

    def stop_recording(self):
        try:
            if self.process and self.recording:
                print("Fermando la registrazione...")
                self.process.terminate()
                self.process.wait()
                self.recording = False
                self.is_waiting = False
                sg.popup("Registrazione terminata.", keep_on_top=True)

            self.reset_area()
        except Exception as e:
            print(f"Errore durante il reset dell'area: {e}")
            #sg.popup_error(f"Errore durante il reset dell'area: {e}")
            print(f"Errore durante il reset dell'area: {e}")  # Solo print, niente popup

    def reset_area(self):
        """Resetta l'area di selezione"""
        self.area = None
        self.config['SETTINGS']['area'] = ''
        save_config(self.config)
        print("Area resettata")

    def get_full_screen_area(self):
        """Ottiene l'area dello schermo intero"""
        screen_size = pyautogui.size()
        return (0, 0, screen_size.width, screen_size.height)

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
