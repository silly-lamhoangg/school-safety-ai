from ultralytics import YOLO
import cv2


class PersonTracker:

    def __init__(self, model_path="yolo26n.pt"):
        self.model = YOLO(model_path)
        self.confidence = 0.4

    def track(self, frame):

        results = self.model.track(
            source=frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0],
            conf=self.confidence,
            imgsz=640,
            verbose=False
        )

        result = results[0]
        output = frame.copy()
        people = []

        if result.boxes is not None:
            boxes = result.boxes

            if boxes.id is not None:

                ids = boxes.id.cpu().tolist()
                coordinates = boxes.xyxy.cpu().tolist()
                confidences = boxes.conf.cpu().tolist()

                for box, track_id, conf in zip(
                    coordinates, ids, confidences
                ):

                    x1, y1, x2, y2 = map(int, box)
                    track_id = int(track_id)

                    people.append({
                        "id": track_id,
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "confidence": float(conf)
                    })

                    # Vẽ khung bao màu xanh
                    cv2.rectangle(
                        output,
                        (x1, y1),
                        (x2, y2),
                        (0, 255, 0),
                        2
                    )

                    # Hiển thị ID và độ tin cậy
                    label = f"ID: {track_id} | {conf:.2f}"

                    cv2.putText(
                        output,
                        label,
                        (x1, max(y1 - 10, 20)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 0),
                        2
                    )

        return output, len(people), people