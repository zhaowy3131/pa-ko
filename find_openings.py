import os
import re
import glob
import sqlite3

# ================= CONFIGURATION =================
SGF_DIR = 'sgf_downloads'
DB_FILE = 'analysis.db'
OPENING_MOVES = 60 

# Thresholds
BALANCED_THRESHOLD = 0.03 # +/- 3%
PUNISHER_THRESHOLD = 0.80 # > 80% or < 20%
INFLUENCE_LINE = 4
INFLUENCE_RATIO = 0.60
CONTACT_THRESHOLD = 0.30 # > 30% of moves are contact moves implies fighting
# =================================================

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS openings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT,
                    opening_type TEXT,
                    details TEXT,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(game_id, opening_type)
                )''')
    conn.commit()
    return conn

class SimpleBoard:
    def __init__(self):
        self.grid = {} # (r, c) -> color (1=B, 2=W)

    def is_contact(self, r, c, color):
        opp_color = 3 - color
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if self.grid.get((nr, nc)) == opp_color:
                return True
        return False

    def play(self, r, c, color):
        self.grid[(r, c)] = color

def get_coord(coord_str):
    if not coord_str or len(coord_str) < 2: return -1, -1
    col = ord(coord_str[0].lower()) - ord('a')
    row = ord(coord_str[1].lower()) - ord('a')
    return row, col

def get_line_height(row, col):
    if row < 0 or col < 0: return 0
    # 1-based distance from edge
    dist_x = min(col, 18 - col) + 1
    dist_y = min(row, 18 - row) + 1
    return min(dist_x, dist_y)

def analyze_opening(moves):
    if not moves: return []
    
    opening_moves = moves[:OPENING_MOVES]
    if len(opening_moves) < 30: return []

    tags = []
    
    # Analyze Stats
    high_moves = 0
    contact_moves = 0
    valid_moves = 0
    
    board = SimpleBoard()
    
    # Need to replay to check contact
    for m in opening_moves:
        r, c = m['row'], m['col']
        color = m['color'] # 1=B, 2=W
        
        if r >= 0 and c >= 0:
            valid_moves += 1
            if get_line_height(r, c) >= INFLUENCE_LINE:
                high_moves += 1
            
            if board.is_contact(r, c, color):
                contact_moves += 1
            
            board.play(r, c, color)

    contact_rate = contact_moves / valid_moves if valid_moves > 0 else 0
    influence_rate = high_moves / valid_moves if valid_moves > 0 else 0

    # 1. Balanced (Perfect Play)
    is_balanced = True
    for m in opening_moves:
        if not (0.50 - BALANCED_THRESHOLD <= m['winrate'] <= 0.50 + BALANCED_THRESHOLD):
            is_balanced = False
            break
    if is_balanced:
        tags.append(('Balanced', f"Deviation < {BALANCED_THRESHOLD*100:.0f}%, Contact {contact_rate*100:.0f}%"))

    # 2. Punisher (Early Lead)
    max_wr = 0.5
    min_wr = 0.5
    for m in opening_moves:
        wr = m['winrate']
        if wr > max_wr: max_wr = wr
        if wr < min_wr: min_wr = wr
    
    lead_score = max(max_wr, 1.0 - min_wr)
    if lead_score >= PUNISHER_THRESHOLD:
        tags.append(('Punisher', f"Spike to {lead_score:.2f}"))

    # 3. Style Classification (Influence vs Territory vs Fighting)
    if influence_rate > INFLUENCE_RATIO:
        if contact_rate > CONTACT_THRESHOLD:
            tags.append(('MidGameFight', f"High {influence_rate*100:.0f}%, Fight {contact_rate*100:.0f}%"))
        else:
            tags.append(('CosmicStyle', f"High {influence_rate*100:.0f}%, Peaceful {contact_rate*100:.0f}%"))
    else:
        # Standard or Low Influence
        if contact_rate > CONTACT_THRESHOLD:
             tags.append(('EarlyFight', f"Low {influence_rate*100:.0f}%, Fight {contact_rate*100:.0f}%"))
        else:
            # Normal Opening (Territorial/Standard) - Optional to tag
            pass

    return tags

def get_sgf_files():
    return glob.glob(os.path.join(SGF_DIR, '**', '*.sgf'), recursive=True)

def parse_sgf_opening(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            sgf_body = f.read()
    except Exception as e:
        return None, []

    p_res = r'RE\[([BW])\+[^\\]+\]'
    re_match = re.search(p_res, sgf_body)
    winner = re_match.group(1) if re_match else '?'

    p_str = r';(B|W)\[([a-zA-Z]{0,2})\].*?C\[(.*?)(?<!\\)\]'
    pattern = re.compile(p_str, re.DOTALL)
    
    moves = []
    current_move = 0
    
    for match in pattern.finditer(sgf_body):
        current_move += 1
        color_str, coord_str, sgf_note = match.groups()
        
        if current_move > OPENING_MOVES + 10:
            break
            
        try:
            parts = sgf_note.strip().split()
            if not parts: continue
            
            w_winrate_str = re.sub(r'[^\-0-9.]', '', parts[0])
            w_winrate = float(w_winrate_str)
            
            row, col = get_coord(coord_str)
            color = 1 if color_str == 'B' else 2
            
            moves.append({
                'move': current_move,
                'winrate': w_winrate,
                'row': row,
                'col': col,
                'color': color
            })
        except (ValueError, IndexError):
            continue
            
    return winner, moves

def main():
    print("Searching for Openings (Analysis v2)...")
    conn = init_db()
    files = get_sgf_files()
    print(f"Found {len(files)} SGF files.")
    
    processed = 0
    # Clear old openings data to avoid mixing definitions?
    # Or just REPLACE.
    # Let's count stats freshly.
    stats = {}
    
    printed_counts = {}

    for f in files:
        filename = os.path.basename(f)
        game_id = filename.replace('.sgf', '')
        
        winner, moves = parse_sgf_opening(f)
        tags = analyze_opening(moves)
        
        c = conn.cursor()
        for tag_type, details in tags:
            try:
                c.execute('''INSERT OR REPLACE INTO openings 
                             (game_id, opening_type, details)
                             VALUES (?, ?, ?)''', 
                          (game_id, tag_type, details))
                
                stats[tag_type] = stats.get(tag_type, 0) + 1
                printed_counts[tag_type] = printed_counts.get(tag_type, 0) + 1
                
                if printed_counts[tag_type] <= 3:
                    print(f"[{tag_type}] {filename}: {details}")
                    
            except Exception as e:
                print(f"DB Error: {e}")
        
        processed += 1
        if processed % 500 == 0:
            conn.commit()
            print(f"Processed {processed}...")

    conn.commit()
    conn.close()
    
    print("\nOpening Analysis Complete.")
    print("Stats:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

if __name__ == "__main__":
    main()
