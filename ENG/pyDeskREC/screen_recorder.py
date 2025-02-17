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
        self.record_system_audio = True
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
        """Handles screen area selection"""
        print("Select the screen area to record.")
        
        # Create a variable to manage completion
        selection_done = threading.Event()
        selected_area = [None]  # List to store the selected area
        
        def selection_thread():
            root = tk.Tk()
            root.overrideredirect(1)
            root.wait_visibility(root)
            try:
                root.wm_attributes("-alpha", 0.5)
            except tk.TclError:
                print("Transparency not supported.")
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
                
                # Calculate the area
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

        # Start the selection thread
        select_thread = threading.Thread(target=selection_thread)
        select_thread.daemon = True
        select_thread.start()

        # Wait for the selection to complete (with timeout)
        selection_done.wait(timeout=60)  # 60-second timeout

        # Handle the selection result
        if selected_area[0]:
            self.area = selected_area[0]
            print(f"Selected area: {self.area}")
            area_string = ','.join(map(str, self.area))
            self.config['SETTINGS']['area'] = area_string
            save_config(self.config)
        else:
            print("No area selected or selection canceled. Using full screen.")
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
                    print(f"Invalid area, using full screen: {offset_x}, {offset_y}, {width}, {height}")

                if width <= 0 or height <= 0:
                    raise ValueError("Selected area is invalid (width or height <= 0)")
        
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
            print(f"Generated FFmpeg command: {' '.join(cmd)}")
            return cmd

        except Exception as e:
            print(f"Error setting up FFmpeg: {e}")
            raise

    def start_recording(self, start_time=None, end_time=None):
        print(f"Current area: {self.area}")
        if self.is_waiting or self.recording:
            print("Recording already in progress or waiting")
            return

        if not self.area:
            area_string = self.config['SETTINGS']['area']
            if area_string:
                self.area = tuple(map(int, area_string.split(',')))
            else:
                screen_size = pyautogui.size()
                self.area = (0, 0, screen_size.width, screen_size.height)
    
        print(f"Selected area for recording: {self.area}")

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
            error_msg = f"Error starting recording: {str(e)}"
            print(error_msg)
            self.error_queue.put(error_msg)
            sg.popup_error(error_msg, keep_on_top=True)

    def _start_recording_now(self, end_time):
        try:
            if not os.path.exists(self.output_folder):
                os.makedirs(self.output_folder)
        
            now = datetime.now()
            extension = '.mkv' if self.video_format == 'mkv' else '.mp4'
            output_file = f"{self.output_folder}/recording_{now.strftime('%Y-%m-%d_%H-%M-%S')}{extension}"
    
            cmd = self.setup_ffmpeg_command(output_file)
            print(f"Executing command: {' '.join(cmd)}")
    
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
            print(f"Recording thread started: {self.record_thread.is_alive()}")
            sg.popup_quick_message("Recording started", background_color='green', text_color='white')
            
            if self.duration_minutes > 0:
                threading.Timer(self.duration_minutes * 60, self.stop_recording).start()
            elif end_time:
                delay = (end_time - datetime.now()).total_seconds()
                if delay > 0:
                    threading.Timer(delay, self.stop_recording).start()

        except Exception as e:
            self.recording = False
            error_msg = f"Error starting recording: {str(e)}"
            print(error_msg)
            self.error_queue.put(error_msg)
            sg.popup_error(error_msg, keep_on_top=True)

    def stop_recording(self):
        try:
            if self.process and self.recording:
                print("Stopping recording...")
                self.process.terminate()
                self.process.wait()
                self.recording = False
                self.is_waiting = False
                sg.popup("Recording stopped.", keep_on_top=True)

            self.reset_area()
        except Exception as e:
            print(f"Error resetting area: {e}")
            #sg.popup_error(f"Error resetting area: {e}")
            print(f"Error resetting area: {e}")  # Print only, no popup

    def reset_area(self):
        """Resets the selection area"""
        self.area = None
        self.config['SETTINGS']['area'] = ''
        save_config(self.config)
        print("Area reset")

    def get_full_screen_area(self):
        """Gets the full screen area"""
        screen_size = pyautogui.size()
        return (0, 0, screen_size.width, screen_size.height)

    def countdown(self, seconds):
        for i in range(seconds, 0, -1):
            sg.popup_auto_close(f"Recording starts in {i} seconds...", 
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
            print("FFmpeg finished recording.")