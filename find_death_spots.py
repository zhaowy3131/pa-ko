import os
import re
import glob
import sqlite3

# ================= CONFIGURATION =================
SGF_DIR = 'sgf_downloads'
DB_FILE = 'analysis.db'

# Life & Death Criteria
SCORE_SWING_THRESHOLD = 10.0 # Score changes > 10 points
WINDOW_SIZE = 6 # Look at last 6 moves to define "locality"
MAX_REGION_SIZE = 12 # Relaxed to 12x12
# =================================================

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS death_spots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT,
                    move_number INTEGER,
                    score_swing REAL,
                    region_r1 INTEGER,
                    region_c1 INTEGER,
                    region_r2 INTEGER,
                    region_c2 INTEGER,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(game_id, move_number)
                )''')
    conn.commit()
    return conn

def get_coord(coord_str):
    if not coord_str or len(coord_str) < 2: return -1, -1
    col = ord(coord_str[0].lower()) - ord('a')
    row = ord(coord_str[1].lower()) - ord('a')
    return row, col

def analyze_death_spots(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            sgf_body = f.read()
    except Exception as e:
        return []

    # Regex for moves
    p_str = r';(B|W)\[([a-zA-Z]{0,2})\].*?C\[(.*?)(?<!\\)\]'
    pattern = re.compile(p_str, re.DOTALL)
    
    moves = []
    current_move = 0
    spots = []
    
    last_score = 0.0
    
    # Store recent moves for locality check: [(r, c), (r, c), ...]
    recent_coords = []
    
    # Global debug counter
    global debug_prints
    if 'debug_prints' not in globals(): debug_prints = 0
    
    for match in pattern.finditer(sgf_body):
        current_move += 1
        _, coord_str, sgf_note = match.groups()
        
        row, col = get_coord(coord_str)
        
        # Update recent buffer
        if row >= 0:
            recent_coords.append((row, col))
            if len(recent_coords) > WINDOW_SIZE:
                recent_coords.pop(0)
        
        try:
            parts = sgf_note.strip().split()
            if len(parts) < 4: continue
            
            # KataGo score is usually parts[3]
            current_score = float(parts[3])
            
            # DEBUG SPECIFIC FILE
            if '89723422.sgf' in filepath and debug_prints < 20:
                debug_prints += 1
                print(f"[DEBUG 89723422] Raw: {parts[3]} -> Float: {current_score} (Prev: {last_score})")
            
            swing = abs(current_score - last_score)
            
            # Check for sudden death/life
            if swing >= SCORE_SWING_THRESHOLD:
                if len(recent_coords) >= 4:
                    # Check locality
                    rows = [rc[0] for rc in recent_coords]
                    cols = [rc[1] for rc in recent_coords]
                    
                    r_min, r_max = min(rows), max(rows)
                    c_min, c_max = min(cols), max(cols)
                    
                    height = r_max - r_min + 1
                    width = c_max - c_min + 1
                    
                    if height <= MAX_REGION_SIZE and width <= MAX_REGION_SIZE:
                        spots.append({
                            'move': current_move,
                            'swing': swing,
                            'r1': r_min, 'c1': c_min,
                            'r2': r_max, 'c2': c_max
                        })
                    else:
                        # Debug: Found swing but failed locality
                        if debug_prints < 5:
                            debug_prints += 1
                            print(f"[DEBUG] Swing {swing:.1f} at {current_move} in {os.path.basename(filepath)} - Too spread: {height}x{width}")
                
            last_score = current_score
            
        except (ValueError, IndexError):
            continue
            
    return spots

def main():
    print("Searching for Life & Death Puzzles (Local Score Swings)...")
    conn = init_db()
    
    # Optional: Only scan games identified as 'Exciting' or 'Punisher' to save time?
    # Or scan all. Let's scan all for completeness.
    files = glob.glob(os.path.join(SGF_DIR, '**', '*.sgf'), recursive=True)
    print(f"Found {len(files)} SGF files.")
    
    processed = 0
    total_spots = 0
    
    for f in files:
        filename = os.path.basename(f)
        game_id = filename.replace('.sgf', '')
        
        spots = analyze_death_spots(f)
        
        c = conn.cursor()
        for s in spots:
            try:
                c.execute('''INSERT OR REPLACE INTO death_spots 
                             (game_id, move_number, score_swing, region_r1, region_c1, region_r2, region_c2)
                             VALUES (?, ?, ?, ?, ?, ?, ?)''',
                          (game_id, s['move'], s['swing'], 
                           s['r1'], s['c1'], s['r2'], s['c2']))
                total_spots += 1
            except Exception as e:
                pass
                
        processed += 1
        if processed % 500 == 0:
            conn.commit()
            print(f"Processed {processed}...")

    conn.commit()
    conn.close()
    
    print("\nLife & Death Scan Complete.")
    print(f"Total Local Death Spots Found: {total_spots}")

if __name__ == "__main__":
    main()