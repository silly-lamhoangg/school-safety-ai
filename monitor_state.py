
import cv2
import json
import os
import time
import uuid

from pathlib import Path
from datetime import datetime


# Thư mục gốc dự án
BASE_DIR = Path(__file__).resolve().parent

# Thư mục runtime
RUNTIME_DIR = BASE_DIR / "runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

STATUS_FILE = RUNTIME_DIR / "status.json"
FRAME_FILE = RUNTIME_DIR / "latest_frame.jpg"
CONTROL_FILE = RUNTIME_DIR / "control.json"


# ==================================
# 1. CAP NHAT TRANG THAI
# ==================================

def update_status(state="STOPPED", source="",
                  person_count=0, video_time=0,
                  alert_count=0, error="",
                  camera_connection_status=None):

        # Giữ trạng thái kết nối camera trước đó
    if camera_connection_status is None:
        try:
            if STATUS_FILE.exists():
                old_data = json.loads(
                    STATUS_FILE.read_text(encoding="utf-8")
                )

                camera_connection_status = old_data.get(
                    "camera_connection_status",
                    "UNKNOWN"
                )
            else:
                camera_connection_status = "UNKNOWN"

        except (OSError, json.JSONDecodeError):
            camera_connection_status = "UNKNOWN"

    data = {
        "state": state,
        "source": str(source),
        "person_count": person_count,
        "video_time": round(float(video_time), 2),
        "alert_count": alert_count,
        "error": error,
        "camera_connection_status": camera_connection_status,
        "updated_at": datetime.now().isoformat(
            timespec="seconds"
        ),
    }

    temp_file = RUNTIME_DIR / (
        f"status_{os.getpid()}.tmp"
    )

    temp_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=4),
        encoding="utf-8"
    )

    for attempt in range(5):
        try:
            os.replace(temp_file, STATUS_FILE)
            return True

        except PermissionError:
            if attempt == 4:
                raise

            time.sleep(0.1)

    return False


# ==================================
# 2. CAP NHAT KHUNG HINH
# ==================================

def update_frame(frame):

    success, encoded = cv2.imencode(
        ".jpg",
        frame,
        [cv2.IMWRITE_JPEG_QUALITY, 80]
    )

    if not success:
        return False

    temp_file = RUNTIME_DIR / (
        f"frame_{os.getpid()}.tmp"
    )

    temp_file.write_bytes(encoded.tobytes())

    for attempt in range(5):
        try:
            os.replace(temp_file, FRAME_FILE)
            return True

        except PermissionError:
            if attempt == 4:
                raise

            time.sleep(0.1)

    return False


# ==================================
# 3. GUI LENH DIEU KHIEN
# ==================================

def send_command(command, source_type=None, source=None):

    command = command.upper()

    if command not in ("START", "STOP"):
        raise ValueError("Lenh dieu khien khong hop le!")

    if command == "START":

        if source_type not in ("video", "camera", "rtsp"):
            raise ValueError("Loai nguon khong hop le!")

        if source is None:
            raise ValueError("Chua chon nguon dau vao!")

        if source_type == "camera":
            if not isinstance(source, int) or source < 0:
                raise ValueError("Chi so camera khong hop le!")

        elif source_type == "video":
            if not isinstance(source, str) or not source.strip():
                raise ValueError("Duong dan video khong hop le!")

        elif source_type == "rtsp":
            if not isinstance(source, str) or not source.strip():
                raise ValueError("Dia chi RTSP khong hop le!")

            if not source.lower().startswith(("rtsp://", "rtsps://")):
                raise ValueError("Dia chi RTSP khong hop le!")

    data = {
        "request_id": str(uuid.uuid4()),
        "command": command,
        "source_type": source_type,
        "source": source,
        "created_at": datetime.now().isoformat(
            timespec="seconds"
        )
    }

    temp_file = RUNTIME_DIR / (
        f"control_{os.getpid()}.tmp"
    )

    temp_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=4),
        encoding="utf-8"
    )

    for attempt in range(5):
        try:
            os.replace(temp_file, CONTROL_FILE)
            return data

        except PermissionError:
            if attempt == 4:
                raise

            time.sleep(0.1)

    return None
# ==================================
# 4. DOC LENH MOI
# ==================================

def get_command(last_request_id=None):

    if not CONTROL_FILE.exists():
        return None

    try:
        data = json.loads(
            CONTROL_FILE.read_text(encoding="utf-8")
        )

        request_id = data.get("request_id")

        if not request_id:
            return None

        # Khong xu ly lai lenh cu
        if request_id == last_request_id:
            return None

        return data

    except (OSError, json.JSONDecodeError):
        return None


# ==================================
# 5. DOC TRANG THAI
# ==================================

def get_status():

    if not STATUS_FILE.exists():
        return {
            "state": "STOPPED",
            "source": "",
            "person_count": 0,
            "video_time": 0,
            "alert_count": 0,
            "error": "",
            "camera_connection_status": "UNKNOWN",
            "updated_at": None
        }

    try:
        return json.loads(
            STATUS_FILE.read_text(encoding="utf-8")
        )

    except (OSError, json.JSONDecodeError):
        return {
            "state": "UNKNOWN",
            "source": "",
            "person_count": 0,
            "video_time": 0,
            "alert_count": 0,
            "error": "",
            "camera_connection_status": "UNKNOWN",
            "updated_at": None
        }
