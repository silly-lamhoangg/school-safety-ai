# SCHOOL SAFETY AI

School monitoring dashboard with person tracking and alert evidence capture.

## Windows setup

Use Python 3.13 and run these commands from the project directory:

```powershell
python -m venv venv_local
.\venv_local\Scripts\python.exe -m pip install -r requirements.txt
winget install --id Gyan.FFmpeg --exact --source winget
.\venv_local\Scripts\python.exe .\create_account.py
.\venv_local\Scripts\python.exe .\web_app\app.py
```

Create an account once, then open <http://127.0.0.1:5000>. FFmpeg is discovered
from `PATH`, the WinGet Gyan.FFmpeg installation, or the legacy
`C:\ffmpeg\bin\ffmpeg.exe` location. Set `FFMPEG_PATH` to use another
installation. The YOLO26n model weights are downloaded by Ultralytics when first
needed.

## Releases

`main` contains the newest code. Versioned Git tags (`v1.0`, `v1.1`, ...) mark
releases; the initial repository release is `v1.0`. See [CHANGELOG.md](CHANGELOG.md)
for release notes.
