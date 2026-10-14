@echo off
REM Blink Buddy · Dry Eye: bygger en enkelt .exe til Windows.
REM Kør i mappen med blink_buddy.py. Kræver Python 3.10+ fra python.org.
setlocal
cd /d "%~dp0"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if not exist blink_buddy.ico python -c "import os,sys; os.environ['QT_QPA_PLATFORM']='offscreen'; from PySide6.QtWidgets import QApplication; a=QApplication(sys.argv); import blink_buddy as b; b.generate_icon('blink_buddy.ico'); print('ikon lavet')"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "Blink Buddy" --icon blink_buddy.ico --add-data "blink_buddy.ico;." --add-data "frames;frames" blink_buddy.py
echo.
echo Færdig: dist\Blink Buddy.exe
pause
