import sqlite3
import os
import json

db_path = os.path.join('storage', 'db.sqlite3')
conn = sqlite3.connect(db_path)
c = conn.cursor()

try:
    c.execute('ALTER TABLE projects ADD COLUMN is_vlog BOOLEAN DEFAULT 1')
    conn.commit()
    print("Added is_vlog column to projects.")
except Exception as e:
    print("Error adding column (might exist):", e)

c.execute("SELECT id, workflow_type, error FROM prompt_logs WHERE status='failed' AND workflow_type='i2v' ORDER BY id DESC LIMIT 5")
for row in c.fetchall():
    print(row)
