import subprocess
import PySimpleGUI as sg

## V 1.0.0 by MoonDragon  - https://github.com/MoonDragon-MD/pyDeskREC

def get_video_devices():
    """Recupera l'elenco dei dispositivi video disponibili"""
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
    """Recupera l'elenco delle sorgenti audio disponibili"""
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
    """Verifica se FFmpeg è installato e funzionante"""
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

def show_webcam(config, stop_event):
    """Mostra l'anteprima della webcam utilizzando FFplay"""
    video_device = config['IMPOSTAZIONI']['dispositivo_video']
    if not video_device:
        sg.popup_error("Non è stato trovato alcun dispositivo video. Vai su Impostazioni per selezionare il dispositivo video.", keep_on_top=True)
        return

    cmd = ['ffplay', '-f', 'video4linux2', '-i', video_device]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    while not stop_event.is_set():
        import time
        time.sleep(0.1)
    
    process.terminate()
    process.wait()