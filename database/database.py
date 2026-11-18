import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash


DB_PATH = "database/school_safety.db"

def get_connection():
    os.makedirs("database", exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_database():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            video_time REAL,
            alert_type TEXT,
            person_id_1 INTEGER,
            person_id_2 INTEGER,
            reason TEXT,
            image_path TEXT,
            clip_path TEXT
        )
    """)

        # Bo sung cot video_name cho database cu
    cursor.execute("PRAGMA table_info(alerts)")
    columns = [row[1] for row in cursor.fetchall()]

    if "video_name" not in columns:
        cursor.execute(
            "ALTER TABLE alerts ADD COLUMN video_name TEXT"
        )

    if "status" not in columns:
        cursor.execute("""
            ALTER TABLE alerts
            ADD COLUMN status TEXT DEFAULT 'MOI'
        """)

    if "handler_note" not in columns:
        cursor.execute("""
            ALTER TABLE alerts
            ADD COLUMN handler_note TEXT DEFAULT ''
        """)

    if "handled_by" not in columns:
        cursor.execute("""
            ALTER TABLE alerts
            ADD COLUMN handled_by TEXT DEFAULT ''
        """)

    if "handled_at" not in columns:
        cursor.execute("""
            ALTER TABLE alerts
            ADD COLUMN handled_at TEXT
        """)

    
    # ==================================
    # TAO BANG QUAN LY CAMERA
    # ==================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cameras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,
            location TEXT DEFAULT '',

            source_type TEXT NOT NULL
                CHECK(source_type IN ('camera', 'rtsp')),

            source TEXT NOT NULL,

            is_enabled INTEGER DEFAULT 1,

            connection_status TEXT DEFAULT 'CHUA_KIEM_TRA',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tao index de tim kiem camera nhanh hon
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cameras_enabled
        ON cameras(is_enabled)
    """)

        # ==================================
    # TAO BANG TAI KHOAN GIAM THI
    # ==================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            full_name TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def save_alert(alert, image_path, clip_path, video_name=""):

    conn = get_connection()

    try:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO alerts (
                created_at,
                video_time,
                alert_type,
                person_id_1,
                person_id_2,
                reason,
                image_path,
                clip_path,
                video_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            alert["created_at"],
            alert["time"],
            alert["type"],
            alert["person_ids"][0],
            alert["person_ids"][1],
            alert["reason"],
            image_path,
            clip_path,
            video_name
        ))

        conn.commit()
        print("DA LUU CANH BAO VAO DATABASE!")

    except Exception as e:
        conn.rollback()
        print("LOI LUU CANH BAO VAO DATABASE:", e)
        raise

    finally:
        conn.close()

def update_alert_status(
    alert_id,
    status,
    handler_note="",
    handled_by=""
):
    allowed_status = [
        "MOI",
        "DANG_KIEM_TRA",
        "DA_XAC_MINH"
    ]

    if status not in allowed_status:
        raise ValueError("Trang thai khong hop le!")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE alerts
        SET status = ?,
            handler_note = ?,
            handled_by = ?,
            handled_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (
        status,
        handler_note,
        handled_by,
        alert_id
    ))

    updated = cursor.rowcount

    conn.commit()
    conn.close()

    return updated > 0

def create_user(username, password, full_name=""):
    """
    Tao tai khoan giam thi.
    Mat khau duoc bam truoc khi luu vao SQLite.
    """

    username = username.strip()
    full_name = full_name.strip()

    if not username or not password:
        raise ValueError("Ten dang nhap va mat khau khong duoc de trong!")

    if len(password) < 8:
        raise ValueError("Mat khau phai co it nhat 8 ky tu!")

    password_hash = generate_password_hash(password)

    conn = get_connection()

    try:
        conn.execute("""
            INSERT INTO users (
                username,
                password_hash,
                full_name
            )
            VALUES (?, ?, ?)
        """, (
            username,
            password_hash,
            full_name
        ))

        conn.commit()
        return True

    except sqlite3.IntegrityError:
        return False

    finally:
        conn.close()


def verify_user(username, password):
    """
    Kiem tra ten dang nhap va mat khau.
    """

    conn = get_connection()

    try:
        user = conn.execute("""
            SELECT id, username, password_hash, full_name
            FROM users
            WHERE username = ?
        """, (username.strip(),)).fetchone()

        if user is None:
            return None

        if not check_password_hash(user[2], password):
            return None

        return {
            "id": user[0],
            "username": user[1],
            "full_name": user[3]
        }

    finally:
        conn.close()