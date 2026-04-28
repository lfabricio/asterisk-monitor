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
    Returns True if changed, False otherwise.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT status FROM ramal_current_status WHERE ramal = ?', (ramal,))
        row = cursor.fetchone()
        
        if row is None:
            # First time seeing this ramal
            cursor.execute('INSERT INTO ramal_current_status (ramal, status) VALUES (?, ?)', (ramal, status))
            cursor.execute('INSERT INTO ramal_status_log (ramal, status) VALUES (?, ?)', (ramal, status))
            conn.commit()
            return True
        elif row['status'] != status:
            # Status changed
            cursor.execute('UPDATE ramal_current_status SET status = ?, last_updated = CURRENT_TIMESTAMP WHERE ramal = ?', (status, ramal))
            cursor.execute('INSERT INTO ramal_status_log (ramal, status) VALUES (?, ?)', (ramal, status))
            conn.commit()
            return True
            
        return False

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
