# PA-KO (AI 圍棋教練/護航系統) 項目總結報告

## 1. 項目核心定位
**PA-KO** 是一個基於 SGF（棋譜）大數據分析的圍棋教育與評估平台。其核心差異化在於：**不僅分析勝率，更通過「雙模型融合」技術區分「AI 故意讓棋」與「人類真實實力」**，從而為棋手生成精準的五維能力畫像並提供個性化訓練建議。

---

## 2. 核心技術方案：雙模型分析 (Dual-Model Strategy)
系統不只使用最強模型（如 KataGo 9d），而是通過兩個視角協同工作：
*   **導師視角 (Mentor, 9d)**：計算絕對的目數損失（Point Loss），判斷棋局的客觀好壞。
*   **陪練視角 (Peer, 5k)**：評估招法是否符合人類直覺。
*   **評估邏輯**：如果 AI 走了一手大勺子（故意讓棋），系統會觀察人類是否能「抓住機會」（體現 **Sharpness/敏銳度**）；如果 AI 只是輕微退讓，系統觀察人類是否能「穩穩收下」（體現 **Stability/穩健度**）。

---

## 3. 功能模塊梳理

### A. 數據採集與預處理 (Data Layer)
*   **下載器**：`sgf_downloader.py`, `archive_downloader.py` 負責從 `katagotraining.org` 等來源獲取原始數據。
*   **提取器**：`extract_archives.py` 處理壓縮包。

### B. 核心特徵分析引擎 (Analysis Layer)
*   **劫爭分析 (`ko_analyzer.py`)**：識別複雜的打劫過程及棋手對劫爭的處理能力。
*   **死活探測 (`death_analyzer.py`, `find_death_spots.py`)**：定位局部死活關鍵點，用於生成題目。
*   **佈局分類 (`find_openings.py`)**：識別棋手偏好的佈局風格（如宇宙流、平衡型）。
*   **激戰評估 (`find_exciting_games.py`)**：通過勝率波動和領先手交換頻率評估對局激烈程度。
*   **逆轉分析 (`find_endgame_reversals.py`)**：分析官子階段的逆轉，評估抗壓與收官能力。

### C. 棋手畫像與技能管理 (Evaluation Layer)
*   **技能管理器 (`skill_manager.py`)**：定義並提取 `KO_MASTER` (劫爭專家)、`DRAGON_SLAYER` (屠龍者) 等標籤。
*   **人類評估原型 (`human_evaluator_prototype.py`)**：實現基於 AI 讓棋標記的實戰表現算法。
*   **畫像維度**：佈局 (Opening)、戰鬥 (Fighting)、韌性 (Resilience)、官子 (Endgame)、技術 (Technique)。

---

## 4. 關鍵文件索引
*   `SPEC_GO_COACH_SYSTEM.md`: 系統整體架構設計與核心算法偽代碼。
*   `API_SPEC_GO_COACH.md`: 前後端異步分析流、雷達圖數據格式及訓練推薦接口定義。
*   `analysis.db` (SQLite): 存儲分析後的結構化數據（劫點、死活點、佈局類型、技能標籤）。

---

## 5. 開發進度與現狀

### 已完成項目
- [x] SGF 批量採集與解析框架。
- [x] 多維度特徵（劫、佈局、死活、逆轉）的提取算法。
- [x] 基於雙模型邏輯的「人類表現評價」算法原型。
- [x] 數據庫 Schema 設計及部分數據填充。

### 待辦事項 (Next Steps)
1.  **後端集成**：將 Python 分析腳本封裝為 Next.js 可調用的 REST API。
2.  **死活題自動生成**：編寫腳本將 `death_spots` 的座標數據自動轉化為可交互的 SGF 訓練題。
3.  **UI/UX 實現**：開發前端雷達圖可視化及「智能護航」訓練對弈界面。

---

## 6. 項目結語
PA-KO 項目已具備紮實的算法基礎和明確的技術路徑。後續開發重心應從「特徵提取」轉向「數據應用」，即如何將 `analysis.db` 中的靜態統計數據轉化為用戶可感知的實時護航建議與專項突破訓練。
