
import sqlite3
import csv
import os
from collections import defaultdict


# Xác định đường dẫn dựa trên vị trí file evaluate.py
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.path.join(BASE_DIR, "database", "school_safety.db")
LABEL_PATH = os.path.join(BASE_DIR, "evaluation", "ground_truth.csv")

# Cho phép cảnh báo xuất hiện trong tình huống
# hoặc tối đa 2 giây sau khi tình huống kết thúc.
TOLERANCE_AFTER = 2.0

# Khoảng cách tối đa giữa hai cảnh báo để gom thành một đợt.
# Có thể điều chỉnh sau khi kiểm tra nhiều video.
ALERT_GAP = 3.0


def load_ground_truth():

    videos = defaultdict(lambda: {
        "duration": 0,
        "events": []
    })

    with open(LABEL_PATH, "r", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            name = row["video_name"].strip()
            duration = float(row["duration_seconds"])

            videos[name]["duration"] = duration

            start = row["event_start"].strip()
            end = row["event_end"].strip()

            if start and end:

                start = float(start)
                end = float(end)

                if start > end:
                    raise ValueError(
                        f"Thoi diem bat dau lon hon ket thuc: {name}"
                    )

                videos[name]["events"].append({
                    "start": start,
                    "end": end
                })

    return videos


def load_alerts():

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT video_name, video_time
        FROM alerts
        WHERE video_name IS NOT NULL
        ORDER BY video_name, video_time
    """)

    rows = cursor.fetchall()
    conn.close()

    alerts = defaultdict(list)

    for video_name, video_time in rows:

        if video_time is not None:
            alerts[video_name].append(float(video_time))

    return alerts


def group_alerts(alert_times, gap=ALERT_GAP):

    """
    Gom các cảnh báo gần nhau thành từng đợt.
    Trả về danh sách các nhóm, không chỉ lấy thời điểm đầu tiên.
    """

    if not alert_times:
        return []

    alert_times = sorted(alert_times)

    groups = []
    current_group = [alert_times[0]]

    for t in alert_times[1:]:

        if t - current_group[-1] <= gap:
            current_group.append(t)

        else:
            groups.append(current_group)
            current_group = [t]

    groups.append(current_group)

    return groups


def evaluate_video(events, alert_times):

    """
    Đánh giá theo tình huống thực tế:

    - Một tình huống có ít nhất một cảnh báo phù hợp: TP.
    - Một tình huống không có cảnh báo phù hợp: FN.
    - Các cảnh báo nằm trong tình huống đã được ghi nhận
      không bị tính lặp thành FP.
    - Cảnh báo ngoài các tình huống được gom thành đợt;
      mỗi đợt không khớp được tính là một FP.
    """

    matched_alert_indices = set()

    tp = 0
    fn = 0

    # Đối chiếu từng tình huống thực tế
    for event in events:

        start = event["start"]
        end = event["end"] + TOLERANCE_AFTER

        # Tìm các cảnh báo nằm trong khoảng tình huống
        matching_indices = [
            i for i, t in enumerate(alert_times)
            if start <= t <= end
        ]

        if matching_indices:

            tp += 1

            # Đánh dấu tất cả cảnh báo trong tình huống
            # để không tính lặp thành cảnh báo sai.
            matched_alert_indices.update(matching_indices)

        else:
            fn += 1

    # Lấy các cảnh báo nằm ngoài các tình huống thực tế
    unmatched_alerts = [
        t for i, t in enumerate(alert_times)
        if i not in matched_alert_indices
    ]

    # Gom cảnh báo ngoài tình huống thành từng đợt
    false_alert_groups = group_alerts(unmatched_alerts)

    fp = len(false_alert_groups)

    return tp, fp, fn, false_alert_groups


def main():

    if not os.path.exists(LABEL_PATH):
        print("Khong tim thay file ground_truth.csv")
        return

    if not os.path.exists(DB_PATH):
        print("Khong tim thay school_safety.db")
        return

    videos = load_ground_truth()
    alerts = load_alerts()

    total_tp = 0
    total_fp = 0
    total_fn = 0
    total_duration = 0

    print("\n========== KET QUA DANH GIA ==========\n")

    for video_name, data in videos.items():

        events = data["events"]
        alert_times = alerts.get(video_name, [])

        tp, fp, fn, false_groups = evaluate_video(
            events,
            alert_times
        )

        total_tp += tp
        total_fp += fp
        total_fn += fn

        # Mỗi video chỉ cộng thời lượng một lần
        total_duration += data["duration"]

        print("Video:", video_name)
        print("  So tinh huong thuc te:", len(events))
        print("  So canh bao tho:", len(alert_times))
        print("  Phat hien dung:", tp)
        print("  Canh bao sai (theo dot):", fp)
        print("  Bo sot:", fn)

        if false_groups:

            print("  Cac dot canh bao sai:")

            for group in false_groups:

                print(
                    f"    {group[0]:.2f}s - {group[-1]:.2f}s "
                    f"({len(group)} canh bao)"
                )

        print("--------------------------------------")

    precision = (
        total_tp / (total_tp + total_fp)
        if total_tp + total_fp > 0 else 0
    )

    recall = (
        total_tp / (total_tp + total_fn)
        if total_tp + total_fn > 0 else 0
    )

    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall > 0 else 0
    )

    false_alerts_per_hour = (
        total_fp / (total_duration / 3600)
        if total_duration > 0 else 0
    )

    print("\n========== TONG HOP ==========")

    print("TP - Phat hien dung:", total_tp)
    print("FP - Dot canh bao sai:", total_fp)
    print("FN - Bo sot:", total_fn)

    print(f"Precision: {precision:.2%}")
    print(f"Recall: {recall:.2%}")
    print(f"F1-score: {f1:.2%}")

    print(
        f"False Alerts/Hour: "
        f"{false_alerts_per_hour:.2f}"
    )

    print("Tong thoi luong video:", total_duration, "giay")


if __name__ == "__main__":
    main()
