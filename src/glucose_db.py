import datetime
import logging
import sqlite3
import threading


class GlucoseDB:
    def __init__(self, db_file):
        self.db_file = db_file

        self._init_tables()
        self.lock = threading.Lock()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug("[DB] Initialized")

    def _init_tables(self):
        with sqlite3.connect(self.db_file) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS glucose (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT UNIQUE,
                    glucose REAL
                )
            """
            )

    def add_readings(self, readings):
        # readings = list of tuples: (timestamp_iso, glucose_mmol)
        with self.lock, sqlite3.connect(self.db_file) as conn:
            for ts, glucose in readings:
                try:
                    conn.execute("INSERT OR IGNORE INTO glucose (timestamp, glucose) VALUES (?, ?)", (ts, glucose))
                except Exception as e:
                    self.logger.error(f"[DB] Insert error {e} for {ts} {glucose}")

    def get_last_24h(self):
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
        with self.lock, sqlite3.connect(self.db_file) as conn:
            cursor = conn.execute(
                "SELECT timestamp, glucose FROM glucose WHERE timestamp >= ? ORDER BY timestamp ASC", (cutoff_str,)
            )
            return [(datetime.datetime.fromisoformat(row[0]), row[1]) for row in cursor.fetchall()]

    def prune_old(self):
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
        with self.lock, sqlite3.connect(self.db_file) as conn:
            conn.execute("DELETE FROM glucose WHERE timestamp < ?", (cutoff_str,))
