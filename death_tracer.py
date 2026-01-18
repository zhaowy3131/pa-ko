import os
import re
import sqlite3

# ================= CONFIGURATION =================
DB_FILE = 'analysis.db'
SGF_DIR = 'sgf_downloads'
TRACE_BACK_LIMIT = 50  # 往回看 50 手
VISITS_THRESHOLD = 2000 # 如果 visits 超過這個數，視為複雜戰鬥的信號
# =================================================

def get_db():
    return sqlite3.connect(DB_FILE)

def find_sgf_path(game_id):
    p1 = os.path.join(SGF_DIR, 'training', f'{game_id}.sgf')
    if os.path.exists(p1): return p1
    p2 = os.path.join(SGF_DIR, 'rating', f'{game_id}.sgf')
    if os.path.exists(p2): return p2
    return None

def parse_sgf_visits(content):
    """ 解析 SGF，返回 { move_num: visits } """
    moves_visits = {}
    pattern = re.compile(r';(B|W)\[([a-zA-Z]{0,2})\](?:C\[(.*?)(?<!\\)\])?', re.DOTALL)
    
    current_move_num = 0
    for match in pattern.finditer(content):
        current_move_num += 1
        comment = match.group(3)
        if comment:
            v_match = re.search(r'v=(\d+)', comment)
            if v_match:
                moves_visits[current_move_num] = int(v_match.group(1))
    return moves_visits

def trace_death_origin():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT id, game_id, move_number FROM sudden_deaths WHERE move_number > 0 AND start_move IS NULL')
    rows = c.fetchall()
    
    if not rows:
        print("沒有待追蹤的崩盤記錄。")
        return

    print(f"開始追蹤 {len(rows)} 個崩盤點 (Visits 回溯法)...")
    
    for row in rows:
        record_id, game_id, death_move = row
        
        path = find_sgf_path(game_id)
        if not path: continue
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            visits_map = parse_sgf_visits(content)
            
            # 回溯邏輯：
            # 在 [death_move - TRACE_BACK_LIMIT, death_move] 區間內
            # 尋找 visits 超過閾值的 *最早* 一手。
            # 如果這區間內都很平靜 (visits < THRESHOLD)，說明是突發死亡，回溯 10 手即可。
            
            start_search = max(1, death_move - TRACE_BACK_LIMIT)
            found_start = None
            
            # 從早往晚找，找到第一個激增點
            for m in range(start_search, death_move + 1):
                v = visits_map.get(m, 0)
                if v >= VISITS_THRESHOLD:
                    found_start = m
                    break # 找到了最早的激增點
            
            if found_start:
                # 為了展示完整性，我們再往前推 2 手作為鋪墊
                final_start = max(1, found_start - 2)
                reason = f"Visits激增 (v={visits_map.get(found_start)})"
            else:
                # 沒找到激增點，默認回溯 10 手
                final_start = max(1, death_move - 10)
                reason = "突發死亡 (Visits平穩)"
            
            # 更新 DB
            c.execute('UPDATE sudden_deaths SET start_move = ? WHERE id = ?', (final_start, record_id))
            print(f"  Game {game_id}: 崩盤點 {death_move} -> 起源 {final_start} ({reason})")
            
        except Exception as e:
            print(f"Error tracing {game_id}: {e}")

    conn.commit()
    conn.close()
    print("追蹤完成。")

if __name__ == "__main__":
    trace_death_origin()