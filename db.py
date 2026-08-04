"""SQLite 数据库模块 - 管理用户订阅和推送历史

表结构：
  subscriptions: 用户订阅信息（dot_api_key, device_id, city, 经纬度, 管理令牌, 状态）
  push_history: 推送历史记录（设备ID, 诗词, 天气, 状态, 时间）
"""

import sqlite3
import secrets
import os
from datetime import datetime

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "poetry_weather.db")
)


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dot_api_key TEXT NOT NULL,
            device_id TEXT NOT NULL,
            city TEXT NOT NULL,
            lng REAL NOT NULL,
            lat REAL NOT NULL,
            manage_token TEXT UNIQUE NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS push_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            device_id TEXT NOT NULL,
            poem_title TEXT,
            poem_author TEXT,
            weather_desc TEXT,
            temperature INTEGER,
            status TEXT NOT NULL,
            error_msg TEXT,
            pushed_at TEXT NOT NULL,
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
        );

        CREATE INDEX IF NOT EXISTS idx_sub_active ON subscriptions(active);
        CREATE INDEX IF NOT EXISTS idx_push_sub ON push_history(subscription_id);
    """)
    conn.commit()
    conn.close()


def add_subscription(dot_api_key, device_id, city, lng, lat):
    """添加新订阅

    Returns:
        str: 管理令牌（用于后续管理订阅）
    """
    manage_token = secrets.token_urlsafe(16)
    now = datetime.now().isoformat()

    conn = get_db()
    # 检查是否已存在相同 device_id 的订阅
    existing = conn.execute(
        "SELECT id, manage_token FROM subscriptions WHERE device_id = ? AND active = 1",
        (device_id,)
    ).fetchone()

    if existing:
        # 已存在，更新信息
        conn.execute(
            """UPDATE subscriptions SET
               dot_api_key = ?, city = ?, lng = ?, lat = ?, updated_at = ?
               WHERE id = ?""",
            (dot_api_key, city, lng, lat, now, existing["id"])
        )
        conn.commit()
        conn.close()
        return existing["manage_token"]

    conn.execute(
        """INSERT INTO subscriptions
           (dot_api_key, device_id, city, lng, lat, manage_token, active, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
        (dot_api_key, device_id, city, lng, lat, manage_token, now, now)
    )
    conn.commit()
    conn.close()
    return manage_token


def get_subscription(manage_token):
    """通过管理令牌获取订阅信息"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM subscriptions WHERE manage_token = ?",
        (manage_token,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_active_subscriptions():
    """获取所有活跃订阅"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE active = 1 ORDER BY created_at"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_subscription(manage_token, city=None, lng=None, lat=None):
    """更新订阅信息"""
    now = datetime.now().isoformat()
    conn = get_db()
    sub = get_subscription(manage_token)
    if not sub:
        conn.close()
        return False

    updates = []
    params = []
    if city is not None:
        updates.append("city = ?")
        params.append(city)
    if lng is not None:
        updates.append("lng = ?")
        params.append(lng)
    if lat is not None:
        updates.append("lat = ?")
        params.append(lat)
    updates.append("updated_at = ?")
    params.append(now)
    params.append(manage_token)

    conn.execute(
        f"UPDATE subscriptions SET {', '.join(updates)} WHERE manage_token = ?",
        params
    )
    conn.commit()
    conn.close()
    return True


def deactivate_subscription(manage_token):
    """停用订阅（软删除）"""
    now = datetime.now().isoformat()
    conn = get_db()
    conn.execute(
        "UPDATE subscriptions SET active = 0, updated_at = ? WHERE manage_token = ?",
        (now, manage_token)
    )
    conn.commit()
    conn.close()


def record_push(subscription_id, device_id, poem_title, poem_author,
                weather_desc, temperature, status, error_msg=None):
    """记录推送历史"""
    now = datetime.now().isoformat()
    conn = get_db()
    conn.execute(
        """INSERT INTO push_history
           (subscription_id, device_id, poem_title, poem_author,
            weather_desc, temperature, status, error_msg, pushed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (subscription_id, device_id, poem_title, poem_author,
         weather_desc, temperature, status, error_msg, now)
    )
    conn.commit()
    conn.close()


def get_push_history(manage_token, limit=10):
    """获取某订阅的推送历史"""
    conn = get_db()
    rows = conn.execute(
        """SELECT ph.* FROM push_history ph
           JOIN subscriptions s ON ph.subscription_id = s.id
           WHERE s.manage_token = ?
           ORDER BY ph.pushed_at DESC
           LIMIT ?""",
        (manage_token, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats():
    """获取服务统计信息"""
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM subscriptions").fetchone()["c"]
    active = conn.execute(
        "SELECT COUNT(*) as c FROM subscriptions WHERE active = 1"
    ).fetchone()["c"]
    pushes = conn.execute("SELECT COUNT(*) as c FROM push_history").fetchone()["c"]
    success = conn.execute(
        "SELECT COUNT(*) as c FROM push_history WHERE status = 'success'"
    ).fetchone()["c"]
    conn.close()
    return {
        "total_subscriptions": total,
        "active_subscriptions": active,
        "total_pushes": pushes,
        "successful_pushes": success,
    }
