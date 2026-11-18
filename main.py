
import cv2
import os
import time
import subprocess

from collections import deque
from datetime import datetime

from video_processing.video_reader import VideoReader
from ai_engine.tracker import PersonTracker
from ai_engine.behavior_analyzer import BehaviorAnalyzer

from database.database import init_database, save_alert
from video_processing.ffmpeg import find_ffmpeg
from monitor_state import (
    update_status,
    update_frame,
    get_command
)


# ==================================
# 1. CAU HINH
# ==================================

IMAGE_DIR = "alerts/images"
CLIP_DIR = "alerts/clips"

PRE_SECONDS = 5
POST_SECONDS = 5

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(CLIP_DIR, exist_ok=True)


# ==================================
# 2. KHOI TAO HE THONG
# ==================================

init_database()

# ==================================
# 3. CAC HAM HO TRO
# ==================================

def format_video_time(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}m{secs:02d}s"


def convert_video_to_h264(raw_path, final_path):

    ffmpeg_path = find_ffmpeg()
    if ffmpeg_path is None:
        raise FileNotFoundError(
            "Khong tim thay FFmpeg. Hay cai FFmpeg, them vao PATH "
            "hoac dat bien moi truong FFMPEG_PATH."
        )

    converted_path = final_path.replace(
        ".mp4",
        "_converted.mp4"
    )

    command = [
        ffmpeg_path,
        "-y",
        "-i", raw_path,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-an",
        "-movflags", "+faststart",
        converted_path
    ]

    try:
        print("DANG CHUYEN VIDEO SANG H264...")

        subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True
        )

        if not os.path.isfile(converted_path):
            raise RuntimeError(
                "FFmpeg khong tao duoc video H264!"
            )

        if os.path.getsize(converted_path) == 0:
            raise RuntimeError(
                "Video H264 co dung luong bang 0!"
            )

        os.replace(converted_path, final_path)

        if os.path.exists(raw_path):
            os.remove(raw_path)

        print("DA CHUYEN MA H264 THANH CONG!")
        print("VIDEO MINH CHUNG:", final_path)

        return True

    except Exception as e:
        print("LOI CHUYEN MA H264:", e)

        if os.path.exists(converted_path):
            os.remove(converted_path)

        # Giu video goc neu FFmpeg that bai
        if os.path.exists(raw_path):
            os.replace(raw_path, final_path)
            print("DA GIU VIDEO GOC.")

        return False


# ==================================
# 4. XU LY MOT PHIEN GIAM SAT
# ==================================

def process_session(source, source_type, source_name):

    video = None
    pending_events = []

    try:
        print("DANG MO NGUON:", source_name)

        # Thong bao dang ket noi RTSP
        if source_type == "rtsp":
            update_status(
                state="STARTING",
                source=source_name,
                camera_connection_status="CONNECTING"
            )

        # Mo video hoac camera
        video = VideoReader(source)

        # Mo nguon thanh cong
        if source_type == "rtsp":
            update_status(
                state="STARTING",
                source=source_name,
                camera_connection_status="CONNECTED"
            )

        info = video.get_info()

        fps = info["fps"]

        if not fps or fps <= 0:
            fps = 25

        width = info["width"]
        height = info["height"]

        if width <= 0 or height <= 0:
            raise RuntimeError(
                "Khong doc duoc kich thuoc nguon video!"
            )

        # Khoi tao AI theo tung phien
        tracker = PersonTracker("yolo26n.pt")
        analyzer = BehaviorAnalyzer(fps)

        pre_buffer = deque(
            maxlen=max(1, int(fps * PRE_SECONDS))
        )

        frame_index = 0
        alert_count = 0

        print("BAT DAU GIAM SAT:", source_name)

        update_status(
            state="RUNNING",
            source=source_name,
            person_count=0,
            video_time=0,
            alert_count=0
        )

        # ----------------------------------
        # HAM TAO VIDEO MINH CHUNG
        # ----------------------------------

        def create_event_writer(clip_path):

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")

            writer = cv2.VideoWriter(
                clip_path,
                fourcc,
                fps,
                (width, height)
            )

            if not writer.isOpened():
                writer.release()
                raise RuntimeError(
                    "Khong the tao file video su kien!"
                )

            return writer

        # ----------------------------------
        # HAM KET THUC SU KIEN
        # ----------------------------------

        def finalize_event(event):

            event["writer"].release()

            raw_path = event["raw_path"]
            final_path = event["final_path"]

            if not os.path.exists(raw_path):
                print("KHONG TIM THAY VIDEO TAM:", raw_path)
                return

            convert_video_to_h264(
                raw_path,
                final_path
            )

        # ----------------------------------
        # VONG LAP PHAN TICH
        # ----------------------------------

        running = True

        while running:

            # Kiem tra lenh tu Dashboard
            command_data = get_command(
                process_session.last_request_id
            )

            if command_data:

                process_session.last_request_id = (
                    command_data.get("request_id")
                )

                if command_data.get("command") == "STOP":
                    print("NHAN LENH DUNG TU DASHBOARD!")
                    break

                # Neu nhan START khi dang chay thi bo qua
                # Khong mo them mot nguon moi.

            ret, frame = video.read_frame()

            if not ret:

                if source_type == "rtsp":

                    print("MAT KET NOI CAMERA RTSP!")

                    update_status(
                        state="RUNNING",
                        source=source_name,
                        person_count=0,
                        video_time=frame_index / fps,
                        alert_count=alert_count,
                        error="Mat ket noi camera RTSP!",
                        camera_connection_status="DISCONNECTED"
                    )

                    print("BAT DAU THU KET NOI LAI...")

                    stop_requested = False

                    while True:

                        # Thu ket noi lai camera
                        if video.reconnect():

                            print("CAMERA RTSP DA KET NOI TRO LAI!")

                            update_status(
                                state="RUNNING",
                                source=source_name,
                                person_count=0,
                                video_time=frame_index / fps,
                                alert_count=alert_count,
                                error="",
                                camera_connection_status="CONNECTED"
                            )

                            break

                        print("KET NOI THAT BAI - SE THU LAI SAU 5 GIAY.")

                        # Cho 5 giay, dong thoi kiem tra lenh STOP
                        for _ in range(10):

                            command_data = get_command(
                                process_session.last_request_id
                            )

                            if command_data:

                                process_session.last_request_id = (
                                    command_data.get("request_id")
                                )

                                if command_data.get("command") == "STOP":

                                    print("NHAN LENH DUNG KHI DANG KET NOI LAI!")

                                    stop_requested = True
                                    break

                            time.sleep(0.5)

                        if stop_requested:
                            break

                    if stop_requested:
                        break

                    # Da ket noi lai, tiep tuc vong lap doc frame
                    continue

                else:
                    print("DA KET THUC NGUON VIDEO.")
                    break

            frame_index += 1

            # Phat hien va theo doi doi tuong
            output, person_count, people = tracker.track(frame)

            # Phan tich hanh vi
            alerts, metrics = analyzer.analyze(people)

            if frame_index % max(1, int(fps)) == 0:
                print(
                    f"Thoi gian: {frame_index / fps:.1f}s | "
                    f"So nguoi: {person_count} | "
                    f"So canh bao: {len(alerts)} | "
                    f"So cap phan tich: {len(metrics)}"
                )

            # Hien thi so nguoi
            cv2.putText(
                output,
                f"Person count: {person_count}",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 0),
                2
            )

            # ----------------------------------
            # XU LY CANH BAO
            # ----------------------------------

            for i, alert in enumerate(alerts):

                now = datetime.now()

                video_time = frame_index / fps
                video_time_name = format_video_time(
                    video_time
                )

                timestamp = now.strftime(
                    "%Y%m%d_%H%M%S_%f"
                )

                file_name = (
                    f"{os.path.splitext(source_name)[0]}_"
                    f"{video_time_name}_{timestamp}"
                )

                image_path = os.path.join(
                    IMAGE_DIR,
                    file_name + ".jpg"
                )

                clip_path = os.path.join(
                    CLIP_DIR,
                    file_name + ".mp4"
                )

                raw_clip_path = os.path.join(
                    CLIP_DIR,
                    file_name + "_raw.mp4"
                )

                alert["created_at"] = now.isoformat(
                    timespec="seconds"
                )

                # Luu anh canh bao
                cv2.imwrite(image_path, output)

                # Tao video tam
                writer = create_event_writer(
                    raw_clip_path
                )

                # Ghi 5 giay truoc canh bao
                for old_frame in pre_buffer:
                    writer.write(old_frame)

                # Luu vao SQLite
                save_alert(
                    alert,
                    image_path,
                    clip_path,
                    source_name
                )

                pending_events.append({
                    "writer": writer,
                    "raw_path": raw_clip_path,
                    "final_path": clip_path,
                    "remaining_frames": int(
                        fps * POST_SECONDS
                    )
                })

                alert_count += 1

                message = (
                    f"CAN KIEM TRA: "
                    f"ID {alert['person_ids'][0]} - "
                    f"ID {alert['person_ids'][1]}"
                )

                cv2.putText(
                    output,
                    message,
                    (20, 80 + i * 35),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2
                )

                print("CANH BAO:", alert)
                print("DA LUU ANH:", image_path)

            # ----------------------------------
            # GHI VIDEO SAU CANH BAO
            # ----------------------------------

            for event in pending_events[:]:

                event["writer"].write(output)
                event["remaining_frames"] -= 1

                if event["remaining_frames"] <= 0:

                    finalize_event(event)
                    pending_events.remove(event)

                    print("DA HOAN TAT VIDEO SU KIEN!")

            # ----------------------------------
            # CAP NHAT DASHBOARD
            # ----------------------------------

            current_video_time = frame_index / fps

            update_status(
                state="RUNNING",
                source=source_name,
                person_count=person_count,
                video_time=current_video_time,
                alert_count=alert_count
            )

            # Cap nhat anh khoang 5 lan/giay
            if frame_index % max(1, int(fps / 5)) == 0:
                update_frame(output)

            pre_buffer.append(output.copy())

            # Hien thi tren may chay AI
            cv2.imshow(
                "SCHOOL SAFETY AI - ALERT SYSTEM",
                output
            )

            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("DUNG BANG PHIM Q.")
                break

    except Exception as e:

        print("LOI PHIEN GIAM SAT:", e)

        if source_type == "rtsp":

            update_status(
                state="ERROR",
                source=source_name,
                error=str(e),
                camera_connection_status="DISCONNECTED"
            )

        else:

            update_status(
                state="ERROR",
                source=source_name,
                error=str(e)
            )

    finally:

        # Hoan tat cac clip dang ghi
        for event in pending_events[:]:

            try:
                finalize_event(event)

            except Exception as e:
                print("LOI KHI DONG VIDEO:", e)

        if video is not None:
            video.release()

        cv2.destroyAllWindows()

        print("DA GIAI PHONG NGUON:", source_name)


# Thuoc tinh dung de ghi nho lenh da xu ly
process_session.last_request_id = None


# ==================================
# 5. VONG LAP CHO LENH
# ==================================

def main():

    print("=" * 50)
    print("SCHOOL SAFETY AI")
    print("AI ENGINE DANG CHO LENH...")
    print("=" * 50)

    update_status(
        state="STOPPED",
        source="",
        person_count=0,
        video_time=0,
        alert_count=0
    )

    last_request_id = None

    try:

        while True:

            command_data = get_command(
                last_request_id
            )

            if not command_data:
                time.sleep(0.3)
                continue

            last_request_id = command_data.get(
                "request_id"
            )

            command = command_data.get("command")

            if command != "START":
                continue

            source_type = command_data.get(
                "source_type"
            )

            source = command_data.get("source")

            if source_type == "camera":

                try:
                    source = int(source)

                    if source < 0:
                        raise ValueError(
                            "Chi so camera khong hop le!"
                        )

                except (ValueError, TypeError):
                    update_status(
                        state="ERROR",
                        error="Chi so camera khong hop le!"
                    )
                    continue

                source_name = f"Camera_{source}"

            elif source_type == "video":

                if not isinstance(source, str) or not source:
                    update_status(
                        state="ERROR",
                        error="Duong dan video khong hop le!"
                    )
                    continue

                if not os.path.isfile(source):
                    update_status(
                        state="ERROR",
                        source=source,
                        error="Khong tim thay video!"
                    )
                    continue

                source_name = os.path.basename(source)

            elif source_type == "rtsp":

                if not isinstance(source, str) or not source.strip():
                    update_status(
                        state="ERROR",
                        error="Dia chi RTSP khong hop le!"
                    )
                    continue

                source = source.strip()

                if not source.lower().startswith(
                    ("rtsp://", "rtsps://")
                ):
                    update_status(
                        state="ERROR",
                        error="Dia chi RTSP phai bat dau bang rtsp:// hoac rtsps://!"
                    )
                    continue

                source_name = "Camera_RTSP"

            else:
                update_status(
                    state="ERROR",
                    error="Loai nguon khong hop le!"
                )
                continue

            # Bao hieu dang khoi dong
            update_status(
                state="STARTING",
                source=source_name,
                person_count=0,
                video_time=0,
                alert_count=0
            )

            # Chuyen lenh da xu ly sang phien
            process_session.last_request_id = last_request_id

            process_session(
                source,
                source_type,
                source_name
            )

            # Cap nhat ID lenh moi nhat sau phien
            last_request_id = (
                process_session.last_request_id
            )

            # Xac dinh trang thai ket noi sau khi ket thuc phien
            camera_status = None

            if source_type == "rtsp":
                from monitor_state import get_status

                current_status = get_status()

                camera_status = current_status.get(
                    "camera_connection_status",
                    "UNKNOWN"
                )

                # Neu camera van ket noi thi day la truong hop dung chu dong
                if camera_status == "CONNECTED":
                    camera_status = "NOT_MONITORING"

            # Tro ve trang thai cho
            update_status(
                state="STOPPED",
                source=source_name,
                person_count=0,
                video_time=0,
                alert_count=0,
                camera_connection_status=camera_status
            )

            print("AI ENGINE TRO VE TRANG THAI CHO LENH.")

    except KeyboardInterrupt:

        print("NHAN CTRL+C - DANG DUNG AI ENGINE.")

    finally:

        update_status(
            state="STOPPED",
            source="",
            person_count=0,
            video_time=0,
            alert_count=0
        )

        cv2.destroyAllWindows()

        print("DA DUNG AI ENGINE.")


if __name__ == "__main__":
    main()
