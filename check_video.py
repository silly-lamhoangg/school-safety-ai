import cv2
from pathlib import Path

video_path = Path(
    r"alerts/clips/test_video_00m13s_20261105_140657_492429.mp4"
)

print("File ton tai:", video_path.exists())

if video_path.exists():
    print("Dung luong:", video_path.stat().st_size, "bytes")

    cap = cv2.VideoCapture(str(video_path))

    print("Mo video:", cap.isOpened())

    if cap.isOpened():
        print("So frame:", cap.get(cv2.CAP_PROP_FRAME_COUNT))
        print("FPS:", cap.get(cv2.CAP_PROP_FPS))
        print("Chieu rong:", cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        print("Chieu cao:", cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        ret, frame = cap.read()
        print("Doc duoc frame dau tien:", ret)

        if ret:
            cv2.imwrite("check_frame.jpg", frame)
            print("Da luu check_frame.jpg")

    cap.release()