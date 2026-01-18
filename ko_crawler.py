import requests
from bs4 import BeautifulSoup
import re
import os
import time

class GoBoard:
    def __init__(self, size=19):
        self.size = size
        self.board = [[0 for _ in range(size)] for _ in range(size)]  # 0: empty, 1: black, 2: white
        self.ko_pos = None
        self.current_player = 1  # starts with black

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
            if pos in visited:
                continue
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
        if row == -1 and col == -1:  # pass
            self.ko_pos = None
            self.current_player = 3 - self.current_player
            return []
        
        pos = (row, col)
        if self.board[row][col] != 0:
            # raise ValueError("Position occupied") # Ignored for now to allow loose parsing
            return None # Skip invalid moves
        
        opp_color = 3 - self.current_player
        
        # Place stone
        self.board[row][col] = self.current_player
        
        # Find captured groups
        captured_stones = []
        captured_groups = []
        visited = set()
        for neigh in self._get_neighbors(row, col):
            nr, nc = neigh
            if self.board[nr][nc] == opp_color and (nr, nc) not in visited:
                group = self._get_group(nr, nc, opp_color)
                visited.update(group)
                if len(self._get_liberties(group)) == 0:
                    captured_groups.append(group)
                    captured_stones.extend(list(group))
        
        # Remove captured
        for p in captured_stones:
            pr, pc = p
            self.board[pr][pc] = 0
        
        # Set ko_pos
        self.ko_pos = None
        if len(captured_stones) == 1:
            self.ko_pos = captured_stones[0]
        
        # Switch player
        self.current_player = 3 - self.current_player
        
        return captured_stones if len(captured_stones) == 1 else None

def parse_sgf(sgf_content):
    # Simple parser for linear SGF
    moves = []
    size = 19
    sz_match = re.search(r'SZ\[(\d+)\]', sgf_content)
    if sz_match:
        size = int(sz_match.group(1))
    
    # Find all moves ;B[xx] or ;W[xx]
    # Removed trailing space in regex to handle tight SGFs
    move_pattern = re.findall(r';(B|W)\[([a-zA-Z]{0,2})\]', sgf_content)
    for color, coord in move_pattern:
        if not coord:  # pass
            row, col = -1, -1
        else:
            if len(coord) == 0:
                row, col = -1, -1
            else:
                col_letter = coord[0]
                row_letter = coord[1] if len(coord) > 1 else '' 
                
                if col_letter >= 'a' and col_letter <= 'z':
                     col = ord(col_letter) - ord('a')
                else:
                     col = ord(col_letter) - ord('A')

                if row_letter >= 'a' and row_letter <= 'z':
                    row = ord(row_letter) - ord('a')
                elif row_letter:
                     row = ord(row_letter) - ord('A')
                else:
                    row = -1
        
        moves.append((1 if color == 'B' else 2, row, col))
    
    return size, moves

def analyze_game(sgf_content):
    try:
        size, moves = parse_sgf(sgf_content)
        board = GoBoard(size)
        ko_captures = []
        move_num = 1
        for color, row, col in moves:
            if row >= size or col >= size: 
                move_num += 1
                continue

            board.current_player = color
            captured = board.play(row, col)
            if board.ko_pos is not None:
                # board.ko_pos is the coordinate (r, c) that is now illegal to play.
                # It represents the 'hole' made by the capture.
                ko_captures.append({'move': move_num, 'pos': board.ko_pos})
            move_num += 1
        
        long_ko_fights = []
        if len(ko_captures) < 2:
            return long_ko_fights
        
        # Robust Chain Logic
        # A Ko fight consists of alternating captures between two positions.
        # We group captures into "chains" where the set of positions involved is exactly size 2.
        
        current_chain = [ko_captures[0]]
        current_spots = {ko_captures[0]['pos']}
        
        for i in range(1, len(ko_captures)):
            capture = ko_captures[i]
            pos = capture['pos']
            
            # Check if this capture belongs to the current fight
            # It belongs if:
            # 1. It's one of the existing spots in the chain
            # 2. OR the chain has only 1 spot so far, so this defines the second spot.
            
            is_part_of_chain = False
            if pos in current_spots:
                is_part_of_chain = True
            elif len(current_spots) == 1:
                # We only have 1 spot so far. Is this the second spot?
                # We only allow it if it's "close" in moves? 
                # Actually, ko captures can be far apart if many threats.
                # But if we capture A, then 100 moves later capture B... is that a fight?
                # The user defined "span > 10 moves".
                # If A (move 10) and B (move 100) are the first two interactions...
                # The span is 90. Is it a fight? No, it's two separate events probably.
                # But let's be generous. If they alternate A, B, A, B... it's a fight.
                # Let's add it.
                current_spots.add(pos)
                is_part_of_chain = True
            
            if is_part_of_chain:
                current_chain.append(capture)
            else:
                # Chain broken (new spot C introduced).
                # Evaluate old chain
                if len(current_spots) == 2:
                    spots_list = list(current_spots)
                    p1, p2 = spots_list[0], spots_list[1]
                    dist = abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])
                    
                    if dist == 1:
                        first_move = current_chain[0]['move']
                        last_move = current_chain[-1]['move']
                        span = last_move - first_move + 1
                        if span > 10:
                            long_ko_fights.append({
                                'start_move': first_move,
                                'end_move': last_move,
                                'span': span,
                                'positions': spots_list
                            })
                
                # Start new chain
                current_chain = [capture]
                current_spots = {pos}
        
        # Evaluate final chain
        if len(current_spots) == 2:
            spots_list = list(current_spots)
            p1, p2 = spots_list[0], spots_list[1]
            dist = abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])
            
            # Valid Ko fight must alternate between two adjacent spots
            if dist == 1:
                first_move = current_chain[0]['move']
                last_move = current_chain[-1]['move']
                span = last_move - first_move + 1
                if span > 10:
                    long_ko_fights.append({
                        'start_move': first_move,
                        'end_move': last_move,
                        'span': span,
                        'positions': spots_list
                    })
        
        return long_ko_fights
    except Exception as e:
        print(f"Error analyzing: {e}")
        return []
    except Exception as e:
        print(f"Error analyzing: {e}")
        return []

def crawl_and_analyze(network_id='kata1-b28c512nbt-s12253653760-d5671874532', max_pages=10, max_games=50, delay=1):
    # Reduced max_pages/max_games for testing
    base_url = f'https://katagotraining.org/networks/kata1/{network_id}/training-games/'
    sgf_dir = 'sgf_files'
    os.makedirs(sgf_dir, exist_ok=True)
    results_file = 'ko_fights_log.txt'
    checked_file = 'ko_checked_games.txt'
    
    # Load already checked games
    checked_ids = set()
    if os.path.exists(checked_file):
        with open(checked_file, 'r', encoding='utf-8') as f:
            for line in f:
                checked_ids.add(line.strip())
    
    game_count = 0
    with open(results_file, 'a', encoding='utf-8') as log, open(checked_file, 'a', encoding='utf-8') as checked_log:
        for page in range(1, max_pages + 1):
            url = f'{base_url}?page={page}'
            print(f"Fetching {url}...")
            try:
                response = requests.get(url, timeout=10)
                if response.status_code != 200:
                    print(f"Status {response.status_code} for {url}")
                    break
            except Exception as e:
                print(f"Error fetching page: {e}")
                break

            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table')
            if not table:
                print("No table found")
                break
            rows = table.find_all('tr')[1:]  # skip header
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 11:
                    continue
                game_id = cols[0].text.strip()
                
                # Skip if already checked
                if game_id in checked_ids:
                    # print(f"Skipping already checked game {game_id}")
                    continue

                sgf_col = cols[10]  # SGF column
                sgf_link = sgf_col.find('a')
                if not sgf_link:
                    continue
                sgf_rel_url = sgf_link['href']
                sgf_url = f'https://katagotraining.org{sgf_rel_url}'
                
                # Download SGF
                try:
                    sgf_response = requests.get(sgf_url, timeout=10)
                    if sgf_response.status_code == 200:
                        content = sgf_response.text
                        
                        # Check board size
                        sz_match = re.search(r'SZ\[(\d+)\]', content)
                        if sz_match and int(sz_match.group(1)) != 19:
                            # Mark as checked even if skipped due to size, so we don't check again
                            checked_ids.add(game_id)
                            checked_log.write(f"{game_id}\n")
                            checked_log.flush()
                            continue
                        
                        sgf_path = os.path.join(sgf_dir, f'{game_id}.sgf')
                        with open(sgf_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        
                        # Analyze
                        long_kos = analyze_game(content)
                        if long_kos:
                            print(f"Found ko fight in {game_id}")
                            log.write(f'Game ID: {game_id}, URL: {sgf_url}\n')
                            for ko in long_kos:
                                log.write(f'  Ko fight from move {ko["start_move"]} to {ko["end_move"]}, span: {ko["span"]}, positions: {ko["positions"]}\n')
                            log.write('\n')
                            log.flush()
                        
                        # Mark as checked
                        checked_ids.add(game_id)
                        checked_log.write(f"{game_id}\n")
                        checked_log.flush()
                        
                        game_count += 1
                        if game_count >= max_games:
                            print(f'Reached max games: {max_games}')
                            return
                        time.sleep(delay)
                except Exception as e:
                    print(f"Error processing game {game_id}: {e}")
            time.sleep(delay)
    print(f'Analysis complete. Results in {results_file}')

if __name__ == "__main__":
    crawl_and_analyze()
