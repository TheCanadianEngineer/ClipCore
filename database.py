import sqlite3
import threading
from datetime import datetime

class Database:
    def __init__(self, db_path="clipboard.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.lock = threading.Lock()
        self._create_table()

    def _create_table(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS clips (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                content   TEXT NOT NULL,
                type      TEXT NOT NULL,
                favourite BOOLEAN NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def save(self, content, clip_type, favourite):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.lock:
            self.cursor.execute(
                "INSERT INTO clips (content, type, favourite, timestamp) VALUES (?, ?, ?, ?)",
                (content, clip_type, favourite, timestamp)
            )
            self.conn.commit()

    def fetch_all(self):
        with self.lock:
            self.cursor.execute(
                "SELECT id, content, type, favourite, timestamp FROM clips ORDER BY timestamp DESC"
            )
            return self.cursor.fetchall()

    def delete_old(self, days=30):
        cutoff = datetime.now().strftime("%Y-%m-%d")
        with self.lock:
            self.cursor.execute(
                "DELETE FROM clips WHERE timestamp < ?",
                (cutoff,)
            )
            self.conn.commit()

    def exists(self, content):
        self.cursor.execute(
        "SELECT 1 FROM clips WHERE content = ? LIMIT 1",
        (content,)
        )
        return self.cursor.fetchone() is not None
    
    def delete_clip(self, content):
        self.cursor.execute("DELETE FROM clips WHERE content = ?", (content,))
        self.conn.commit()

    def toggle_favourite(self, content, value):
        self.cursor.execute(f'UPDATE clips SET favourite = ? WHERE content = ?', (value, content))
        self.conn.commit()

    def insert_clip(self, content, category):
        self.cursor.execute(
            "INSERT INTO clips (content, category, favourite, timestamp) VALUES (?, ?, 0, datetime('now'))",
            (content, category)
        )
        self.conn.commit()

    def close(self):
        self.conn.close()