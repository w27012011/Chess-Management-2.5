import sqlite3
import os
import re

# Ensure DB directory exists
if not os.path.exists('DB'):
    os.makedirs('DB')

def create_batch_database(batch_name):
    """Create a new SQLite database for a given batch_name."""
    # Sanitize batch_name to be filesystem-safe
    safe_batch_name = re.sub(r'[^a-zA-Z0-9_-]', '_', batch_name)
    db_path = f'DB/batch_{safe_batch_name}_database.db'
    
    # Check if database already exists to prevent duplicates
    if os.path.exists(db_path):
        return db_path

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Create Students table
    c.execute('''
    CREATE TABLE IF NOT EXISTS Students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT UNIQUE,
        name TEXT,
        class TEXT,
        roll TEXT,
        mobile TEXT,
        year TEXT,
        points REAL DEFAULT 0,
        matches_played INTEGER DEFAULT 0,
        paid_entry BOOLEAN DEFAULT FALSE
    )
    ''')

    # Create Matches table with batch_id
    c.execute('''
    CREATE TABLE IF NOT EXISTS Matches (
        match_id INTEGER PRIMARY KEY AUTOINCREMENT,
        student1_id TEXT,
        student2_id TEXT,
        winner_id TEXT,
        points_assigned INTEGER DEFAULT 0,
        match_date DATE DEFAULT (date('now')),
        batch_id TEXT
    )
    ''')

    # Create MatchHistory table with batch_id
    c.execute('''
    CREATE TABLE IF NOT EXISTS MatchHistory (
        match_id INTEGER PRIMARY KEY AUTOINCREMENT,
        student1_id TEXT,
        student2_id TEXT,
        winner_id TEXT,
        points_assigned INTEGER DEFAULT 0,
        match_date DATE,
        batch_id TEXT
    )
    ''')

    conn.commit()
    conn.close()
    return db_path