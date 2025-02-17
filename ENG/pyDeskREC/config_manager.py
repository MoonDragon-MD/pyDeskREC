import configparser
import os
import PySimpleGUI as sg

## V 1.0.0 by MoonDragon  - https://github.com/MoonDragon-MD/pyDeskREC

# Configuration constants
CONFIG_FILE = "pyDeskREC.ini"

def load_config():
    """Loads or creates initial configuration"""
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
            # Update existing settings
            current_settings = dict(config['SETTINGS'])
            for key, value in default_settings.items():
                if key not in current_settings:
                    config['SETTINGS'][key] = value
        save_config(config)
    else:
        config['SETTINGS'] = default_settings
        save_config(config)

    # Load area coordinates
    area_string = config['SETTINGS']['area']
    area = tuple(map(int, area_string.split(','))) if area_string else None

    # Load display
    display_value = config['SETTINGS']['display']
    
    return config, area, display_value

def save_config(config):
    """Saves configuration to file"""
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)

def validate_time(time_str):
    """Validates and converts time string to datetime object"""
    from datetime import datetime
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
