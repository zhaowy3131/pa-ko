import os
import re
import glob
import sqlite3
import time

# ================= CONFIGURATION =================
DB_FILE = 'analysis.db'
SGF_DIR = 'sgf_downloads'
# =================================================

# ----------------- 數據庫管理 -----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 表1: 記錄已分析的檔案 (以 game_id 為主鍵)
    c.execute('''CREATE TABLE IF NOT EXISTS processed_games (
                    game_id TEXT PRIMARY KEY,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    
    # 表2: 記錄發現的打劫 (Ko Fights)
    # 包含位置信息，方便後續視覺化或統計
    c.execute('''CREATE TABLE IF NOT EXISTS ko_fights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT,
                    start_move INTEGER,
                    end_move INTEGER,
                    span INTEGER,
                    capture_count INTEGER,
                    pos1_r INTEGER,
                    pos1_c INTEGER,
                    pos2_r INTEGER,
                    pos2_c INTEGER,
                    FOREIGN KEY(game_id) REFERENCES processed_games(game_id)
                )''')
    
    conn.commit()
    return conn

def is_processed(conn, game_id):
    c = conn.cursor()
    c.execute('SELECT 1 FROM processed_games WHERE game_id = ?', (game_id,))
    return c.fetchone() is not None

def save_results(conn, game_id, ko_results):
    c = conn.cursor()
    try:
        # 1. 標記為已處理
        c.execute('INSERT INTO processed_games (game_id) VALUES (?)', (game_id,))
        
        # 2. 插入打劫記錄
        for ko in ko_results:
            p1 = ko['pair'][0]
            # 如果 pair 只有一個元素(理論上不會，因為有 check，但防禦性編程)，就重複它
            p2 = ko['pair'][1] if len(ko['pair']) > 1 else p1
            
            c.execute('''INSERT INTO ko_fights 
                         (game_id, start_move, end_move, span, capture_count, pos1_r, pos1_c, pos2_r, pos2_c)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (game_id, ko['start'], ko['end'], ko['span'], ko['count'], 
                       p1[0], p1[1], p2[0], p2[1]))
        
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # 如果 game_id 已存在 (並發情況下可能發生)，則回滾
        conn.rollback()
        return False

# ----------------- 棋盤與分析邏輯 (保持不變) -----------------
class GoBoard:
    def __init__(self, size=19):
        self.size = size
        self.board = [[0 for _ in range(size)] for _ in range(size)]
        self.current_player = 1 

    def _get_neighbors(self, row, col):
        neighbors = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            r, c = row + dr, col + dc
            if 0 <= r < self.size and 0 <= c < self.size:
                neighbors.append((r, c))
        return neighbors

    def _get_group(self, row, col, color):
        if self.board[row][col] != color:
            return set()
        visited = set()
        stack = [(row, col)]
        group = set()
        while stack:
            pos = stack.pop()
            if pos in visited: continue
            visited.add(pos)
            r, c = pos
            if self.board[r][c] == color:
                group.add(pos)
                for neigh in self._get_neighbors(r, c):
                    stack.append(neigh)
        return group

    def _get_liberties(self, group):
        liberties = set()
        for pos in group:
            r, c = pos
            for neigh in self._get_neighbors(r, c):
                nr, nc = neigh
                if self.board[nr][nc] == 0:
                    liberties.add(neigh)
        return liberties

    def play(self, row, col):
        if row == -1 and col == -1:
            self.current_player = 3 - self.current_player
            return None
        
        if self.board[row][col] != 0:
            return None 
        
        opp_color = 3 - self.current_player
        self.board[row][col] = self.current_player
        
        captured_stones = []
        visited = set()
        for neigh in self._get_neighbors(row, col):
            nr, nc = neigh
            if self.board[nr][nc] == opp_color and (nr, nc) not in visited:
                group = self._get_group(nr, nc, opp_color)
                visited.update(group)
                if len(self._get_liberties(group)) == 0:
                    captured_stones.extend(list(group))
        
        for p in captured_stones:
            self.board[p[0]][p[1]] = 0
        
        captured_pos = None
        if len(captured_stones) == 1:
            captured_pos = captured_stones[0]
            
        self.current_player = 3 - self.current_player
        return captured_pos

def parse_sgf_moves(content):
    moves = []
    tokens = re.findall(r';(B|W)\[([a-zA-Z]{0,2})\]', content)
    for color_str, coord in tokens:
        if not coord:
            row, col = -1, -1
        else:
            if len(coord) == 0: 
                row, col = -1, -1
            else:
                c_s, r_s = coord[0], (coord[1] if len(coord)>1 else '')
                col = ord(c_s) - (ord('a') if 'a' <= c_s <= 'z' else ord('A'))
                row = ord(r_s) - (ord('a') if 'a' <= r_s <= 'z' else ord('A')) if r_s else -1
        
        color = 1 if color_str == 'B' else 2
        moves.append((color, row, col))
    return moves

def analyze_sgf_content(content):
    moves = parse_sgf_moves(content)
    if not moves: return []
    
    board = GoBoard(19)
    ko_events = []
    
    for i, (color, r, c) in enumerate(moves):
        move_num = i + 1
        if r < 0 or r >= 19 or c < 0 or c >= 19:
            board.play(r, c)
            continue
            
        board.current_player = color
        captured_pos = board.play(r, c)
        
        if captured_pos:
            ko_events.append({'move': move_num, 'pos': captured_pos})

    if len(ko_events) < 2:
        return []

    fights = []
    pair_activity = {}

    for i in range(len(ko_events)):
        curr = ko_events[i]
        curr_pos = curr['pos']
        
        for j in range(i):
            prev = ko_events[j]
            prev_pos = prev['pos']
            
            dist = abs(curr_pos[0] - prev_pos[0]) + abs(curr_pos[1] - prev_pos[1])
            if dist == 1:
                pair_key = frozenset({curr_pos, prev_pos})
                if pair_key not in pair_activity:
                    pair_activity[pair_key] = set()
                pair_activity[pair_key].add(prev['move'])
                pair_activity[pair_key].add(curr['move'])

    results = []
    for pair_set, move_set in pair_activity.items():
        moves = sorted(list(move_set))
        if len(moves) < 2: continue
        
        GAP_LIMIT = 50
        segments = []
        current_segment = [moves[0]]
        
        for k in range(1, len(moves)):
            if moves[k] - moves[k-1] > GAP_LIMIT:
                segments.append(current_segment)
                current_segment = [moves[k]]
            else:
                current_segment.append(moves[k])
        segments.append(current_segment)
        
        pair_list = list(pair_set)
        
        for seg in segments:
            span = seg[-1] - seg[0] + 1
            if span > 10:
                results.append({
                    'pair': pair_list,
                    'start': seg[0],
                    'end': seg[-1],
                    'span': span,
                    'count': len(seg)
                })
    return results

# ----------------- 主程序 -----------------
def main():
    conn = init_db()
    
    print("正在掃描 SGF 檔案...")
    files = glob.glob(os.path.join(SGF_DIR, '**', '*.sgf'), recursive=True)
    total_files = len(files)
    print(f"掃描到 {total_files} 個檔案。 সন")
    
    new_count = 0
    ko_found_count = 0
    
    for idx, filepath in enumerate(files):
        filename = os.path.basename(filepath)
        game_id = filename.replace('.sgf', '')
        
        if is_processed(conn, game_id):
            continue
            
        # 讀取並分析
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            results = analyze_sgf_content(content)
            
            # 存入 DB (無論有沒有發現 Ko，都標記為已處理，避免重複分析)
            if save_results(conn, game_id, results):
                new_count += 1
                if results:
                    ko_found_count += 1
                    print(f"[{new_count}] {game_id}: 發現 {len(results)} 個劫爭")
                else:
                    # print(f"[{new_count}] {game_id}: 無")
                    pass
                    
        except Exception as e:
            print(f"處理 {filename} 時出錯: {e}")
            
        # 每處理 100 個顯示一次進度
        if new_count % 100 == 0 and new_count > 0:
            print(f"已分析 {new_count} 個新檔案...")

    conn.close()
    print(f"\n任務完成。 সন")
    print(f"新分析檔案: {new_count}")
    print(f"發現劫爭局: {ko_found_count}")

if __name__ == "__main__":
    main()