import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

DB_FILE = os.environ.get("DB_FILE", os.path.join(os.path.dirname(__file__), "history.db"))

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Create table if not exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ramal_status_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ramal TEXT NOT NULL,
                status TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # We also need a table to store the current state to know when it changes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ramal_current_status (
                ramal TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Table to track Asterisk server connectivity (instability history)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS asterisk_connectivity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL CHECK(status IN ('online', 'offline')),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Current connectivity state (singleton row)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS asterisk_current_connectivity (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                status TEXT NOT NULL DEFAULT 'unknown',
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Ensure the singleton row exists
        cursor.execute('''
            INSERT OR IGNORE INTO asterisk_current_connectivity (id, status) VALUES (1, 'unknown')
        ''')
        conn.commit()

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def log_status_if_changed(ramal: str, status: str):
    """
    Checks if the status changed since the last check.
    If it did, logs the new status to ramal_status_log and updates ramal_current_status.
    Returns a dict with change metadata.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT status FROM ramal_current_status WHERE ramal = ?', (ramal,))
        row = cursor.fetchone()
        cursor.execute(
            '''
            SELECT status
            FROM ramal_status_log
            WHERE ramal = ?
              AND lower(status) IN ('online', 'offline')
            ORDER BY id DESC
            LIMIT 1
            ''',
            (ramal,),
        )
        previous_notifiable_row = cursor.fetchone()
        previous_notifiable_status = previous_notifiable_row['status'] if previous_notifiable_row else None
        
        if row is None:
            # First time seeing this ramal
            cursor.execute('INSERT INTO ramal_current_status (ramal, status) VALUES (?, ?)', (ramal, status))
            cursor.execute('INSERT INTO ramal_status_log (ramal, status) VALUES (?, ?)', (ramal, status))
            conn.commit()
            return {
                "changed": True,
                "first_seen": True,
                "previous_status": None,
                "previous_notifiable_status": previous_notifiable_status,
                "current_status": status,
            }
        elif row['status'] != status:
            # Status changed
            previous_status = row['status']
            cursor.execute('UPDATE ramal_current_status SET status = ?, last_updated = CURRENT_TIMESTAMP WHERE ramal = ?', (status, ramal))
            cursor.execute('INSERT INTO ramal_status_log (ramal, status) VALUES (?, ?)', (ramal, status))
            conn.commit()
            return {
                "changed": True,
                "first_seen": False,
                "previous_status": previous_status,
                "previous_notifiable_status": previous_notifiable_status,
                "current_status": status,
            }
            
        return {
            "changed": False,
            "first_seen": False,
            "previous_status": row['status'],
            "previous_notifiable_status": previous_notifiable_status,
            "current_status": status,
        }

def get_status_history(hours: int = 24):
    """
    Returns the status history for the last N hours.
    It also includes an artificial boundary event at the start of the period 
    if a previous state existed, preventing lines before the system creation.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        time_modifier = f'-{hours} hours'
        
        # Find the exact timestamp string for the start of the period
        cursor.execute("SELECT datetime('now', ?)", (time_modifier,))
        start_time_str = cursor.fetchone()[0]
        
        # Get the most recent status before the period for each ramal
        cursor.execute('''
            SELECT ramal, status, MAX(timestamp) as max_time
            FROM ramal_status_log
            WHERE timestamp < ?
            GROUP BY ramal
        ''', (start_time_str,))
        previous_states = cursor.fetchall()
        
        # Get actual events within the period
        cursor.execute('''
            SELECT ramal, status, timestamp 
            FROM ramal_status_log 
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
        ''', (start_time_str,))
        events_in_period = [dict(row) for row in cursor.fetchall()]
        
        history = []
        for row in previous_states:
            history.append({
                "ramal": row["ramal"],
                "status": row["status"],
                "timestamp": start_time_str
            })
            
        history.extend(events_in_period)
        history.sort(key=lambda x: x["timestamp"])
        
        return history

def get_current_statuses():
    """
    Returns the current status of all ramais according to the DB.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT ramal, status, last_updated FROM ramal_current_status')
        return [dict(row) for row in cursor.fetchall()]


def log_asterisk_connectivity(is_online: bool) -> dict:
    """
    Logs Asterisk server connectivity status if changed.
    Returns a dict with change metadata.
    """
    new_status = "online" if is_online else "offline"

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('SELECT status FROM asterisk_current_connectivity WHERE id = 1')
        row = cursor.fetchone()

        if row is None or row['status'] != new_status:
            previous = row['status'] if row else 'unknown'
            cursor.execute('''
                UPDATE asterisk_current_connectivity
                SET status = ?, last_updated = CURRENT_TIMESTAMP
                WHERE id = 1
            ''', (new_status,))
            cursor.execute('''
                INSERT INTO asterisk_connectivity_log (status) VALUES (?)
            ''', (new_status,))
            conn.commit()
            return {"changed": True, "previous_status": previous, "current_status": new_status}

        return {"changed": False, "previous_status": row['status'], "current_status": new_status}


def get_asterisk_connectivity_history(hours: int = 24):
    """
    Returns the Asterisk connectivity history for the last N hours.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        time_modifier = f'-{hours} hours'

        cursor.execute("SELECT datetime('now', ?)", (time_modifier,))
        start_time_str = cursor.fetchone()[0]

        # Get the most recent status before the period
        cursor.execute('''
            SELECT status, timestamp
            FROM asterisk_connectivity_log
            WHERE timestamp < ?
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (start_time_str,))
        previous = cursor.fetchone()

        # Get events within the period
        cursor.execute('''
            SELECT status, timestamp
            FROM asterisk_connectivity_log
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
        ''', (start_time_str,))
        events = [dict(row) for row in cursor.fetchall()]

        history = []
        if previous:
            history.append({
                "status": previous["status"],
                "timestamp": start_time_str
            })

        history.extend(events)
        return history


def get_asterisk_current_connectivity():
    """
    Returns the current Asterisk connectivity status.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT status, last_updated FROM asterisk_current_connectivity WHERE id = 1')
        row = cursor.fetchone()
        if row:
            return {"status": row["status"], "last_updated": row["last_updated"]}
        return {"status": "unknown", "last_updated": None}
