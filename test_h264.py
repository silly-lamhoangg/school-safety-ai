import cv2

output_path = "test_h264.mp4"

fourcc = cv2.VideoWriter_fourcc(*"avc1")

writer = cv2.VideoWriter(
    output_path,
    fourcc,
    30,
    (1280, 720)
)

print("Writer opened:", writer.isOpened())

if writer.isOpened():
    for i in range(90):
        frame = 255 * (i % 2) * (cv2.UMat(720, 1280, cv2.CV_8UC3).get())
        writer.write(frame)

    writer.release()
    print("Da tao video test")
else:
    print("OpenCV chua ho tro ghi H264")