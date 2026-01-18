import os
import re
import sqlite3
import glob

# ================= CONFIGURATION =================
DB_FILE = 'analysis.db'
SGF_DIR = 'sgf_downloads'
SCORE_DROP_THRESHOLD = 15.0 # 目數損失超過 15 目視為「雪崩」
# =================================================

def get_db():
    return sqlite3.connect(DB_FILE)

def find_sgf_path(game_id):
    p1 = os.path.join(SGF_DIR, 'training', f'{game_id}.sgf')
    if os.path.exists(p1): return p1
    p2 = os.path.join(SGF_DIR, 'rating', f'{game_id}.sgf')
    if os.path.exists(p2): return p2
    return None

def parse_sgf_scores(content):
    """
    解析 SGF，返回 { move_num: {'score': float, 'visits': int, 'color': int} }
    """
    moves_data = {}
    pattern = re.compile(r';(B|W)\[([a-zA-Z]{0,2})\](?:C\[(.*?)(?<!\\)\])?', re.DOTALL)
    
    current_move_num = 0
    for match in pattern.finditer(content):
        color_str, coord, comment = match.groups()
        current_move_num += 1
        color = 1 if color_str == 'B' else 2
        
        if comment:
            v_match = re.search(r'v=(\d+)', comment)
            visits = int(v_match.group(1)) if v_match else 0
            
            parts = comment.strip().split()
            if len(parts) >= 4:
                try:
                    def clean_float(s):
                        return float(re.sub(r'[^0-9.]', '', s))
                    # KataGo Score: B+ is positive, W+ is negative
                    # 這一點很重要，我們統一轉換為「當前下子方」的視角嗎？
                    # 不，我們統一用「黑棋視角」比較方便計算差值
                    score_lead = clean_float(parts[3]) 
                    
                    moves_data[current_move_num] = {
                        'score': score_lead,
                        'visits': visits,
                        'color': color
                    }
                except (ValueError, IndexError):
                    pass
    return moves_data

def analyze_deaths():
    conn = get_db()
    c = conn.cursor()
    
    # 這裡我們需要決定：是只分析 ko_fights 裡沒有的棋譜？還是全部重掃？
    # 為了簡單，我們先掃描所有已下載的 SGF，但利用一個新表或機制來避免重複？
    # 由於 processed_games 表已經被 ko_analyzer 用了，我們這裡簡單點：
    # 檢查 sudden_deaths 表裡有沒有這個 game_id，如果有就跳過。
    
    # 獲取所有已分析過死活的 game_id
    print("載入已分析清單...")
    processed_ids = set([r[0] for r in c.execute('SELECT DISTINCT game_id FROM sudden_deaths').fetchall()])
    
    # 掃描檔案
    print("掃描 SGF 檔案...")
    files = glob.glob(os.path.join(SGF_DIR, '**', '*.sgf'), recursive=True)
    
    new_count = 0
    deaths_found = 0
    
    for filepath in files:
        game_id = os.path.basename(filepath).replace('.sgf', '')
        
        if game_id in processed_ids:
            continue
            
        # 為了避免每次都跑 1000 個，我們也可以用一個簡單的內存標記，或者假設一次跑完
        # 其實可以用一個新的 processed_deaths 表，但這裡先直接跑
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            moves_data = parse_sgf_scores(content)
            
            # 尋找雪崩
            # 從第 2 手開始
            has_record = False
            
            # 按順序遍歷
            sorted_moves = sorted(moves_data.keys())
            for i in range(1, len(sorted_moves)):
                curr_m = sorted_moves[i]
                prev_m = sorted_moves[i-1]
                
                # 確保連續（雖然 parse 通常是連續的）
                if curr_m - prev_m != 1: continue
                
                curr = moves_data[curr_m]
                prev = moves_data[prev_m]
                
                # score 是黑棋領先目數
                # 如果是黑棋下(color=1)，我們希望 score 變大。如果 score 變小，就是黑棋虧了。
                # Loss = Prev_Score - Curr_Score
                
                # 如果是白棋下(color=2)，我們希望 score 變小(越負越好)。如果 score 變大，就是白棋虧了。
                # Loss = Curr_Score - Prev_Score
                
                loss = 0.0
                if curr['color'] == 1: # Black played
                    loss = prev['score'] - curr['score']
                else: # White played
                    loss = curr['score'] - prev['score']
                
                if loss > SCORE_DROP_THRESHOLD:
                    # 發現雪崩！
                    c.execute('''INSERT INTO sudden_deaths 
                                 (game_id, move_number, color, score_loss, visits)
                                 VALUES (?, ?, ?, ?, ?)''',
                              (game_id, curr_m, curr['color'], loss, curr['visits']))
                    deaths_found += 1
                    has_record = True
            
            # 如果這盤棋完全沒有雪崩，我們也要記錄它「已分析過」，以免下次重跑
            # 但我們目前的機制是 check `DISTINCT game_id FROM sudden_deaths`
            # 這意味著如果一盤棋沒有雪崩，下次還會被掃描。
            # 這有點浪費，但考慮到只有幾千盤，先這樣。
            # 如果要優化，應該加一個 `death_analyzed_games` 表。
            # 為了效率，我們這裡如果沒發現，就插入一條 dummy record? 不好。
            # 讓我們加一個 placeholder 表吧。
            
            # 算了，簡單起見，我們就在 sudden_deaths 裡插一條 move_number = 0 的記錄代表「已檢查但無雪崩」
            if not has_record:
                c.execute('''INSERT INTO sudden_deaths 
                             (game_id, move_number, color, score_loss, visits)
                             VALUES (?, 0, 0, 0, 0)''', (game_id,))
            
            new_count += 1
            if new_count % 100 == 0:
                print(f"已分析 {new_count} 個新檔案，發現 {deaths_found} 個雪崩瞬間...")
                conn.commit()
                
        except Exception as e:
            print(f"Error {game_id}: {e}")
            
    conn.commit()
    conn.close()
    print(f"\n任務完成。分析了 {new_count} 個檔案，共發現 {deaths_found} 個雪崩瞬間。")

if __name__ == "__main__":
    analyze_deaths()
