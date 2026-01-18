import os
import re
import glob
import sqlite3

# ================= CONFIGURATION =================
SGF_DIR = 'sgf_downloads'
DB_FILE = 'analysis.db'

# Criteria for "Exciting"
MIN_LEAD_CHANGES = 5  # At least 5 lead changes
HIGH_SCORE_SWING = 20 # Score swing > 20 points implies huge fight/kill
CLOSE_GAME_MARGIN = 2.5 # Final result <= 2.5 points
# =================================================

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS exciting_games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT UNIQUE,
                    winner TEXT,
                    total_moves INTEGER,
                    lead_changes INTEGER,
                    max_score_gap REAL,
                    final_score_gap REAL,
                    score_volatility REAL,
                    tags TEXT,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    conn.commit()
    return conn

def parse_game_data(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            sgf_body = f.read()
    except Exception as e:
        return None

    # 1. Parse Result from Header
    p_res = r'RE\[([BW])\+([^\\]+)\]'
    re_match = re.search(p_res, sgf_body)
    if not re_match: return None
    
    winner = re_match.group(1)
    result_str = re_match.group(2)
    
    # Parse final margin if possible (e.g. 0.5, 1.5, R, Resign)
    try:
        final_margin = float(result_str)
    except ValueError:
        final_margin = 999.0 # Resign or Time

    # 2. Parse Moves
    # We need Winrate AND Score estimate
    # KataGo comments: "0.45 0.55 0.00 -1.5 v=..." (Winrate B, Winrate W, Draw, Score B)
    p_str = r';(B|W)\[([a-zA-Z]{0,2})\].*?C\[(.*?)(?<!\\)\]'
    pattern = re.compile(p_str, re.DOTALL)
    
    lead_changes = 0
    prev_leader = None # 'B' or 'W'
    
    min_score = 0.0
    max_score = 0.0
    
    score_diff_accum = 0.0
    last_score = 0.0
    
    move_count = 0
    
    for match in pattern.finditer(sgf_body):
        move_count += 1
        _, _, sgf_note = match.groups()
        
        try:
            parts = sgf_note.strip().split()
            if len(parts) < 4: continue
            
            # parts[0]: B winrate (if standard) or W winrate?
            # Let's verify standard KataGo output format: "B_winrate W_winrate Draw Score_Lead_B"
            # Example: 0.47 0.53 0.00 -0.2
            
            # Using Winrate for Lead Changes
            # Standard KataGo: First number is Black's winrate?
            # Wait, in previous task we deduced parts[0] is White's winrate?
            # Let's re-verify logic. In 1875688.sgf:
            # Last move: C[0.96 0.04 ... result=W+R]
            # If parts[0] is 0.96 and result is W, then parts[0] is WHITE's winrate.
            # So:
            w_winrate = float(parts[0])
            b_winrate = 1.0 - w_winrate
            
            current_leader = 'W' if w_winrate > 0.5 else 'B'
            
            if prev_leader and current_leader != prev_leader:
                lead_changes += 1
            prev_leader = current_leader
            
            # Using Score for Volatility
            # parts[3] is Score Lead. Usually for BLACK?
            # Let's check 1875688.sgf again:
            # Last move: "... 7.6 ..." (positive) and result W+R.
            # If parts[3] is 7.6 and W wins, it implies parts[3] is WHITE's score lead.
            # So parts[3] is Score Lead for the perspective of parts[0] (White).
            
            score_lead = float(parts[3])
            
            if score_lead > max_score: max_score = score_lead
            if score_lead < min_score: min_score = score_lead
            
            score_diff_accum += abs(score_lead - last_score)
            last_score = score_lead
            
        except (ValueError, IndexError):
            continue

    if move_count < 100: return None
    
    # Calculate Metrics
    max_score_swing = max_score - min_score
    score_volatility = score_diff_accum / move_count # Avg point swing per move
    
    tags = []
    if lead_changes >= MIN_LEAD_CHANGES:
        tags.append('Seesaw')
    
    if max_score_swing >= HIGH_SCORE_SWING:
        tags.append('DragonFight')
        
    if final_margin <= CLOSE_GAME_MARGIN:
        tags.append('CloseGame')
        
    # Combine logic
    is_exciting = False
    if 'Seesaw' in tags: is_exciting = True
    if 'DragonFight' in tags: is_exciting = True
    if 'CloseGame' in tags and lead_changes > 2: is_exciting = True # Close game with some fighting
    
    if is_exciting:
        return {
            'game_id': os.path.basename(filepath).replace('.sgf', ''),
            'winner': winner,
            'moves': move_count,
            'lead_changes': lead_changes,
            'max_score_gap': max_score_swing,
            'final_margin': final_margin,
            'volatility': score_volatility,
            'tags': ','.join(tags)
        }
    return None

def main():
    print("Searching for Exciting Games (Score Swings & Lead Changes)...")
    conn = init_db()
    files = get_glob_files()
    print(f"Found {len(files)} SGF files.")
    
    processed = 0
    found_count = 0
    
    for f in files:
        res = parse_game_data(f)
        if res:
            try:
                c = conn.cursor()
                c.execute('''INSERT OR REPLACE INTO exciting_games
                             (game_id, winner, total_moves, lead_changes, max_score_gap, final_score_gap, score_volatility, tags)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                          (res['game_id'], res['winner'], res['moves'], res['lead_changes'],
                           res['max_score_gap'], res['final_margin'], res['volatility'], res['tags']))
                found_count += 1
                
                # Print truly crazy games immediately
                if 'Seesaw' in res['tags'] and 'DragonFight' in res['tags']:
                    print(f"[EPIC] {res['game_id']}: {res['lead_changes']} lead changes, {res['max_score_gap']:.1f} score swing!")
                    
            except Exception as e:
                print(f"DB Error: {e}")
                
        processed += 1
        if processed % 500 == 0:
            conn.commit()
            print(f"Processed {processed}...")
            
    conn.commit()
    conn.close()
    print(f"\nAnalysis Complete. Found {found_count} exciting games.")

def get_glob_files():
    return glob.glob(os.path.join(SGF_DIR, '**', '*.sgf'), recursive=True)

if __name__ == "__main__":
    main()
