#!/bin/bash

# Mostra la finestra principale dell'installatore
(
    while true; do
        sleep 1
    done
) | zenity --progress --width=600 --height=500 --title="Installatore per pyDeskREC by MoonDragon" \
    --text="<b>Installatore per pyDeskREC by MoonDragon</b>\n\nVersione: 1.0.0\n\nhttps://github.com/MoonDragon-MD/pyDeskREC\n\nSeguirà l'installazione guidata comprese le dipendenze e scorciatoia sul menù" \
    --no-cancel --auto-close --pulsate &

INSTALLER_PID=$!

# Funzione per mostrare un popup con il comando da eseguire
show_command_popup() {
    zenity --error --width=400 --text="Errore: $1 non trovato.\nEsegui il seguente comando:\n\n<b>$2</b>"
}

# Verifica le dipendenze
if ! zenity --question --width=400 --text="Vuoi verificare e installare le dipendenze?"; then
    INSTALL_DEPENDENCIES=false
else
    INSTALL_DEPENDENCIES=true
fi

if [ "$INSTALL_DEPENDENCIES" = true ]; then
    # Verifica Python3
    if ! command -v python3 &> /dev/null; then
        show_command_popup "Python3" "sudo apt-get install python3"
        kill $INSTALLER_PID
        exit 1
    fi

    # Verifica pip
    if ! command -v pip3 &> /dev/null; then
        show_command_popup "pip3" "sudo apt-get install python3-pip"
        kill $INSTALLER_PID
        exit 1
    fi

    # Verifica ffmpeg
    if ! command -v ffmpeg &> /dev/null; then
        show_command_popup "ffmpeg" "sudo apt-get install ffmpeg"
        kill $INSTALLER_PID
        exit 1
    fi

    # Installa le dipendenze Python
    zenity --info --width=400 --text="Installando le dipendenze Python..."
    pip3 install PySimpleGUI==4.60.5.0 pyautogui opencv-python numpy
fi

# Chiede all'utente dove installare pyDeskREC
INSTALL_DIR=$(zenity --file-selection --directory --title="Seleziona la directory di installazione per pyDeskREC" --width=400)
if [ -z "$INSTALL_DIR" ]; then
    zenity --error --width=400 --text="Nessuna directory selezionata.\nInstallazione annullata."
    kill $INSTALLER_PID
    exit 1
fi

# Crea il desktop entry
zenity --info --width=400 --text="Creando il collegamento nel menu applicazioni..."
cat > ~/.local/share/applications/pydeskrec.desktop << EOL
[Desktop Entry]
Name=pyDeskREC
Comment=Screen Recorder Application
Exec=$INSTALL_DIR/pyDeskREC/pyDeskREC.sh
Icon=$INSTALL_DIR/pyDeskREC/icon.png
Terminal=false
Type=Application
Categories=Utility;AudioVideo;
EOL

# Crea la directory di installazione se non esiste
mkdir -p "$INSTALL_DIR"

# Copia i file necessari
zenity --info --width=400 --text="Installando l'applicazione..."
cp -r pyDeskREC "$INSTALL_DIR/"

# Genera lo script pyDeskREC.sh
cat > "$INSTALL_DIR/pyDeskREC/pyDeskREC.sh" << EOL
#!/bin/bash
cd $INSTALL_DIR/pyDeskREC/
python3 main.py
EOL

# Rende eseguibile lo script pyDeskREC.sh
chmod +x "$INSTALL_DIR/pyDeskREC/pyDeskREC.sh"

# Chiude la finestra principale dell'installatore
kill $INSTALLER_PID

zenity --info --width=400 --text="Installazione completata!"
zenity --info --width=400 --text="Puoi avviare pyDeskREC dal menu delle applicazioni o eseguendo 'pyDeskREC' nel terminale"
