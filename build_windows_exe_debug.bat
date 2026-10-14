@echo off
REM Fejlsøgningsudgave med konsolvindue, så eventuelle fejl kan ses.
setlocal
cd /d "%~dp0"
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --console --name "Blink Buddy DEBUG" --icon blink_buddy.ico --add-data "blink_buddy.ico;." --add-data "frames;frames" blink_buddy.py
pause
