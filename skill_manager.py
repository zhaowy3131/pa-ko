import sqlite3
import os

# ================= CONFIGURATION =================
DB_FILE = 'analysis.db'
# =================================================

def init_db(conn):
    c = conn.cursor()
    # Main table to link Games to Skills
    c.execute('''CREATE TABLE IF NOT EXISTS game_skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT,
                    skill_id TEXT,
                    skill_value REAL, 
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(game_id, skill_id)
                )''')
    
    # Optional: Skill Definition Table (for metadata)
    c.execute('''CREATE TABLE IF NOT EXISTS skill_definitions (
                    skill_id TEXT PRIMARY KEY,
                    name TEXT,
                    category TEXT,
                    description TEXT
                )''')
    
    # Pre-populate Definitions
    skills = [
        ('KO_MASTER', 'Ko Master', 'Tactics', 'Complex ko fights detected'),
        ('COSMIC_FLOW', 'Cosmic Flow', 'Opening', 'High influence opening style'),
        ('PERFECT_OPENING', 'Perfect Opening', 'Opening', 'Balanced AI-like opening'),
        ('PUNISHER', 'Punisher', 'Opening', 'Crushing opponent in opening'),
        ('MUD_FIGHTER', 'Mud Fighter', 'Midgame', 'High frequency of lead changes'),
        ('DRAGON_SLAYER', 'Dragon Slayer', 'Fighting', 'Huge score swings indicating kills'),
        ('ENDGAME_WIZARD', 'Endgame Wizard', 'Endgame', 'Reversed game in late endgame'),
        ('SHARP_SHOOTER', 'Sharp Shooter', 'Tactics', 'Found multiple local life & death spots')
    ]
    c.executemany('INSERT OR IGNORE INTO skill_definitions VALUES (?,?,?,?)', skills)
    conn.commit()

def assign_skills():
    print("Assigning Skills to Games based on Analysis...")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    init_db(conn)
    
    total_assigned = 0

    # 1. KO_MASTER
    # Logic: Games with ko fights (from ko_fights table)
    # Could refine to count > 0
    c.execute('''SELECT game_id, count(*) as cnt 
                 FROM ko_fights 
                 GROUP BY game_id''')
    rows = c.fetchall()
    for gid, cnt in rows:
        val = float(cnt)
        desc = f"Found {cnt} ko fights"
        c.execute("INSERT OR REPLACE INTO game_skills (game_id, skill_id, skill_value, description) VALUES (?, ?, ?, ?)",
                  (gid, 'KO_MASTER', val, desc))
        total_assigned += 1

    # 2. OPENING SKILLS (Cosmic, Perfect, Punisher)
    c.execute('''SELECT game_id, opening_type, details FROM openings''')
    rows = c.fetchall()
    for gid, otype, det in rows:
        skill_id = None
        if otype == 'CosmicStyle': skill_id = 'COSMIC_FLOW'
        elif otype == 'Balanced': skill_id = 'PERFECT_OPENING'
        elif otype == 'Punisher': skill_id = 'PUNISHER'
        
        if skill_id:
            c.execute("INSERT OR REPLACE INTO game_skills (game_id, skill_id, skill_value, description) VALUES (?, ?, ?, ?)",
                      (gid, skill_id, 1.0, det))
            total_assigned += 1

    # 3. FIGHTING SKILLS (Mud Fighter, Dragon Slayer)
    c.execute('''SELECT game_id, lead_changes, max_score_gap, tags FROM exciting_games''')
    rows = c.fetchall()
    for gid, changes, gap, tags in rows:
        # Mud Fighter
        if changes >= 10:
            c.execute("INSERT OR REPLACE INTO game_skills (game_id, skill_id, skill_value, description) VALUES (?, ?, ?, ?)",
                      (gid, 'MUD_FIGHTER', float(changes), f"{changes} lead changes"))
            total_assigned += 1
            
        # Dragon Slayer
        if gap >= 30.0:
            c.execute("INSERT OR REPLACE INTO game_skills (game_id, skill_id, skill_value, description) VALUES (?, ?, ?, ?)",
                      (gid, 'DRAGON_SLAYER', gap, f"Max score swing {gap:.1f}"))
            total_assigned += 1

    # 4. ENDGAME WIZARD
    c.execute('''SELECT game_id, reversal_move FROM reversals WHERE reversal_type = 'Endgame' ''')
    rows = c.fetchall()
    for gid, rev_move in rows:
        c.execute("INSERT OR REPLACE INTO game_skills (game_id, skill_id, skill_value, description) VALUES (?, ?, ?, ?)",
                  (gid, 'ENDGAME_WIZARD', float(rev_move), f"Reversed at move {rev_move}"))
        total_assigned += 1

    # 5. SHARP SHOOTER (Life & Death)
    c.execute('''SELECT game_id, count(*) as cnt FROM death_spots GROUP BY game_id''')
    rows = c.fetchall()
    for gid, cnt in rows:
        if cnt >= 1: # Even 1 is good, but maybe >=2 for "Shooter" title? Let's say >=1 for now
            c.execute("INSERT OR REPLACE INTO game_skills (game_id, skill_id, skill_value, description) VALUES (?, ?, ?, ?)",
                      (gid, 'SHARP_SHOOTER', float(cnt), f"Solved {cnt} local tactical situations"))
            total_assigned += 1

    conn.commit()
    conn.close()
    print(f"Skill Assignment Complete. Added {total_assigned} tags.")

if __name__ == "__main__":
    assign_skills()
