#!/bin/bash

# Show the main installer window
(
    while true; do
        sleep 1
    done
) | zenity --progress --width=600 --height=500 --title="Installer for pyDeskREC by MoonDragon" \
    --text="<b>Installer for pyDeskREC by MoonDragon</b>\n\nVersion: 1.0.0\n\nhttps://github.com/MoonDragon-MD/pyDeskREC\n\nFollow the guided installation including dependencies and menu shortcut" \
    --no-cancel --auto-close --pulsate &

INSTALLER_PID=$!

# Function to show a popup with the command to execute
show_command_popup() {
    zenity --error --width=400 --text="Error: $1 not found.\nExecute the following command:\n\n<b>$2</b>"
}

# Verify dependencies
if ! zenity --question --width=400 --text="Do you want to verify and install dependencies?"; then
    INSTALL_DEPENDENCIES=false
else
    INSTALL_DEPENDENCIES=true
fi

if [ "$INSTALL_DEPENDENCIES" = true ]; then
    # Verify Python3
    if ! command -v python3 &> /dev/null; then
        show_command_popup "Python3" "sudo apt-get install python3"
        kill $INSTALLER_PID
        exit 1
    fi

    # Verify pip
    if ! command -v pip3 &> /dev/null; then
        show_command_popup "pip3" "sudo apt-get install python3-pip"
        kill $INSTALLER_PID
        exit 1
    fi

    # Verify ffmpeg
    if ! command -v ffmpeg &> /dev/null; then
        show_command_popup "ffmpeg" "sudo apt-get install ffmpeg"
        kill $INSTALLER_PID
        exit 1
    fi

    # Install Python dependencies
    zenity --info --width=400 --text="Installing Python dependencies..."
    pip3 install PySimpleGUI==4.60.5.0 pyautogui opencv-python numpy
fi

# Ask the user where to install pyDeskREC
INSTALL_DIR=$(zenity --file-selection --directory --title="Select the installation directory for pyDeskREC" --width=400)
if [ -z "$INSTALL_DIR" ]; then
    zenity --error --width=400 --text="No directory selected.\nInstallation canceled."
    kill $INSTALLER_PID
    exit 1
fi

# Create the desktop entry
zenity --info --width=400 --text="Creating the application menu shortcut..."
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

# Create the installation directory if it doesn't exist
mkdir -p "$INSTALL_DIR"

# Copy the necessary files
zenity --info --width=400 --text="Installing the application..."
cp -r pyDeskREC "$INSTALL_DIR/"

# Generate the pyDeskREC.sh script
cat > "$INSTALL_DIR/pyDeskREC/pyDeskREC.sh" << EOL
#!/bin/bash
cd $INSTALL_DIR/pyDeskREC/
python3 main.py
EOL

# Make the pyDeskREC.sh script executable
chmod +x "$INSTALL_DIR/pyDeskREC/pyDeskREC.sh"

# Close the main installer window
kill $INSTALLER_PID

zenity --info --width=400 --text="Installation completed!"
zenity --info --width=400 --text="You can start pyDeskREC from the application menu or by running 'pyDeskREC' in the terminal"