
import cv2
from getpass import getpass

print("=== KIỂM TRA CAMERA EZVIZ H6c ===")

# Nhập địa chỉ RTSP do bạn đã chuẩn bị
rtsp_url = input("Nhập địa chỉ RTSP: ")
print("\nĐang kết nối camera...")

cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

if not cap.isOpened():
    print("KHÔNG THỂ KẾT NỐI CAMERA!")
    print("Kiểm tra lại IP, đường dẫn RTSP, tài khoản và mật khẩu.")
    exit()

print("ĐÃ KẾT NỐI CAMERA!")
print("Đang chờ khung hình...")

while True:
    ret, frame = cap.read()

    if not ret:
        print("Không đọc được khung hình!")
        break

    cv2.imshow("EZVIZ H6c - RTSP TEST", frame)

    # Nhấn Q để thoát
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()

print("Đã kết thúc kiểm tra.")
