import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_processing.ffmpeg import find_ffmpeg


class FindFFmpegTests(unittest.TestCase):
    def test_prefers_configured_executable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "ffmpeg.exe"
            executable.touch()

            with patch.dict(
                os.environ,
                {"FFMPEG_PATH": str(executable)},
                clear=True
            ), patch("video_processing.ffmpeg.shutil.which", return_value=None):
                self.assertEqual(find_ffmpeg(), str(executable))

    def test_finds_winget_install(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = (
                Path(temp_dir)
                / "Microsoft"
                / "WinGet"
                / "Packages"
                / "Gyan.FFmpeg_test"
                / "ffmpeg-test"
                / "bin"
                / "ffmpeg.exe"
            )
            executable.parent.mkdir(parents=True)
            executable.touch()

            with patch.dict(
                os.environ,
                {"LOCALAPPDATA": temp_dir},
                clear=True
            ), patch("video_processing.ffmpeg.shutil.which", return_value=None):
                self.assertEqual(find_ffmpeg(), str(executable))


if __name__ == "__main__":
    unittest.main()
