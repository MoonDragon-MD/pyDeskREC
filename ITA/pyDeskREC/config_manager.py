import configparser
import os
import PySimpleGUI as sg

## V 1.0.0 by MoonDragon  - https://github.com/MoonDragon-MD/pyDeskREC

# Costanti di configurazione
CONFIG_FILE = "pyDeskREC.ini"

def load_config():
    """Carica o crea la configurazione iniziale"""
    config = configparser.ConfigParser()
    impostazioni_predefinite = {
        'dispositivo_audio': '',
        'dispositivo_video': '',
        'fps': '30',
        'cartella_output': os.path.expanduser("~/Video"),
        'formato_video': 'mp4',
        'area': '',
        'schermo': ''
    }

    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
        if not config.has_section('IMPOSTAZIONI'):
            config['IMPOSTAZIONI'] = impostazioni_predefinite
        else:
            # Aggiorna le impostazioni esistenti
            impostazioni_correnti = dict(config['IMPOSTAZIONI'])
            for key, value in impostazioni_predefinite.items():
                if key not in impostazioni_correnti:
                    config['IMPOSTAZIONI'][key] = value
        save_config(config)
    else:
        config['IMPOSTAZIONI'] = impostazioni_predefinite
        save_config(config)

    # Carica le coordinate dell'area
    stringa_area = config['IMPOSTAZIONI']['area']
    area = tuple(map(int, stringa_area.split(','))) if stringa_area else None

    # Carica lo schermo
    valore_schermo = config['IMPOSTAZIONI']['schermo']
    
    return config, area, valore_schermo

def save_config(config):
    """Salva la configurazione su file"""
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)

def validate_time(time_str):
    """Convalida e converte la stringa dell'ora in un oggetto datetime"""
    from datetime import datetime
    try:
        if not time_str:
            return None
        oggetto_ora = datetime.strptime(time_str, "%H:%M")
        return datetime.now().replace(hour=oggetto_ora.hour, 
                                      minute=oggetto_ora.minute, 
                                      second=0, 
                                      microsecond=0)
    except ValueError:
        return None