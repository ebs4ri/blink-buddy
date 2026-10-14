#!/bin/bash
# Blink Buddy · Dry Eye: bygger "Blink Buddy.app" til macOS.
# Kør i mappen med blink_buddy.py:  bash build_mac_app.sh
# Kræver Python 3.10+ (python.org eller Homebrew).
set -e
cd "$(dirname "$0")"
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
QT_QPA_PLATFORM=offscreen python3 -c "import sys; from PySide6.QtWidgets import QApplication; a=QApplication(sys.argv); import blink_buddy as b; b.generate_icns('blink_buddy.icns'); print('ikon lavet')"
python3 -m PyInstaller --noconfirm --clean --windowed --name "Blink Buddy" --icon blink_buddy.icns \
  --osx-bundle-identifier dk.dryeye.blinkbuddy \
  --add-data "blink_buddy.ico:." --add-data "frames:frames" blink_buddy.py
# Ingen dock-ikon: appen bor i menulinjen
plutil -replace LSUIElement -bool true "dist/Blink Buddy.app/Contents/Info.plist"
# Zip, der bevarer app-bundtet
ditto -c -k --keepParent "dist/Blink Buddy.app" "dist/Blink-Buddy-mac.zip"
echo
echo "Færdig: dist/Blink Buddy.app  (zip: dist/Blink-Buddy-mac.zip)"
echo "Første gang: højreklik på appen og vælg Åbn (appen er ikke signeret)."
