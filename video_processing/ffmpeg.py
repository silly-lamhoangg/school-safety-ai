import os
import shutil
from pathlib import Path


def find_ffmpeg():
    configured_path = os.environ.get("FFMPEG_PATH")
    if configured_path:
        return configured_path if Path(configured_path).is_file() else None

    path_command = shutil.which("ffmpeg")
    if path_command:
        return path_command

    candidates = [
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
    ]

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        winget_packages = (
            Path(local_app_data)
            / "Microsoft"
            / "WinGet"
            / "Packages"
        )
        candidates.extend(
            winget_packages.glob(
                "Gyan.FFmpeg_*/ffmpeg-*/bin/ffmpeg.exe"
            )
        )

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    return None
