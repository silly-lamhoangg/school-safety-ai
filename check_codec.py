import cv2

video_path = r"alerts/clips/test_video_00m13s_20261105_140657_492429.mp4"

cap = cv2.VideoCapture(video_path)

if cap.isOpened():
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))

    codec = "".join(
        chr((fourcc >> (8 * i)) & 0xFF)
        for i in range(4)
    )

    print("Codec:", codec)
    print("FPS:", cap.get(cv2.CAP_PROP_FPS))
    print("Frames:", cap.get(cv2.CAP_PROP_FRAME_COUNT))
else:
    print("Khong mo duoc video")

cap.release()