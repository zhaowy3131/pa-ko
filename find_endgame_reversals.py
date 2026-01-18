import os
import re
import glob
import sqlite3

# ================= CONFIGURATION =================
SGF_DIR = 'sgf_downloads'
DB_FILE = 'analysis.db'
MIN_GAME_LENGTH = 150

# Logic: Match ANY of these criteria
CRITERIA = [
    # 1. Massive Reversal: Dropped below 10%, reversed after move 130
    {'name': 'Massive', 'min_reversal_move': 130, 'max_low_wr': 0.10, 'search_start': 100},
    
    # 2. Late Game Reversal: Dropped below 45%, reversed after move 200
    {'name': 'Endgame', 'min_reversal_move': 200, 'max_low_wr': 0.45, 'search_start': 150}
]
# =================================================

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Create table if not exists
    # We use game_id as UNIQUE to prevent duplicates
    c.execute('''CREATE TABLE IF NOT EXISTS reversals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT UNIQUE,
                    winner TEXT,
                    total_moves INTEGER,
                    reversal_type TEXT,
                    low_winrate REAL,
                    low_move INTEGER,
                    reversal_move INTEGER,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    conn.commit()
    return conn

def is_analyzed(conn, game_id):
    # Check if we already have a record for this game
    # Note: If we want to record "No Reversal Found", we might need a separate 'processed_games' table
    # like in ko_analyzer. But for now, user asked to "put results in table".
    # However, to support "incremental scan", we need to know if we checked it.
    # Let's create a separate tracking table for "checked files" to be robust.
    
    c = conn.cursor()
    # Create processed tracking table on the fly if needed
    c.execute('''CREATE TABLE IF NOT EXISTS reversal_processed (
                    game_id TEXT PRIMARY KEY
                )''')
    conn.commit()
    
    c.execute('SELECT 1 FROM reversal_processed WHERE game_id = ?', (game_id,))
    return c.fetchone() is not None

def mark_as_processed(conn, game_id):
    c = conn.cursor()
    try:
        c.execute('INSERT OR IGNORE INTO reversal_processed (game_id) VALUES (?)', (game_id,))
        conn.commit()
    except:
        pass

def save_reversal(conn, data):
    c = conn.cursor()
    try:
        # Extract game_id from filepath
        filename = os.path.basename(data['file'])
        game_id = filename.replace('.sgf', '')
        
        c.execute('''INSERT OR REPLACE INTO reversals 
                     (game_id, winner, total_moves, reversal_type, low_winrate, low_move, reversal_move)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (game_id, data['winner'], data['moves'], data['type'], 
                   data['lowest_winrate'], data['lowest_move'], data['reversal_move']))
        conn.commit()
        return True
    except Exception as e:
        print(f"DB Error: {e}")
        return False

def get_sgf_files():
    return glob.glob(os.path.join(SGF_DIR, '**', '*.sgf'), recursive=True)

def parse_sgf_reversal(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            sgf_body = f.read()
    except Exception as e:
        return None

    # 1. Parse Result
    # Split regex to avoid tool bug
    p_res = r'RE\[([BW])\+[^]]+\]'
    re_match = re.search(p_res, sgf_body)
    if not re_match:
        return None
    winner_color = re_match.group(1)

    # 2. Parse Moves and Winrates
    # Regex construction
    p_str = r';(B|W)\[([a-zA-Z]{0,2})\]\s*?C\[(.*?)(?<!\\)\]'
    pattern = re.compile(p_str, re.DOTALL)
    
    moves = []
    current_move = 0
    
    for match in pattern.finditer(sgf_body):
        current_move += 1
        color_str, coord_str, sgf_note = match.groups()
        
        try:
            parts = sgf_note.strip().split()
            if not parts: continue
            
            # parts[0] is WHITE's winrate
            w_winrate_str = re.sub(r'[^\-0-9.]', '', parts[0])
            w_winrate = float(w_winrate_str)
            
            # Store WINNER's winrate directly for easier logic later
            if winner_color == 'W':
                winrate = w_winrate
            else:
                winrate = 1.0 - w_winrate
            
            moves.append({
                'move': current_move,
                'winrate': winrate
            })
        except (ValueError, IndexError):
            continue

    if len(moves) < MIN_GAME_LENGTH:
        return None

    # 3. Analyze for Reversal
    
    # Condition 1: Winner must be winning at the end ( > 0.5)
    if moves[-1]['winrate'] < 0.5:
        return None # Zombie game

    # Find the "Final Reversal Point"
    # The last time winrate was <= 0.5
    final_reversal_index = -1
    for i in range(len(moves) - 1, -1, -1):
        if moves[i]['winrate'] <= 0.5:
            final_reversal_index = i
            break
            
    if final_reversal_index == -1:
        return None # Always winning
        
    reversal_move_num = moves[final_reversal_index + 1]['move']
    
    # Check against Criteria
    matched_criteria = []
    
    for crit in CRITERIA:
        if reversal_move_num < crit['min_reversal_move']:
            continue
            
        # Check if they hit the low point AFTER search_start
        # AND BEFORE the reversal (logically true if reversal > start)
        
        search_start_idx = 0
        for i, m in enumerate(moves):
            if m['move'] >= crit['search_start']:
                search_start_idx = i
                break
        
        # Scan for low point
        lowest_wr = 1.0
        lowest_wr_move = -1
        found_low = False
        
        # We search up to the reversal point (or end of game, but reversal point implies 
        # previous moves were lower).
        # Actually we just need to find *IF* it dipped low in the relevant window.
        
        # Window: [search_start, final_reversal_index]
        for i in range(search_start_idx, final_reversal_index + 1):
            wr = moves[i]['winrate']
            if wr < lowest_wr:
                lowest_wr = wr
                lowest_wr_move = moves[i]['move']
            
            if wr < crit['max_low_wr']:
                found_low = True
                
        if found_low:
            matched_criteria.append({
                'name': crit['name'],
                'low': lowest_wr,
                'low_at': lowest_wr_move
            })

    if matched_criteria:
        # Pick the "best" criteria match (e.g. Massive > Endgame) or just the first
        # Let's return the one with the lowest winrate
        best_match = min(matched_criteria, key=lambda x: x['low'])
        
        return {
            'file': filepath,
            'winner': winner_color,
            'moves': len(moves),
            'type': best_match['name'],
            'lowest_winrate': best_match['low'],
            'lowest_move': best_match['low_at'],
            'reversal_move': reversal_move_num
        }
    
    return None

def main():
    print("Searching for Endgrame Reversals (Massive & Late-Game)...")
    conn = init_db()
    files = get_sgf_files()
    print(f"Found {len(files)} SGF files.")
    
    reversals = []
    processed = 0
    new_found = 0
    
    for f in files:
        filename = os.path.basename(f)
        game_id = filename.replace('.sgf', '')
        
        if is_analyzed(conn, game_id):
            processed += 1
            continue
            
        res = parse_sgf_reversal(f)
        
        # Mark as processed regardless of result to avoid rescanning
        mark_as_processed(conn, game_id)
        
        if res:
            if save_reversal(conn, res):
                new_found += 1
                reversals.append(res)
                print(f"[{res['type']}] {filename} (W:{res['winner']}) "
                      f"Low:{res['lowest_winrate']:.2f}@{res['lowest_move']} -> "
                      f"Rev@{res['reversal_move']} (Len:{res['moves']})")
        
        processed += 1
        if processed % 500 == 0:
            print(f"Processed {processed}...")

    conn.close()
    print(f"\nScan Complete.")
    print(f"Total Files Checked: {processed}")
    print(f"New Reversals Found: {new_found}")

if __name__ == "__main__":
    main()