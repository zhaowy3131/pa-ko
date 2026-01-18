python

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
            raise ValueError("Position occupied")
        
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
    move_pattern = re.findall(r';(B|W)\[([a-t]{0,2})\]', sgf_content)
    for color, coord in move_pattern:
        if not coord:  # pass
            row, col = -1, -1
        else:
            col_letter, row_letter = coord
            col = ord(col_letter) - ord('a')
            row = ord(row_letter) - ord('a')
        moves.append((1 if color == 'B' else 2, row, col))
    
    return size, moves

def analyze_game(sgf_content):
    size, moves = parse_sgf(sgf_content)
    board = GoBoard(size)
    ko_captures = []
    move_num = 1
    for color, row, col in moves:
        board.current_player = color
        captured = board.play(row, col)
        if board.ko_pos is not None:
            ko_captures.append((move_num, board.ko_pos))
        move_num += 1
    
    # Find alternating ko chains
    long_ko_fights = []
    if len(ko_captures) < 2:
        return long_ko_fights
    
    current_chain = [ko_captures[0]]
    for i in range(1, len(ko_captures)):
        prev_pos = current_chain[-1][1]
        curr_pos = ko_captures[i][1]
        if curr_pos != prev_pos:
            current_chain.append(ko_captures[i])
        else:
            # Check if current_chain is alternating with exactly two positions
            if len(current_chain) >= 2:
                positions = set([p[1] for p in current_chain])
                if len(positions) == 2:
                    first_move = current_chain[0][0]
                    last_move = current_chain[-1][0]
                    span = last_move - first_move + 1
                    if span > 10:
                        long_ko_fights.append({
                            'start_move': first_move,
                            'end_move': last_move,
                            'span': span,
                            'positions': positions
                        })
            current_chain = [ko_captures[i]]
    
    # Check last chain
    if len(current_chain) >= 2:
        positions = set([p[1] for p in current_chain])
        if len(positions) == 2:
            first_move = current_chain[0][0]
            last_move = current_chain[-1][0]
            span = last_move - first_move + 1
            if span > 10:
                long_ko_fights.append({
                    'start_move': first_move,
                    'end_move': last_move,
                    'span': span,
                    'positions': positions
                })
    
    return long_ko_fights

def crawl_and_analyze(network_id='kata1-b28c512nbt-s12253653760-d5671874532', max_pages=10, max_games=50, delay=1):
    base_url = f'https://katagotraining.org/networks/kata1/{network_id}/training-games/'
    sgf_dir = 'sgf_files'
    os.makedirs(sgf_dir, exist_ok=True)
    results_file = 'ko_fights_log.txt'
    
    game_count = 0
    with open(results_file, 'w', encoding='utf-8') as log:
        for page in range(1, max_pages + 1):
            url = f'{base_url}?page={page}'
            response = requests.get(url)
            if response.status_code != 200:
                break
            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table')
            if not table:
                break
            rows = table.find_all('tr')[1:]  # skip header
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 11:
                    continue
                sgf_col = cols[10]  # SGF column
                sgf_link = sgf_col.find('a')
                if not sgf_link:
                    continue
                sgf_rel_url = sgf_link['href']
                sgf_url = f'https://katagotraining.org{sgf_rel_url}'
                game_id = cols[0].text.strip()
                
                # Download SGF
                sgf_response = requests.get(sgf_url)
                if sgf_response.status_code == 200:
                    sgf_path = os.path.join(sgf_dir, f'{game_id}.sgf')
                    with open(sgf_path, 'w', encoding='utf-8') as f:
                        f.write(sgf_response.text)
                    
                    # Analyze
                    long_kos = analyze_game(sgf_response.text)
                    if long_kos:
                        log.write(f'Game ID: {game_id}, URL: {sgf_url}\n')
                        for ko in long_kos:
                            log.write(f'  Ko fight from move {ko["start_move"]} to {ko["end_move"]}, span: {ko["span"]}, positions: {ko["positions"]}\n')
                        log.write('\n')
                    
                    game_count += 1
                    if game_count >= max_games:
                        print(f'Reached max games: {max_games}')
                        return
                    time.sleep(delay)
            time.sleep(delay)
    print(f'Analysis complete. Results in {results_file}')

# Example usage: change network_id if needed, adjust max_pages and max_games
crawl_and_analyze()

這個程式是一個 Python 爬蟲，用來從 KataGo 訓練遊戲頁面爬取 SGF 文件，然後分析每個遊戲是否含有持續超過 10 步的打劫（ko fight）。它會下載 SGF 到 sgf_files 資料夾，並將有長打劫的遊戲記錄到 ko_fights_log.txt。需要安裝的套件：pip install requests beautifulsoup4它從指定的 network (預設是最新的) 的 training games 開始，分頁爬取（預設最多 10 頁，每頁約 20 遊戲）。
限制最多分析 50 個遊戲，以避免過多請求（可調整）。
分析邏輯：模擬棋盤，追蹤單石捕獲（ko 捕獲），找出交替在兩個位置的 ko 捕獲序列，如果序列跨度 >10 步，記錄下來。
注意：網站可能有反爬蟲機制，請禮貌使用，加延遲。程式假設 19x19、無分支 SGF。
如果需要其他 network，修改 network_id（從網站複製）。如果要分析 rating games，修改 URL 為 /rating-games/。



=======================================================
or the following plan for your choice.
=======================================================

直说：这事**不难，但也不“顺手”**。难点不在爬虫，而在**如何在不跑 KataGo 分析的前提下，从 SGF 里可靠地识别“打劫并持续 ≥10 手”**。不过可以工程化解决。

下面我给你一个**可落地方案**，不讲玄学。

---

## 一、总体思路（拆成三层）

### 1️⃣ 爬虫层（机械活）

* 目标：批量抓取 SGF 文件
* 不关心棋力、胜负、分析
* 只要 **原始 SGF**

### 2️⃣ 解析层（SGF → 落子序列）

* 解析 SGF
* 得到：

  * 棋盘尺寸（一般 19）
  * 手数序列
  * 每一步的坐标与执棋方

### 3️⃣ 规则层（**纯规则判断打劫**）

* **不跑 KataGo**
* **只用围棋规则**
* 识别：

  * 是否出现劫
  * 同一劫是否反复
  * 连续打劫是否 ≥ 10 手

---

## 二、关键点：什么叫“打劫 ≥10 手”

工程上你要一个**可判定定义**，否则永远扯皮。

### 推荐工程定义（实用版）

> **一个“劫循环”定义为：**
>
> * 出现一次单子劫（simple ko）
> * 双方围绕同一劫点反复提回
> * 在劫点及其相邻提子点之间往返
> * 累计相关落子 ≥ 10 手

这是**可算法化的**，而不是棋理争论。

---

## 三、核心算法（不跑引擎）

### 1️⃣ 棋盘模拟（必须）

你必须**自己实现一个简化围棋规则引擎**：

* 棋盘：`19x19`
* 规则：

  * 落子
  * 提子
  * 气的计算
  * **单劫判定**

不用管：

* 劫材好坏
* 大劫/三劫循环（先不碰）

---

### 2️⃣ 单劫判定规则（重点）

**标准单劫判定条件：**

当一步落子导致：

* 恰好提掉 **对方 1 子**
* 且提子后，该落子本身 **只剩 1 口气**
* 且这个状态与前一手棋盘完全相同（除去刚提那一子）

→ **这是单劫**

工程简化判定（够用）：

```text
if captured_stones == 1 and
   liberties(new_stone_group) == 1:
    ko_point = captured_stone_position
```

---

### 3️⃣ 跟踪“劫循环”

维护一个状态机：

```python
current_ko = None
ko_history = []
```

逻辑：

* 每当检测到一个 ko：

  * 如果 `current_ko is None`：

    * 开始一个新劫
    * 记录劫点坐标
    * 步数 = 1
  * else：

    * 如果是**同一个劫点**：

      * 步数 += 1
    * 否则：

      * 结束旧劫，开启新劫

* 当步数 ≥ 10：

  * **记录该 SGF**
  * 保存：

    * SGF 文件名
    * 劫点坐标
    * 起止手数
    * 劫长度

---

## 四、爬虫部分（随便搞）

### 示例（Python + requests）

```python
import requests
from pathlib import Path

BASE_URL = "https://example.com/katago-sgf/"
OUT = Path("sgf")

OUT.mkdir(exist_ok=True)

for i in range(100000):
    url = f"{BASE_URL}/{i}.sgf"
    r = requests.get(url, timeout=10)
    if r.status_code == 200 and r.text.startswith("("):
        (OUT / f"{i}.sgf").write_text(r.text)
```

你自己知道具体来源，我就不编 URL 了。

---

## 五、SGF 解析（别自己写）

用现成库，别犯傻。

### 推荐

* `sgfmill`
* `gomill`（老一点）

```bash
pip install sgfmill
```

```python
from sgfmill import sgf, boards

def load_game(path):
    with open(path, "rb") as f:
        game = sgf.Sgf_game.from_bytes(f.read())
    board = boards.Board(19)
    moves = game.get_main_sequence()
    return board, moves
```

---

## 六、最核心：棋盘 + 劫检测（伪代码）

```python
for move_number, move in enumerate(moves):
    color, point = move.get_move()
    captured = board.play(color, point)

    if len(captured) == 1:
        libs = board.get_liberties(point)
        if libs == 1:
            ko_point = captured[0]
            register_ko(ko_point, move_number)
```

⚠️ 注意：

* 要自己补：

  * `register_ko`
  * 劫状态机
  * 劫中断判断（比如中途走远了）

---

## 七、输出结果（别太花）

建议直接 CSV / JSON：

```json
{
  "sgf": "12345.sgf",
  "ko_point": "K10",
  "start_move": 87,
  "end_move": 102,
  "length": 16
}
```

---

## 八、现实提醒（不糖衣）

1. **90% SGF 没有长劫**
2. 真正 ≥10 手的劫：

   * 多见于职业棋
   * 或复杂死活题
3. 不跑引擎是对的
   👉 **你要的是“模式筛选”，不是“棋力评估”**

---

## 九、下一步你可以干什么（更狠）

如果你要升级，我建议：

* 把“劫循环”抽象成 **图结构**
* 顺便识别：

  * 接不归
  * 双活劫
  * 假劫
* 最终你会得到一个：

  > **围棋“战术模式数据库”**

这玩意比跑 KataGo 更值钱。

---

如果你愿意，下一步我可以直接：

* 给你一份 **最小可运行的完整 Python 脚本**
* 或帮你把它做成 **Rust（你是程序员，懂的）**

你选。

