# AI 圍棋教練後端 API 規範 (Backend API Specification)

**版本**: 1.0
**狀態**: 草稿
**協議**: RESTful JSON / WebSocket (可選)

---

## 1. 核心架構：異步分析流 (Async Analysis Pipeline)

由於 KataGo 雙模型分析整盤棋可能耗時 (10s - 1min)，我們採用 **異步任務隊列** 設計。

1.  **Frontend**: 提交 SGF -> 獲得 `job_id`。
2.  **Backend (Queue)**: 
    *   啟動 KataGo Worker。
    *   **並行執行**: 
        *   Task A: `Model_9d` (Mentor) -> 計算標準 Loss。
        *   Task B: `Model_5k` (Peer) -> 計算直覺吻合度。
    *   **合併邏輯**: 對比 A 和 B 的輸出，生成 `ai_letting_severity` 和 `human_performance`。
    *   **寫入 DB**: 更新 `game_skills` 和 `human_performance` 表。
3.  **Frontend**: 輪詢或通過 WebSocket 接收完成通知 -> 獲取報告。

---

## 2. API 接口定義

### 2.1 對局上傳與分析 (Game Ingestion)

#### `POST /api/v1/games/analyze`
提交一盤棋進行分析。

**Request Body:**
```json
{
  "player_id": "user_12345",
  "sgf_content": "(;GM[1]FF[4]...)", 
  "player_color": "B",  // 用戶執黑還是執白
  "opponent_type": "AI", // "AI" 或 "HUMAN"
  "ai_level": "10k"     // 如果是對手是 AI，記錄其標稱等級
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "job_abc_789",
  "status": "queued",
  "estimated_time_seconds": 30
}
```

---

### 2.2 獲取對局報告 (Game Report)

#### `GET /api/v1/games/{game_id}/report`
獲取分析完成後的詳細報告。這是前端「覆盤頁面」的核心數據源。

**Response (200 OK):**
```json
{
  "game_id": "game_xyz_888",
  "meta": {
    "winner": "B",
    "score_gap": 2.5
  },
  
  // 1. 技能標籤 (本局亮點)
  "skills_detected": [
    { "id": "KO_MASTER", "name": "劫爭專家", "desc": "處理了 3 個複雜劫爭" },
    { "id": "SHARP_SHOOTER", "name": "局部敏銳", "desc": "第 125 手精準抓住了 AI 的勺子" }
  ],

  // 2. 棋局高光時刻 (用於生成卡片)
  "highlights": [
    { "move_num": 125, "type": "BRILLIANT", "comment": "一擊必殺！懲罰了 AI 的脫先。" },
    { "move_num": 50, "type": "STABLE", "comment": "面對 AI 的小讓步，穩穩收下利益。" }
  ],

  // 3. 手數詳情 (用於繪製勝率圖和讓棋標記) - 這是雙模型融合後的結果
  "moves": [
    {
      "move_num": 1,
      "coords": "qd",
      "winrate": 0.48,      // 9d 模型的勝率 (基準)
      "score_lead": -0.2,   // 9d 模型的目數
      "point_loss": 0.1,    // 用戶這手棋虧了多少
      
      // 關鍵：AI 讓棋標記 (上一手 AI 是否在讓?)
      "ai_letting_severity": "NONE", // NONE, MICRO, BLUNDER
      
      // 關鍵：人類表現 (針對上一手 AI 的回應)
      "human_eval": "GOOD" // GOOD, BAD, MISSED, EXCELLENT
    },
    // ... 更多手數
  ]
}
```

---

### 2.3 棋手畫像 (Player Profile)

#### `GET /api/v1/players/{player_id}/radar`
獲取五維雷達圖數據。

**Response:**
```json
{
  "level": "10級", // 內部評估等級
  "xp": 1250,      // 經驗值
  "radar": {
    "opening": 75,    // 佈局 (大局觀)
    "fighting": 40,   // 戰鬥 (死活/抓勺)
    "resilience": 60, // 韌性 (逆轉率)
    "endgame": 30,    // 官子 (穩健度)
    "technique": 80   // 技術 (劫爭)
  },
  "recent_trend": {
    "fighting": "+5", // 最近有進步
    "endgame": "-2"   // 最近在退步
  }
}
```

---

### 2.4 智能訓練推薦 (Smart Drill)

#### `GET /api/v1/training/next-task`
這就是「護航系統」的核心。根據畫像短板，從數據庫拉取一道題目。

**Request Params:**
*   `mode`: "auto" (自動護航) | "focus" (專項突破)

**Response:**
```json
{
  "task_id": "puzzle_death_897234_150",
  "type": "SHARP_SHOOTER", // 題目類型：局部死活
  "difficulty": "5k",
  "reason": "您的【戰鬥力】較弱，我們來做一道實戰死活題提升一下。",
  
  // SGF 片段 (初始盤面)
  "initial_state_sgf": "(;GM[1]...AB[dd][dp]...)", 
  
  // 正解路徑 (用於前端判斷對錯)
  // 這裡的數據來自 analysis.db 的 death_spots 記錄
  "target_region": {"r1":0, "c1":12, "r2":6, "c2":18} 
}
```

---

## 3. 內部數據處理流程 (Backend Logic)

### 3.1 雙模型融合邏輯 (Dual Model Fusion Strategy)

這部分邏輯運行在 Python 後端 (Worker)。

```python
def process_move(current_board, move, model_9d, model_5k):
    # 1. 導師視角 (Mentor View - 9d)
    # 用於計算絕對的好壞 (Point Loss)
    analysis_9d = model_9d.query(current_board)
    best_move_9d = analysis_9d.best_move
    actual_loss = analysis_9d.score - analysis_9d.score_after(move)

    # 2. 陪練視角 (Peer View - 5k)
    # 用於判斷這手棋是否"符合直覺"
    analysis_5k = model_5k.query(current_board)
    peer_winrate_drop = analysis_5k.winrate - analysis_5k.winrate_after(move)

    # 3. 綜合判斷 (Synthesis)
    
    # 判斷 AI (上一手) 是否讓棋
    ai_severity = "NONE"
    if prev_ai_loss > 15.0:
        ai_severity = "BLUNDER"
    elif prev_ai_loss > 3.0:
        # 如果 9d 覺得虧了，但 5k 覺得沒虧多少 -> 這是"隱蔽的緩手" (Micro Let)
        # 如果 5k 也覺得虧炸了 -> 這是"明顯的緩手"
        ai_severity = "MICRO"

    # 判斷 Human (這一手) 的表現
    human_eval = "NORMAL"
    if ai_severity == "BLUNDER":
        if actual_loss < 2.0:
            human_eval = "BRILLIANT" # 抓住了勺子
        else:
            human_eval = "BLIND"     # 瞎了
            
    elif ai_severity == "MICRO":
        if actual_loss < 1.0:
            human_eval = "STABLE"    # 穩健
        else:
            human_eval = "SOFT"      # 退讓

    return {
        "loss": actual_loss,
        "ai_letting": ai_severity,
        "human_eval": human_eval
    }
```

---

## 4. KataGo JSON 協議備忘

後端與 KataGo 子進程通信的標準格式（參考）：

**Input (Stdin):**
```json
{
  "id": "query_move_123",
  "moves": [["B", "Q4"], ["W", "D4"], ...],
  "rules": "chinese",
  "komi": 7.5,
  "boardXSize": 19,
  "boardYSize": 19,
  "includePolicy": true,
  "includeOwnership": true
}
```

**Output (Stdout):**
```json
{
  "id": "query_move_123",
  "turnNumber": 58,
  "moveInfos": [
    {
      "move": "R16",
      "order": 0,
      "scoreLead": 1.5,
      "winrate": 0.55,
      "prior": 0.23, // 策略網絡概率
      "lcb": 0.52    // 用於保守估計
    },
    ...
  ],
  "rootInfo": {
    "scoreLead": 1.4,
    "winrate": 0.54
  }
}
```

我們的後端需要解析這個 `Output`，提取 `scoreLead` 和 `winrate` 來驅動上述的分析邏輯。
