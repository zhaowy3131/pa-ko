import sqlite3
conn = sqlite3.connect('analysis.db')
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM reversals")
print(f"Total Reversals stored: {c.fetchone()[0]}")
c.execute("SELECT * FROM reversals ORDER BY low_winrate ASC LIMIT 5")
print("\nTop 5 Massive Reversals:")
for row in c.fetchall():
    print(row)
conn.close()

