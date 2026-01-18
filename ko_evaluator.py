import os
import re
import sqlite3
import glob

# ================= CONFIGURATION =================
DB_FILE = 'analysis.db'
SGF_DIR = 'sgf_downloads'
# =================================================

def get_db():
    return sqlite3.connect(DB_FILE)

def find_sgf_path(game_id):
    p1 = os.path.join(SGF_DIR, 'training', f'{game_id}.sgf')
    if os.path.exists(p1): return p1
    
    p2 = os.path.join(SGF_DIR, 'rating', f'{game_id}.sgf')
    if os.path.exists(p2): return p2
    return None

def parse_sgf_details(content):
    """
    解析 SGF，返回兩個 dict:
    1. moves_data: { move_num: {'winrate':..., 'score':..., 'visits':...} }
    2. moves_colors: { move_num: 1(B) or 2(W) }
    """
    moves_data = {}
    moves_colors = {}
    
    pattern = re.compile(r';(B|W)\[([a-zA-Z]{0,2})\](?:C\[(.*?)(?<!\\)\])?', re.DOTALL)
    
    current_move_num = 0
    for match in pattern.finditer(content):
        color_str, coord, comment = match.groups()
        current_move_num += 1
        
        moves_colors[current_move_num] = 1 if color_str == 'B' else 2
        
        if comment:
            v_match = re.search(r'v=(\d+)', comment)
            visits = int(v_match.group(1)) if v_match else 0
            
            parts = comment.strip().split()
            if len(parts) >= 4:
                try:
                    def clean_float(s):
                        return float(re.sub(r'[^\-0-9.]', '', s))
                    
                    winrate = clean_float(parts[0])
                    score = clean_float(parts[3])
                    
                    moves_data[current_move_num] = {
                        'winrate': winrate,
                        'score': score,
                        'visits': visits
                    }
                except (ValueError, IndexError):
                    pass
    
    return moves_data, moves_colors

def process_fights():
    print("連接資料庫...")
    conn = get_db()
    c = conn.cursor()
    
    print("查詢待處理記錄...")
    c.execute('SELECT id, game_id, start_move, end_move FROM ko_fights WHERE blunder_move IS NULL')
    rows = c.fetchall()
    
    print(f"查詢返回 {len(rows)} 條記錄")
    
    if not rows:
        print("沒有需要評估的記錄。")
        return

    print(f"找到 {len(rows)} 條待評估記錄，開始處理...")
    
    count = 0
    current_game_id = None
    moves_data = None
    moves_colors = None
    
    for row in rows:
        record_id, game_id, start, end = row
        
        if game_id != current_game_id:
            path = find_sgf_path(game_id)
            if not path:
                continue
                
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                moves_data, moves_colors = parse_sgf_details(content)
                current_game_id = game_id
            except Exception as e:
                print(f"讀取錯誤 {game_id}: {e}")
                moves_data = {}
                moves_colors = {}
                continue
        
        if not moves_data: continue
        
        data_start = moves_data.get(start, {})
        data_end = moves_data.get(end, {})
        
        max_v = 0
        for m in range(start, end + 1):
            v = moves_data.get(m, {}).get('visits', 0)
            if v > max_v: max_v = v

        # --- 新增: 計算 Blunder (敗著) ---
        max_drop = 0.0
        blunder_mv = None
        
        for m in range(start, end + 1):
            if m == 1: continue
            
            curr_info = moves_data.get(m)
            prev_info = moves_data.get(m-1)
            
            if curr_info and prev_info:
                color = moves_colors.get(m)
                wr_curr = curr_info['winrate']
                wr_prev = prev_info['winrate']
                
                drop = 0.0
                if color == 1: # 黑棋下的
                    drop = wr_prev - wr_curr
                elif color == 2: # 白棋下的
                    drop = wr_curr - wr_prev
                
                if drop > 0.05 and drop > max_drop:
                    max_drop = drop
                    blunder_mv = m
        
        # 即使沒有 blunder (blunder_mv 為 None), 也要更新 winrate 等信息
        # 並且要把 blunder_move 設為 0 或 -1 (如果不想留 NULL)，但保持 NULL 也行
        # 不過為了避免下次 loop 又選出來，我們必須更新那些欄位
        # 如果 blunder_mv 是 None，我們寫入 NULL 到 DB
        # SQLite 的 execute 若收到 None 會寫入 NULL
        
        # **重要**: 我們必須確保這條記錄即使沒 blunder 也被更新了，
        # 否則下次 SELECT ... WHERE blunder_move IS NULL 又會選中它，造成死循環。
        # 解決方法：我們可以用另一個標記，或者如果 blunder_mv 是 None，我們就存個特殊值（如 0）表示「已檢查但無敗著」。
        # 這裡我們選擇：如果沒敗著，存 0。
        
        final_blunder_mv = blunder_mv if blunder_mv is not None else 0
        final_blunder_loss = max_drop if blunder_mv is not None else 0.0

        if data_start and data_end:
            c.execute('''UPDATE ko_fights SET 
                            winrate_start = ?, winrate_end = ?,
                            score_start = ?, score_end = ?,
                            visits_max = ?,
                            blunder_move = ?, blunder_loss = ?
                         WHERE id = ?''',
                      (data_start.get('winrate'), data_end.get('winrate'),
                       data_start.get('score'), data_end.get('score'),
                       max_v, 
                       final_blunder_mv, final_blunder_loss,
                       record_id))
            count += 1
            
        if count % 100 == 0:
            print(f"已評估 {count} 條記錄...")
            conn.commit()

    conn.commit()
    conn.close()
    print(f"評估完成，更新了 {count} 條記錄。")

if __name__ == "__main__":
    process_fights()