
from collections import defaultdict, deque
from itertools import combinations
import math
import os


class BehaviorAnalyzer:

    def __init__(self, fps=25):

        self.log_path = "evaluation/behavior_log.txt"

        os.makedirs("evaluation", exist_ok=True)

        # Xoa nhat ky cu khi bat dau phan tich moi
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write("NHAT KY PHAN TICH HANH VI\n")
        
        self.fps = max(float(fps), 1.0)

        # Lich su vi tri tung nguoi
        self.history = defaultdict(
            lambda: deque(maxlen=15)
        )

        # Lich su dau hieu cua tung cap nguoi
        self.pair_history = defaultdict(
            lambda: deque(maxlen=60)
        )

        # Lich su khoang cach cua tung cap
        self.distance_history = defaultdict(
            lambda: deque(maxlen=30)
        )

        # Nguong phan tich - phien ban thu nghiem
        self.close_threshold = 1.3
        self.speed_threshold = 0.7
        self.approach_threshold = 0.3
        self.overlap_threshold = 0.10

        # Thoi gian duy tri dau hieu
        self.required_duration = 0.4

        # Ty le khung hinh co dau hieu bat thuong
        self.required_ratio = 0.6

        # Thoi gian toi thieu giua hai canh bao cua cung mot cap nguoi
        self.cooldown = 15.0

        # Thu nghiem gom cac cap nguoi phat hien gan nhau thanh mot dot canh bao.
        # Neu nhieu cap cung co dau hieu trong 5 giay, chi tao mot canh bao.
        # Can doi chieu video de dieu chinh gia tri nay, tranh bo sot hai su kien gan nhau.
        self.global_alert_cooldown = 5.0
        self.last_global_alert_time = -self.global_alert_cooldown

        self.last_alert = {}

        self.frame_index = 0

    def get_center(self, person):

        cx = (person["x1"] + person["x2"]) / 2
        cy = (person["y1"] + person["y2"]) / 2

        return cx, cy

    def get_height(self, person):

        return max(
            person["y2"] - person["y1"], 1
        )

    def get_distance(self, p1, p2):

        x1, y1 = self.get_center(p1)
        x2, y2 = self.get_center(p2)

        return math.hypot(x2 - x1, y2 - y1)

    def get_iou(self, p1, p2):

        x_left = max(p1["x1"], p2["x1"])
        y_top = max(p1["y1"], p2["y1"])

        x_right = min(p1["x2"], p2["x2"])
        y_bottom = min(p1["y2"], p2["y2"])

        if x_right <= x_left or y_bottom <= y_top:
            return 0.0

        intersection = (
            (x_right - x_left) *
            (y_bottom - y_top)
        )

        area1 = (
            (p1["x2"] - p1["x1"]) *
            (p1["y2"] - p1["y1"])
        )

        area2 = (
            (p2["x2"] - p2["x1"]) *
            (p2["y2"] - p2["y1"])
        )

        union = area1 + area2 - intersection

        return intersection / max(union, 1)

    def update_position(self, people, timestamp):

        for person in people:

            track_id = person["id"]
            cx, cy = self.get_center(person)

            self.history[track_id].append(
                (timestamp, cx, cy)
            )

    def get_velocity(self, track_id, body_height):

        points = self.history[track_id]

        if len(points) < 2:
            return 0.0, 0.0

        current_time, current_x, current_y = points[-1]

        # Tim diem lich su cach thoi diem hien tai
        # it nhat khoang 0.16 giay
        previous = None

        for point in reversed(list(points)[:-1]):

            if current_time - point[0] >= 0.16:
                previous = point
                break

        if previous is None:
            previous = points[0]

        old_time, old_x, old_y = previous

        dt = current_time - old_time

        if dt <= 0:
            return 0.0, 0.0

        vx = (
            (current_x - old_x)
            / dt
            / max(body_height, 1)
        )

        vy = (
            (current_y - old_y)
            / dt
            / max(body_height, 1)
        )

        return vx, vy

    def analyze(self, people):

        self.frame_index += 1

        timestamp = self.frame_index / self.fps

        self.update_position(people, timestamp)

        alerts = []
        pair_metrics = []

        for p1, p2 in combinations(people, 2):

            id1 = p1["id"]
            id2 = p2["id"]

            pair_id = tuple(sorted((id1, id2)))

            distance = self.get_distance(p1, p2)

            avg_height = (
                self.get_height(p1) +
                self.get_height(p2)
            ) / 2

            normalized_distance = (
                distance / max(avg_height, 1)
            )

            vx1, vy1 = self.get_velocity(
                id1, avg_height
            )

            vx2, vy2 = self.get_velocity(
                id2, avg_height
            )

            # Toc do tuong doi
            relative_speed = math.hypot(
                vx1 - vx2,
                vy1 - vy2
            )

            overlap = self.get_iou(p1, p2)

            # Luu khoang cach theo thoi gian
            distance_history = self.distance_history[pair_id]

            distance_history.append(
                (timestamp, normalized_distance)
            )

            # Toc do tiep can:
            # Gia tri duong = hai nguoi dang lai gan nhau
            approach_speed = 0.0

            if len(distance_history) >= 2:

                previous = None

                for point in reversed(list(distance_history)[:-1]):

                    if timestamp - point[0] >= 0.2:
                        previous = point
                        break

                if previous is not None:

                    old_time, old_distance = previous

                    dt = timestamp - old_time

                    if dt > 0:
                        approach_speed = (
                            (old_distance - normalized_distance) / dt
                        )

            # Dieu kien bat thuong:
            # Phai o gan nhau va co chuyen dong tuong doi manh.
            # Dong thoi phai co dau hieu tiep can
            # hoac chong lap khung hinh.
            is_close = normalized_distance < self.close_threshold
            is_fast = relative_speed > self.speed_threshold
            is_approaching = approach_speed > self.approach_threshold
            has_overlap = overlap > self.overlap_threshold

            # Dieu kien phat hien bat thuong
            suspicious = (
                is_close
                and is_fast
                and (is_approaching or has_overlap)
            )

            # Ghi nhan cac cap nguoi gan nhau de kiem tra
            

            history = self.pair_history[pair_id]

            history.append(
                (timestamp, suspicious)
            )

            # Chi giu lich su trong 1.5 giay gan nhat
            while (
                history
                and timestamp - history[0][0] > 1.5
            ):
                history.popleft()

            suspicious_frames = sum(
                1 for _, value in history if value
            )

            total_frames = len(history)

            required_frames = max(
                2,
                int(self.fps * self.required_duration)
            )

            suspicious_ratio = (
                suspicious_frames / total_frames
                if total_frames > 0 else 0
            )

            duration_detected = (
                suspicious_frames >= required_frames
                and suspicious_ratio >= self.required_ratio
            )
            # if is_close:
            #     print(
            #         f"[{timestamp:.1f}s] "
            #         f"ID {id1}-{id2} | "
            #         f"Distance: {normalized_distance:.2f} | "
            #         f"Speed: {relative_speed:.2f} | "
            #         f"Approach: {approach_speed:.2f} | "
            #         f"IoU: {overlap:.2f} | "
            #         f"Close: {is_close} | "
            #         f"Fast: {is_fast} | "
            #         f"Approaching: {is_approaching} | "
            #         f"Overlap: {has_overlap} | "
            #         f"Suspicious: {suspicious} | "
            #         f"Detected: {duration_detected}"
            #     )
            if is_close:

                log_message = (
                    f"[{timestamp:.2f}s] "
                    f"ID {id1}-{id2} | "
                    f"Distance: {normalized_distance:.2f} | "
                    f"Speed: {relative_speed:.2f} | "
                    f"Approach: {approach_speed:.2f} | "
                    f"IoU: {overlap:.2f} | "
                    f"Close: {is_close} | "
                    f"Fast: {is_fast} | "
                    f"Approaching: {is_approaching} | "
                    f"Overlap: {has_overlap} | "
                    f"Suspicious: {suspicious} | "
                    f"Detected: {duration_detected}"
                )

                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(log_message + "\n")
                            

            pair_metrics.append({

                "id1": id1,
                "id2": id2,

                "distance": round(
                    normalized_distance, 2
                ),

                "speed": round(
                    relative_speed, 2
                ),

                "approach_speed": round(
                    approach_speed, 2
                ),

                "overlap": round(overlap, 2),

                "suspicious_frames": suspicious_frames,

                "suspicious_ratio": round(
                    suspicious_ratio, 2
                ),
                "is_close": is_close,
                "is_fast": is_fast,
                "is_approaching": is_approaching,
                "has_overlap": has_overlap,
                "duration_detected": duration_detected,
            })

            # Kiem tra cooldown
            last_time = self.last_alert.get(
                pair_id, -self.cooldown
            )

            if (
                duration_detected
                and timestamp - last_time >= self.cooldown
                and timestamp - self.last_global_alert_time >= self.global_alert_cooldown
            ):

                alerts.append({

                    "type": "CAN_KIEM_TRA",

                    "person_ids": [id1, id2],

                    "time": round(timestamp, 2),

                    "reason": (
                        "Phat hien nhieu dau hieu "
                        "chuyen dong tuong tac bat thuong"
                    )
                })

                self.last_alert[pair_id] = timestamp
                self.last_global_alert_time = timestamp
                if self.frame_index % int(self.fps) == 0:
                    for item in pair_metrics:
                        print(
                            f"[{timestamp:.1f}s] "
                            f"ID {item['id1']}-{item['id2']} | "
                            f"D={item['distance']} | "
                            f"V={item['speed']} | "
                            f"A={item['approach_speed']} | "
                            f"IoU={item['overlap']} | "
                            f"Close={item['is_close']} | "
                            f"Fast={item['is_fast']} | "
                            f"Approach={item['is_approaching']} | "
                            f"Overlap={item['has_overlap']} | "
                            f"Detected={item['duration_detected']}"
                        )

        return alerts, pair_metrics
