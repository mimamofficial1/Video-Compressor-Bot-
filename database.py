import sqlite3
from config import Config

DEFAULT_SETTINGS = {
    "resolution":  "480p",
    "codec":       "x264",
    "bits":        "8 Bits",
    "crf":         30,
    "aspect":      "None",
    "upload_mode": "Document",
    "watermark":   None,
    "wm_color":    "red",
    "wm_pos":      "bottom",
    "wm_size":     25,
    "metadata":    "Disabled",
    "rename":      None,
}

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(Config.DB_PATH, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                user_id     INTEGER PRIMARY KEY,
                resolution  TEXT    DEFAULT '480p',
                codec       TEXT    DEFAULT 'x264',
                bits        TEXT    DEFAULT '8 Bits',
                crf         INTEGER DEFAULT 30,
                aspect      TEXT    DEFAULT 'None',
                upload_mode TEXT    DEFAULT 'Document',
                watermark   TEXT,
                wm_color    TEXT    DEFAULT 'red',
                wm_pos      TEXT    DEFAULT 'bottom',
                wm_size     INTEGER DEFAULT 25,
                metadata    TEXT    DEFAULT 'Disabled',
                rename      TEXT
            )
        """)
        self.conn.commit()

    def get_settings(self, user_id: int) -> dict:
        row = self.conn.execute(
            "SELECT * FROM settings WHERE user_id = ?", (user_id,)
        ).fetchone()

        if not row:
            self.conn.execute(
                "INSERT INTO settings (user_id) VALUES (?)", (user_id,)
            )
            self.conn.commit()
            return dict(DEFAULT_SETTINGS)

        cols = ["user_id","resolution","codec","bits","crf","aspect",
                "upload_mode","watermark","wm_color","wm_pos","wm_size",
                "metadata","rename"]
        d = dict(zip(cols, row))
        d.pop("user_id")
        return d

    def update_setting(self, user_id: int, key: str, value):
        self.get_settings(user_id)  # ensure row exists
        self.conn.execute(
            f"UPDATE settings SET {key} = ? WHERE user_id = ?", (value, user_id)
        )
        self.conn.commit()

    def reset_settings(self, user_id: int):
        self.conn.execute("DELETE FROM settings WHERE user_id = ?", (user_id,))
        self.conn.commit()
