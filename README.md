# Blink Buddy · Dry Eye (desktop-udgave)

Et lille øje, der ligger forrest på skærmen, blinker af sig selv og minder dig om at blinke helt
med faste mellemrum. Velværeværktøj til tørre øjne og skærmarbejde. Ikke medicinsk udstyr.

## Sådan bruges programmet
- Træk øjet med musen. Det husker sin plads.
- Højreklik på øjet (eller på ikonet i systembakken) for menu: Indstillinger, Pause i 1 time, Åbn dryeye.dk, Luk.
- Dobbeltklik åbner Indstillinger: blinkinterval (standard 5 s), påmindelse hvert 15. minut, påmindelsen vises i 6 s, start automatisk med Windows.
- Påmindelsen "Blink helt 5 gange" tæller ned fra 5 og forsvinder af sig selv. Klik på den for at lukke den før tid.

## Kør fra kildekode
    python -m pip install -r requirements.txt
    python blink_buddy.py

## Byg Windows-exe
Dobbeltklik på `build_windows_exe.bat` på en Windows-pc med Python 3.10+ installeret.
Resultatet ligger i `dist\Blink Buddy.exe` (cirka 60-100 MB, fordi Qt følger med).

Alternativ uden Windows-pc: læg mappen i et GitHub-repositorium; `.github/workflows/build.yml` bygger exe-filen
automatisk på GitHubs Windows-maskiner (Actions → seneste kørsel → Artifacts).

## Før offentliggørelse på dryeye.dk
1. Kodesignering. En usigneret exe udløser Windows SmartScreen ("Windows beskyttede din pc"). Køb et
   kodesigneringscertifikat (OV eller EV) til selskabet, og signér med `signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a "dist\Blink Buddy.exe"`.
   Indtil da: skriv på download-siden, at man skal vælge "Flere oplysninger" → "Kør alligevel".
2. Test på en ren Windows 10 og 11.
3. Mac: kør `bash build_mac_app.sh` på en Mac (eller lad GitHub-workflowet bygge). Resultatet er `dist/Blink Buddy.app` og en zip. Appen er ikke signeret, så første gang højreklikkes på den og vælges Åbn. Den bor i menulinjen (intet dock-ikon).

## Filer
- `blink_buddy.py` – hele programmet
- `frames/eye-open.png`, `eye-half.png`, `eye-closed.png` – Dry Eyes tre øjebilleder (åbent, halvt, lukket). Appen blinker ved at tone mellem dem. Udskift filerne, hvis designet ændres (samme udsnit og mål, 708 x 378 px).
- `frames/logo-mark.png` – Dry Eye-logoet til udseendet "Dry Eye-logo" (vælges under Indstillinger)
- `blink_buddy.ico` / `blink_buddy.icns` – ikoner (genereres automatisk ud fra det åbne øje)
- `build_mac_app.sh` – bygger Mac-appen
- `requirements.txt`, `build_windows_exe.bat`, `build_windows_exe_debug.bat`
- `.github/workflows/build.yml` – automatisk bygning til Windows og Mac; et tag `v1.1.0` laver en Release med begge filer

## Indstillinger (version 1.1)
- Udseende: "Øje" (Dry Eyes tegnede øje i tre faser) eller "Dry Eye-logo" (tigerøjet, der blinker).
- Påmindelsens placering: ved øjet, midt på skærmen, i et hjørne, eller hvor du selv har trukket boksen hen. Boksen kan altid trækkes med musen; så huskes stedet.
- "Vis påmindelsen nu" findes både i Indstillinger og i højrekliksmenuen, så placeringen kan afprøves med det samme.
- Start automatisk: Windows (registreringsdatabasen) og Mac (LaunchAgent).
