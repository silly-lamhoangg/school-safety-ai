import sqlite3
import sys
import time
from pathlib import Path
import importlib.util
import atexit
import subprocess
import threading
from flask_wtf.csrf import CSRFProtect


BASE_DIR = Path(__file__).resolve().parents[1]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Import monitor_state trực tiếp từ đường dẫn tuyệt đối
MONITOR_FILE = BASE_DIR / "monitor_state.py"

spec = importlib.util.spec_from_file_location(
    "monitor_state",
    MONITOR_FILE
)

monitor_state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor_state)

get_status = monitor_state.get_status
send_command = monitor_state.send_command
FRAME_FILE = monitor_state.FRAME_FILE
CONTROL_FILE = monitor_state.CONTROL_FILE

from flask import (
    Flask, render_template, abort, send_file,
    request, redirect, url_for, Response, jsonify,
    session
)

import secrets

from database.database import (
    update_alert_status,
    init_database,
    verify_user
)

app = Flask(__name__)
csrf = CSRFProtect()

# Tao khoa bao mat session va luu lai de khong thay doi khi khoi dong lai
SECRET_KEY_FILE = BASE_DIR / ".flask_secret_key"

if SECRET_KEY_FILE.exists():
    app.secret_key = SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
else:
    app.secret_key = secrets.token_hex(32)
    SECRET_KEY_FILE.write_text(
        app.secret_key,
        encoding="utf-8"
    )

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    SESSION_PERMANENT=False
)
# Kich hoat bao ve CSRF
csrf.init_app(app)

init_database()

# Xác định thư mục gốc của dự án
DB_PATH = BASE_DIR / "database" / "school_safety.db"
VIDEO_DIR = BASE_DIR / "videos"


# Các định dạng video được hỗ trợ
VIDEO_EXTENSIONS = {
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".webm"
}

# ==================================
# QUAN LY AI ENGINE
# ==================================

AI_ENGINE_PROCESS = None

# Dong bo cac thao tac voi tien trinh AI Engine
ENGINE_LOCK = threading.RLock()

# Su dung de dung luong kiem tra khi Flask tat
SHUTDOWN_EVENT = threading.Event()
SHUTTING_DOWN = False

ENGINE_RECOVERY_FAILED = False

# Luu nguon giam sat gan nhat de phuc hoi khi gap su co
LAST_MONITOR_SOURCE = None

# Danh dau phien giam sat da thuc su bat dau hay chua
MONITOR_SESSION_SEEN_ACTIVE = False

# Cau hinh tu phuc hoi
ENGINE_CHECK_INTERVAL = 2
ENGINE_RESTART_DELAY = 3
MAX_RESTART_ATTEMPTS = 3
ENGINE_STABLE_SECONDS = 30

# ==================================
# DANG NHAP VA XAC THUC
# ==================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if session.get("user"):
        return redirect(url_for("dashboard"))

    error = None

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = verify_user(username, password)

        if user:

            session.clear()
            session["user"] = user

            return redirect(url_for("dashboard"))

        error = "Tên đăng nhập hoặc mật khẩu không chính xác!"

    return render_template(
        "login.html",
        error=error
    )


@app.route("/logout", methods=["POST"])
def logout():

    session.clear()

    return redirect(url_for("login"))


# ==================================
# BAO VE TOAN BO TRANG VA API
# ==================================

@app.before_request
def require_login():

    # Cho phep truy cap trang dang nhap va tai nguyen tinh
    if request.endpoint in ("login", "static"):
        return None

    # Neu chua dang nhap
    if not session.get("user"):

        # API tra ve JSON 401
        if request.path.startswith("/api/"):
            return jsonify({
                "success": False,
                "message": "Vui long dang nhap de tiep tuc!"
            }), 401

        # Cac trang khac chuyen ve trang dang nhap
        return redirect(url_for("login"))

    return None

def get_ai_engine_health():
    """
    Kiem tra tinh trang tien trinh AI Engine.
    """

    global AI_ENGINE_PROCESS

    if AI_ENGINE_PROCESS is None:
        return {
            "engine_running": False,
            "engine_pid": None,
            "engine_exit_code": None
        }

    exit_code = AI_ENGINE_PROCESS.poll()

    return {
        "engine_running": exit_code is None,
        "engine_pid": AI_ENGINE_PROCESS.pid,
        "engine_exit_code": exit_code
    }


def start_ai_engine():
    """
    Khoi dong AI Engine neu tien trinh chua chay.
    """

    global AI_ENGINE_PROCESS

    with ENGINE_LOCK:

        if SHUTTING_DOWN:
            print("FLASK DANG TAT, KHONG KHOI DONG AI ENGINE.")
            return

        # Tranh khoi dong trung tien trinh
        if (
            AI_ENGINE_PROCESS is not None
            and AI_ENGINE_PROCESS.poll() is None
        ):
            print("AI ENGINE DA DANG CHAY.")
            return

        # Xoa lenh dieu khien cu
        if CONTROL_FILE.exists():
            CONTROL_FILE.unlink()

        main_file = BASE_DIR / "main.py"

        if not main_file.is_file():
            raise FileNotFoundError(
                f"Khong tim thay main.py: {main_file}"
            )

        print("DANG KHOI DONG AI ENGINE...")

        creation_flags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            if sys.platform == "win32"
            else 0
        )

        AI_ENGINE_PROCESS = subprocess.Popen(
            [sys.executable, str(main_file)],
            cwd=str(BASE_DIR),
            creationflags=creation_flags
        )

        print(
            "AI ENGINE DA KHOI DONG. PID:",
            AI_ENGINE_PROCESS.pid
        )


def stop_ai_engine():
    """
    Dung AI Engine an toan khi Flask tat.
    """

    global AI_ENGINE_PROCESS
    global SHUTTING_DOWN

    # Bao hieu dung luong tu phuc hoi
    SHUTTING_DOWN = True
    SHUTDOWN_EVENT.set()

    with ENGINE_LOCK:

        if AI_ENGINE_PROCESS is None:
            return

        if AI_ENGINE_PROCESS.poll() is not None:
            AI_ENGINE_PROCESS = None
            return

        process = AI_ENGINE_PROCESS
        print("DANG DUNG AI ENGINE...")

        try:
            status = get_status()

            if status.get("state") in ("RUNNING", "STARTING"):

                send_command("STOP")

                timeout = time.monotonic() + 10

                while time.monotonic() < timeout:

                    if process.poll() is not None:
                        AI_ENGINE_PROCESS = None
                        return

                    status = get_status()

                    if status.get("state") == "STOPPED":
                        break

                    time.sleep(0.2)

        except Exception as e:
            print("LOI KHI GUI LENH DUNG:", e)

        try:
            process.terminate()
            process.wait(timeout=5)

        except subprocess.TimeoutExpired:
            print(
                "AI ENGINE KHONG PHAN HOI, "
                "DANG CUONG CHE DUNG."
            )

            process.kill()
            process.wait()

        AI_ENGINE_PROCESS = None
        print("DA DUNG AI ENGINE.")



def monitor_ai_engine():
    """
    Giam sat tien trinh AI Engine va tu dong khoi phuc khi bi loi.
    """

    global LAST_MONITOR_SOURCE
    global MONITOR_SESSION_SEEN_ACTIVE
    global ENGINE_RECOVERY_FAILED

    restart_attempts = 0
    engine_started_at = time.monotonic()
    failure_reported = False

    print("DA BAT CHE DO TU GIAM SAT AI ENGINE.")

    while not SHUTDOWN_EVENT.wait(ENGINE_CHECK_INTERVAL):

        with ENGINE_LOCK:

            if SHUTTING_DOWN:
                break

            health = get_ai_engine_health()
            status = get_status()
            current_state = status.get("state")

            # ==================================
            # AI ENGINE DANG CHAY
            # ==================================

            if health["engine_running"]:

                if current_state in ("RUNNING", "STARTING"):
                    MONITOR_SESSION_SEEN_ACTIVE = True

                elif (
                    current_state == "STOPPED"
                    and MONITOR_SESSION_SEEN_ACTIVE
                ):
                    LAST_MONITOR_SOURCE = None
                    MONITOR_SESSION_SEEN_ACTIVE = False

                # Tien trinh on dinh 30 giay:
                # Dat lai bo dem thu khoi phuc
                if (
                    time.monotonic() - engine_started_at
                    >= ENGINE_STABLE_SECONDS
                ):
                    if restart_attempts > 0:
                        print(
                            "AI ENGINE DA HOAT DONG ON DINH. "
                            "DAT LAI BO DEM PHUC HOI."
                        )

                    restart_attempts = 0
                    failure_reported = False

                continue

            # ==================================
            # AI ENGINE DA DUNG
            # ==================================

            # Neu phien giam sat da ket thuc binh thuong
            if (
                current_state == "STOPPED"
                and MONITOR_SESSION_SEEN_ACTIVE
            ):
                LAST_MONITOR_SOURCE = None
                MONITOR_SESSION_SEEN_ACTIVE = False

            # Da het so lan thu khoi phuc
            if restart_attempts >= MAX_RESTART_ATTEMPTS:
                
                ENGINE_RECOVERY_FAILED = True

                if not failure_reported:
                    print(
                        "PHAT HIEN AI ENGINE DA DUNG BAT THUONG. "
                        "Ma ket thuc:",
                        health["engine_exit_code"]
                    )

                    print(
                        "AI ENGINE KHONG THE TU PHUC HOI "
                        f"SAU {MAX_RESTART_ATTEMPTS} LAN THU."
                    )

                    failure_reported = True

                continue

            print(
                "PHAT HIEN AI ENGINE DA DUNG BAT THUONG. "
                "Ma ket thuc:",
                health["engine_exit_code"]
            )

            next_attempt = restart_attempts + 1

            print(
                "CHUAN BI KHOI DONG LAI AI ENGINE "
                f"LAN {next_attempt}/{MAX_RESTART_ATTEMPTS}..."
            )

        # Cho truoc khi khoi dong lai
        if SHUTDOWN_EVENT.wait(ENGINE_RESTART_DELAY):
            break

        with ENGINE_LOCK:

            if SHUTTING_DOWN:
                break

            # Kiem tra lai tien trinh
            if (
                AI_ENGINE_PROCESS is not None
                and AI_ENGINE_PROCESS.poll() is None
            ):
                continue

            # Cap nhat lai nguon can phuc hoi
            resume_source = (
                LAST_MONITOR_SOURCE.copy()
                if LAST_MONITOR_SOURCE is not None
                else None
            )

            try:
                # Tinh mot lan thu khoi phuc
                restart_attempts += 1

                print(
                    f"DANG THU KHOI DONG LAI "
                    f"LAN {restart_attempts}/{MAX_RESTART_ATTEMPTS}..."
                )

                start_ai_engine()
                ENGINE_RECOVERY_FAILED = False

                # Khoi phuc phien giam sat cu
                if resume_source is not None:

                    command = send_command(
                        "START",
                        source_type=resume_source["source_type"],
                        source=resume_source["source"]
                    )

                    LAST_MONITOR_SOURCE = resume_source.copy()
                    MONITOR_SESSION_SEEN_ACTIVE = False

                    print(
                        "DA GUI LAI LENH GIAM SAT. REQUEST ID:",
                        command["request_id"]
                    )

                engine_started_at = time.monotonic()
                failure_reported = False

                print(
                    "DA KHOI DONG LAI AI ENGINE. "
                    "DANG THEO DOI KHA NANG HOAT DONG."
                )

            except Exception as e:

                print(
                    "LOI KHI KHOI DONG LAI AI ENGINE:",
                    e
                )

                # Neu khong khoi dong duoc thi tiep tuc thu
                # cho den khi dat gioi han

    print("DA DUNG LUONG TU GIAM SAT AI ENGINE.")


def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

# ==================================
# TRANG QUAN LY CAMERA
# ==================================

@app.route("/cameras")
def cameras_page():
    conn = get_db_connection()

    try:
        cameras = conn.execute("""
            SELECT *
            FROM cameras
            ORDER BY id DESC
        """).fetchall()

        return render_template(
            "cameras.html",
            cameras=cameras
        )

    finally:
        conn.close()


# ==================================
# API QUAN LY CAMERA
# ==================================

@app.route("/api/cameras", methods=["GET"])
def get_cameras_api():
    """
    Lay danh sach camera.
    """

    conn = get_db_connection()

    cameras = conn.execute("""
        SELECT *
        FROM cameras
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return jsonify({
        "success": True,
        "total": len(cameras),
        "cameras": [
            dict(camera)
            for camera in cameras
        ]
    })


@app.route("/api/cameras", methods=["POST"])
def add_camera_api():
    """
    Them camera moi.
    """

    data = request.get_json(silent=True) or {}

    name = data.get("name", "").strip()
    location = data.get("location", "").strip()
    source_type = data.get("source_type", "").strip()
    source = data.get("source")

    # Kiem tra ten camera
    if not name:
        return jsonify({
            "success": False,
            "message": "Ten camera khong duoc de trong!"
        }), 400

    # Kiem tra loai nguon
    if source_type not in ("camera", "rtsp"):
        return jsonify({
            "success": False,
            "message": "Loai nguon camera khong hop le!"
        }), 400

    # Kiem tra nguon
    if source is None or str(source).strip() == "":
        return jsonify({
            "success": False,
            "message": "Nguon camera khong duoc de trong!"
        }), 400

    if source_type == "camera":

        try:
            source = int(source)

            if source < 0:
                raise ValueError

        except (ValueError, TypeError):
            return jsonify({
                "success": False,
                "message": "Chi so webcam khong hop le!"
            }), 400

    elif source_type == "rtsp":

        source = str(source).strip()

        if not source.lower().startswith("rtsp://"):
            return jsonify({
                "success": False,
                "message": "Dia chi RTSP khong hop le!"
            }), 400

    conn = get_db_connection()

    try:
        cursor = conn.execute("""
            INSERT INTO cameras (
                name,
                location,
                source_type,
                source
            )
            VALUES (?, ?, ?, ?)
        """, (
            name,
            location,
            source_type,
            str(source)
        ))

        camera_id = cursor.lastrowid

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Them camera thanh cong!",
            "camera_id": camera_id
        }), 201

    except sqlite3.Error as e:

        conn.rollback()

        return jsonify({
            "success": False,
            "message": "Loi database: " + str(e)
        }), 500

    finally:
        conn.close()


# ==================================
# API CHINH SUA CAMERA
# ==================================

@app.route("/api/cameras/<int:camera_id>", methods=["PUT"])
def update_camera_api(camera_id):

    data = request.get_json(silent=True) or {}

    name = data.get("name", "").strip()
    location = data.get("location", "").strip()
    source_type = data.get("source_type", "").strip()
    source = data.get("source")

    if not name:
        return jsonify({
            "success": False,
            "message": "Ten camera khong duoc de trong!"
        }), 400

    if source_type not in ("camera", "rtsp"):
        return jsonify({
            "success": False,
            "message": "Loai nguon camera khong hop le!"
        }), 400

    if source is None or str(source).strip() == "":
        return jsonify({
            "success": False,
            "message": "Nguon camera khong duoc de trong!"
        }), 400

    if source_type == "camera":
        try:
            source = int(source)

            if source < 0:
                raise ValueError

        except (ValueError, TypeError):
            return jsonify({
                "success": False,
                "message": "Chi so webcam khong hop le!"
            }), 400

    else:
        source = str(source).strip()

        if not source.lower().startswith("rtsp://"):
            return jsonify({
                "success": False,
                "message": "Dia chi RTSP khong hop le!"
            }), 400

    conn = get_db_connection()

    try:
        cursor = conn.execute("""
            UPDATE cameras
            SET name = ?,
                location = ?,
                source_type = ?,
                source = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            name,
            location,
            source_type,
            str(source),
            camera_id
        ))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({
                "success": False,
                "message": "Khong tim thay camera!"
            }), 404

        return jsonify({
            "success": True,
            "message": "Cap nhat camera thanh cong!"
        })

    except sqlite3.Error as e:
        conn.rollback()

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

    finally:
        conn.close()


# ==================================
# API XOA CAMERA
# ==================================

@app.route("/api/cameras/<int:camera_id>", methods=["DELETE"])
def delete_camera_api(camera_id):

    conn = get_db_connection()

    try:
        cursor = conn.execute("""
            DELETE FROM cameras
            WHERE id = ?
        """, (camera_id,))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({
                "success": False,
                "message": "Khong tim thay camera!"
            }), 404

        return jsonify({
            "success": True,
            "message": "Xoa camera thanh cong!"
        })

    except sqlite3.Error as e:
        conn.rollback()

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

    finally:
        conn.close()


# ==================================
# API BAT / TAT CAMERA
# ==================================

@app.route(
    "/api/cameras/<int:camera_id>/enabled",
    methods=["PATCH"]
)
def toggle_camera_api(camera_id):

    data = request.get_json(silent=True) or {}

    is_enabled = data.get("is_enabled")

    if not isinstance(is_enabled, bool):
        return jsonify({
            "success": False,
            "message": "is_enabled phai la true hoac false!"
        }), 400

    conn = get_db_connection()

    try:
        cursor = conn.execute("""
            UPDATE cameras
            SET is_enabled = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            1 if is_enabled else 0,
            camera_id
        ))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({
                "success": False,
                "message": "Khong tim thay camera!"
            }), 404

        return jsonify({
            "success": True,
            "message": (
                "Da bat camera!"
                if is_enabled
                else "Da tat camera!"
            )
        })

    except sqlite3.Error as e:
        conn.rollback()

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

    finally:
        conn.close()



def get_available_videos():
    """
    Lấy danh sách video có trong thư mục videos.
    Chỉ lấy các tệp có định dạng được hỗ trợ.
    """
    if not VIDEO_DIR.exists():
        return []

    videos = []

    for file_path in VIDEO_DIR.iterdir():
        if (
            file_path.is_file()
            and file_path.suffix.lower() in VIDEO_EXTENSIONS
        ):
            videos.append(file_path.name)

    return sorted(videos, key=str.lower)

def generate_frames():
    """
    Đọc khung hình mới nhất do AI Engine lưu
    và phát đến trình duyệt bằng MJPEG.
    """
    last_modified = None

    while True:
        try:
            if FRAME_FILE.exists():
                current_modified = FRAME_FILE.stat().st_mtime_ns

                # Chỉ gửi khi có khung hình mới
                if current_modified != last_modified:
                    frame_data = FRAME_FILE.read_bytes()

                    last_modified = current_modified

                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + frame_data
                        + b"\r\n"
                    )

        except (OSError, IOError):
            pass

        time.sleep(0.1)

def get_alert_statistics():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Tong so canh bao
    cursor.execute("SELECT COUNT(*) FROM alerts")
    total_alerts = cursor.fetchone()[0]

    # So canh bao moi
    cursor.execute("""
        SELECT COUNT(*)
        FROM alerts
        WHERE status = 'MOI' OR status IS NULL
    """)
    new_alerts = cursor.fetchone()[0]

    # So canh bao dang kiem tra
    cursor.execute("""
        SELECT COUNT(*)
        FROM alerts
        WHERE status = 'DANG_KIEM_TRA'
    """)
    checking_alerts = cursor.fetchone()[0]

    # So canh bao da xac minh
    cursor.execute("""
        SELECT COUNT(*)
        FROM alerts
        WHERE status = 'DA_XAC_MINH'
    """)
    verified_alerts = cursor.fetchone()[0]

    # So anh minh chung da luu
    cursor.execute("""
        SELECT COUNT(*)
        FROM alerts
        WHERE image_path IS NOT NULL
          AND image_path != ''
    """)
    saved_images = cursor.fetchone()[0]

    conn.close()

    return {
        "total_alerts": total_alerts,
        "new_alerts": new_alerts,
        "checking_alerts": checking_alerts,
        "verified_alerts": verified_alerts,
        "saved_images": saved_images
    }

def get_daily_alert_statistics():
    conn = get_db_connection()

    rows = conn.execute("""
        WITH RECURSIVE days(day) AS (
            SELECT date('now', '-6 days')

            UNION ALL

            SELECT date(day, '+1 day')
            FROM days
            WHERE day < date('now')
        )

        SELECT
            strftime('%d/%m', days.day) AS label,
            COUNT(alerts.id) AS total
        FROM days
        LEFT JOIN alerts
            ON date(alerts.created_at) = days.day
        GROUP BY days.day
        ORDER BY days.day
    """).fetchall()

    conn.close()

    daily_alerts = [
        {
            "label": row["label"],
            "total": row["total"]
        }
        for row in rows
    ]

    max_total = max(
        (item["total"] for item in daily_alerts),
        default=0
    )

    for item in daily_alerts:
        if max_total > 0:
            item["height"] = max(
                5,
                item["total"] / max_total * 100
            )
        else:
            item["height"] = 0

    return daily_alerts

def get_recent_alerts(limit=5):
    conn = get_db_connection()

    alerts = conn.execute("""
        SELECT *
        FROM alerts
        ORDER BY id DESC
        LIMIT ?
    """, (limit,)).fetchall()

    conn.close()
    return alerts


@app.route("/")
def dashboard():
    statistics = get_alert_statistics()
    recent_alerts = get_recent_alerts(5)
    daily_alerts = get_daily_alert_statistics()
    available_videos = get_available_videos()
    
    print("BASE_DIR:", BASE_DIR)
    print("VIDEO_DIR:", VIDEO_DIR)
    print("DANH SACH VIDEO:", available_videos) 

    return render_template(
        "dashboard.html",
        statistics=statistics,
        recent_alerts=recent_alerts,
        daily_alerts=daily_alerts,
        available_videos=available_videos
    )


@app.route("/alerts")
def alerts_page():

    # Nhận thông tin tìm kiếm và bộ lọc
    status = request.args.get("status", "ALL")
    alert_type = request.args.get("alert_type", "ALL")
    search_query = request.args.get("q", "").strip()

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    per_page = 10
    offset = (page - 1) * per_page

    allowed_status = [
        "ALL",
        "MOI",
        "DANG_KIEM_TRA",
        "DA_XAC_MINH"
    ]

    if status not in allowed_status:
        status = "ALL"

    conn = get_db_connection()

    # Lấy danh sách các loại cảnh báo
    alert_types = conn.execute("""
        SELECT DISTINCT alert_type
        FROM alerts
        WHERE alert_type IS NOT NULL
          AND alert_type != ''
        ORDER BY alert_type
    """).fetchall()

    alert_types = [row["alert_type"] for row in alert_types]

    # Xây dựng điều kiện truy vấn
    conditions = []
    params = []

    if status == "MOI":
        conditions.append("(status = ? OR status IS NULL)")
        params.append("MOI")

    elif status != "ALL":
        conditions.append("status = ?")
        params.append(status)

    if alert_type != "ALL":
        conditions.append("alert_type = ?")
        params.append(alert_type)

    if search_query:
        keyword = f"%{search_query}%"

        conditions.append("""
            (
                CAST(id AS TEXT) LIKE ?
                OR video_name LIKE ?
                OR alert_type LIKE ?
                OR reason LIKE ?
                OR CAST(person_id_1 AS TEXT) LIKE ?
                OR CAST(person_id_2 AS TEXT) LIKE ?
            )
        """)

        params.extend([keyword] * 6)

    where_clause = ""

    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # Đếm tổng số kết quả phù hợp
    count_sql = f"""
        SELECT COUNT(*)
        FROM alerts
        {where_clause}
    """

    total_alerts = conn.execute(
        count_sql, params
    ).fetchone()[0]

    # Tính tổng số trang
    total_pages = max(
        1,
        (total_alerts + per_page - 1) // per_page
    )

    if page > total_pages:
        page = total_pages
        offset = (page - 1) * per_page

    # Lấy dữ liệu của trang hiện tại
    query_sql = f"""
        SELECT *
        FROM alerts
        {where_clause}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """

    alerts = conn.execute(
        query_sql,
        params + [per_page, offset]
    ).fetchall()

    conn.close()

    return render_template(
        "alerts.html",
        alerts=alerts,
        selected_status=status,
        selected_type=alert_type,
        search_query=search_query,
        alert_types=alert_types,
        total_alerts=total_alerts,
        page=page,
        total_pages=total_pages
    )



@app.route("/alerts/<int:alert_id>")
def alert_detail(alert_id):
    conn = get_db_connection()

    alert = conn.execute("""
        SELECT * FROM alerts WHERE id = ?
    """, (alert_id,)).fetchone()

    conn.close()

    if alert is None:
        abort(404)

    return render_template("alert_detail.html", alert=alert)

@app.route("/alerts/<int:alert_id>/update", methods=["POST"])
def update_alert(alert_id):

    status = request.form.get("status", "").strip()
    handler_note = request.form.get(
        "handler_note", ""
    ).strip()

    handled_by = request.form.get(
        "handled_by", ""
    ).strip()

    allowed_status = [
        "MOI",
        "DANG_KIEM_TRA",
        "DA_XAC_MINH"
    ]

    if status not in allowed_status:
        abort(400)

    updated = update_alert_status(
        alert_id,
        status,
        handler_note,
        handled_by
    )

    if not updated:
        abort(404)

    return redirect(
        url_for("alert_detail", alert_id=alert_id)
    )


@app.route("/evidence/<int:alert_id>/<kind>")
def view_evidence(alert_id, kind):
    if kind not in ("image", "video"):
        abort(404)

    conn = get_db_connection()

    alert = conn.execute("""
        SELECT image_path, clip_path
        FROM alerts
        WHERE id = ?
    """, (alert_id,)).fetchone()

    conn.close()

    if alert is None:
        abort(404)

    relative_path = (
        alert["image_path"] if kind == "image"
        else alert["clip_path"]
    )

    if not relative_path:
        abort(404)

    file_path = (BASE_DIR / relative_path).resolve()

    # Chỉ cho phép truy cập tệp nằm trong thư mục dự án
    try:
        file_path.relative_to(BASE_DIR.resolve())
    except ValueError:
        abort(403)

    if not file_path.is_file():
        abort(404)

    if kind == "video":
        response = send_file(
            file_path,
            mimetype="video/mp4",
            conditional=True
        )

        response.headers["Accept-Ranges"] = "bytes"
        response.headers["Cache-Control"] = "no-cache"

        return response

    return send_file(
        file_path,
        mimetype="image/jpeg"
    )

@app.route("/api/monitor-status")
def monitor_status_api():
    """
    API tra ve trang thai AI Engine va tien trinh.
    """

    status = get_status()
    health = get_ai_engine_health()

    result = {
        **status,
        **health,
        "engine_recovery_failed": ENGINE_RECOVERY_FAILED
    }

    if not health["engine_running"] and not SHUTTING_DOWN:

        if ENGINE_RECOVERY_FAILED:
            result["state"] = "ERROR"
            result["error"] = (
                "AI Engine khong the tu phuc hoi "
                f"sau {MAX_RESTART_ATTEMPTS} lan thu."
            )

        else:
            result["state"] = "RECOVERING"
            result["error"] = (
                "AI Engine da dung. "
                "He thong dang thu khoi phuc."
            )

    return jsonify(result)

@app.route("/api/monitor/start", methods=["POST"])
def start_monitor_api():
    global LAST_MONITOR_SOURCE
    global MONITOR_SESSION_SEEN_ACTIVE 
    data = request.get_json(silent=True) or {}

    source_type = data.get("source_type")
    source = data.get("source")

    status = get_status()

    if status.get("state") in ("RUNNING", "STARTING"):
        return jsonify({
            "success": False,
            "message": "AI Engine dang hoat dong!"
        }), 409

    try:
        if source_type == "camera":

            if source is None or str(source).strip() == "":
                raise ValueError("Không có camera khả dụng! Vui lòng thêm hoặc bật camera trước.")

            source = int(source)

            # Kiểm tra camera có tồn tại và đang được bật trong SQLite
            conn = get_db_connection()

            try:
                camera = conn.execute("""
                    SELECT id
                    FROM cameras
                    WHERE source_type = 'camera'
                    AND source = ?
                    AND is_enabled = 1
                    LIMIT 1
                """, (str(source),)).fetchone()

            finally:
                conn.close()

            if camera is None:
                raise ValueError(
                    "Camera không tồn tại hoặc đã bị vô hiệu hóa!"
                )

        elif source_type == "video":
            if not isinstance(source, str) or not source.strip():
                raise ValueError("Chua chon video!")

            # Chỉ cho phép chọn video bên trong thư mục videos
            video_dir = (BASE_DIR / "videos").resolve()
            video_path = (video_dir / source).resolve()

            try:
                video_path.relative_to(video_dir)
            except ValueError:
                raise ValueError("Duong dan video khong hop le!")

            if not video_path.is_file():
                raise ValueError("Khong tim thay video!")

            source = str(video_path)

        elif source_type == "rtsp":

            if not isinstance(source, str) or not source.strip():
                raise ValueError("Chua nhap dia chi RTSP!")

            source = source.strip()

            if not source.lower().startswith(("rtsp://", "rtsps://")):
                raise ValueError(
                    "Dia chi RTSP phai bat dau bang rtsp:// hoac rtsps://!"
                )

            # Kiem tra camera RTSP co ton tai va dang duoc bat trong SQLite
            conn = get_db_connection()

            try:
                camera = conn.execute("""
                    SELECT id
                    FROM cameras
                    WHERE source_type = 'rtsp'
                    AND source = ?
                    AND is_enabled = 1
                    LIMIT 1
                """, (source,)).fetchone()

            finally:
                conn.close()

            if camera is None:
                raise ValueError(
                    "Camera RTSP khong ton tai hoac da bi vo hieu hoa!"
                )

        else:
            raise ValueError("Loai nguon khong hop le!")

        with ENGINE_LOCK:

            health = get_ai_engine_health()

            if not health["engine_running"]:
                return jsonify({
                    "success": False,
                    "message": "AI Engine dang khoi dong lai. Vui long thu lai sau!"
                }), 503

            command = send_command(
                "START",
                source_type=source_type,
                source=source
            )

            # Luu nguon de phuc hoi neu AI Engine gap su co
            LAST_MONITOR_SOURCE = {
                "source_type": source_type,
                "source": source
            }

            MONITOR_SESSION_SEEN_ACTIVE = False

        return jsonify({
            "success": True,
            "message": "Da gui lenh bat dau giam sat!",
            "request_id": command["request_id"]
        })

    except (ValueError, OSError) as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400

@app.route("/api/monitor/stop", methods=["POST"])
def stop_monitor_api():
    global LAST_MONITOR_SOURCE
    global MONITOR_SESSION_SEEN_ACTIVE
    status = get_status()

    if status.get("state") not in ("RUNNING", "STARTING"):
        return jsonify({
            "success": False,
            "message": "AI Engine khong trong trang thai hoat dong!"
        }), 409

    try:
        command = send_command("STOP")

        LAST_MONITOR_SOURCE = None
        MONITOR_SESSION_SEEN_ACTIVE = False

        return jsonify({
            "success": True,
            "message": "Da gui lenh dung giam sat!",
            "request_id": command["request_id"]
        })

    except OSError as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@app.route("/video_feed")
def video_feed():
    """
    Phát hình ảnh giám sát trực tiếp từ AI Engine.
    """
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache"
        }
    )

@app.route("/debug-videos")
def debug_videos():
    return jsonify({
        "base_dir": str(BASE_DIR),
        "video_dir": str(VIDEO_DIR),
        "video_dir_exists": VIDEO_DIR.exists(),
        "video_files": [
            file.name
            for file in VIDEO_DIR.iterdir()
            if file.is_file()
        ] if VIDEO_DIR.exists() else [],
        "available_videos": get_available_videos()
    })

if __name__ == "__main__":

    # Khoi dong AI Engine
    start_ai_engine()

    # Dang ky ham dung AI Engine khi Flask ket thuc
    atexit.register(stop_ai_engine)

    # Khoi dong luong tu giam sat AI Engine
    engine_monitor_thread = threading.Thread(
        target=monitor_ai_engine,
        daemon=False
    )

    engine_monitor_thread.start()

    try:
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=False,
            use_reloader=False
        )

    finally:
        SHUTTING_DOWN = True
        SHUTDOWN_EVENT.set()
        engine_monitor_thread.join()
        stop_ai_engine()