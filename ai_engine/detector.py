
from ultralytics import YOLO
import cv2


class PersonDetector:

    def __init__(self, model_path="yolo26n.pt"):
        # Tai mo hinh YOLO
        self.model = YOLO(model_path)

        # Nguong do tin cay
        self.confidence = 0.4

    def detect(self, frame):

        # Nhan dien doi tuong trong frame
        results = self.model.predict(
            source=frame,
            classes=[0],       # Chi nhan dien nguoi
            conf=self.confidence,
            imgsz=640,
            verbose=False
        )

        result = results[0]

        # Sao chep frame de ve ket qua
        output = frame.copy()

        person_count = 0

        if result.boxes is not None:

            for box in result.boxes:

                # Lay toa do khung bao
                x1, y1, x2, y2 = map(
                    int,
                    box.xyxy[0].cpu().tolist()
                )

                # Lay do tin cay
                confidence = float(box.conf[0])

                person_count += 1

                # Ve khung bao quanh nguoi
                cv2.rectangle(
                    output,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 0),
                    2
                )

                # Hien thi nhan va do tin cay
                label = f"Person: {confidence:.2f}"

                cv2.putText(
                    output,
                    label,
                    (x1, max(y1 - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2
                )

        return output, person_count
