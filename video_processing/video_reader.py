
import cv2


class VideoReader:

    def __init__(self, source):
        """
        source:
            - Camera: 0, 1, 2...
            - Video: "videos/test_video.mp4"
            - RTSP: "rtsp://user:password@ip:554/..."
        """

        self.video_path = source
        self.pending_frame = None

        self.is_camera = isinstance(source, int)

        self.is_rtsp = (
            isinstance(source, str)
            and source.lower().startswith(
                ("rtsp://", "rtsps://")
            )
        )

        self.cap = self._open_capture()

        if not self.cap.isOpened():
            self.cap.release()
            self.cap = None

            raise ValueError(
                f"Khong the mo nguon video/camera: {source}"
            )

        self._read_metadata()

        self.current_frame = 0

    def _open_capture(self):

        if self.is_rtsp:
            return cv2.VideoCapture(
                self.video_path,
                cv2.CAP_FFMPEG
            )

        return cv2.VideoCapture(self.video_path)

    def _read_metadata(self):

        self.fps = self.cap.get(
            cv2.CAP_PROP_FPS
        )

        self.width = int(
            self.cap.get(
                cv2.CAP_PROP_FRAME_WIDTH
            )
        )

        self.height = int(
            self.cap.get(
                cv2.CAP_PROP_FRAME_HEIGHT
            )
        )

        self.total_frames = int(
            self.cap.get(
                cv2.CAP_PROP_FRAME_COUNT
            )
        )

    def read_frame(self):

        if self.cap is None:
            return False, None

        # Neu co frame da doc khi reconnect thi su dung truoc
        if self.pending_frame is not None:

            frame = self.pending_frame
            self.pending_frame = None

            self.current_frame += 1

            return True, frame

        ret, frame = self.cap.read()

        if ret:
            self.current_frame += 1

        return ret, frame

    def reconnect(self):
        """
        Thu ket noi lai nguon RTSP
        va kiem tra kha nang doc frame thuc te.
        """

        if not self.is_rtsp:
            return False

        # Dong ket noi cu
        if self.cap is not None:
            self.cap.release()
            self.cap = None

        self.pending_frame = None

        try:

            # Mo lai RTSP
            self.cap = self._open_capture()

            if not self.cap.isOpened():
                self.cap.release()
                self.cap = None
                return False

            # Doc thu mot frame de xac nhan ket noi
            ret, frame = self.cap.read()

            if not ret or frame is None:
                self.cap.release()
                self.cap = None
                return False

            # Cap nhat thong tin nguon
            self._read_metadata()

            # Giu lai frame dau tien
            self.pending_frame = frame

            print("DA KET NOI LAI CAMERA RTSP!")

            return True

        except Exception as e:

            print("LOI KET NOI LAI RTSP:", e)

            if self.cap is not None:
                self.cap.release()
                self.cap = None

            return False

    def get_info(self):

        return {
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "total_frames": self.total_frames
        }

    def release(self):

        if self.cap is not None:
            self.cap.release()
            self.cap = None
