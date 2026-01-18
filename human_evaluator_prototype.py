from enum import Enum
import random

class LettingSeverity(Enum):
    NONE = 0        # AI 正常下 (真劍決勝)
    MICRO = 1       # 小讓 (緩手, 虧 2-5 目) -> 考驗基本功/官子
    MISTAKE = 2     # 中讓 (惡手, 虧 5-15 目) -> 考驗判斷力
    BLUNDER = 3     # 大勺子 (送禮, 虧 >15 目) -> 考驗戰鬥嗅覺

class HumanEvaluator:
    def __init__(self):
        self.scores = {
            "Stability": 0,   # 穩健度 (對應: 官子好/不退讓)
            "Sharpness": 0,   # 敏銳度 (對應: 抓住大勺子)
            "MissedOpps": 0   # 錯失良機次數
        }
        self.history = []

    def evaluate_move(self, move_num, ai_letting_type, human_point_loss):
        """
        move_num: 手數
        ai_letting_type: AI 上一手的讓棋程度 (LettingSeverity)
        human_point_loss: 人類這一手的目數損失 (正數代表虧損，負數代表賺了/懲罰了AI)
        """
        
        evaluation = "N/A"
        
        # 1. 應對 AI 的正常招法 (考驗基本實力)
        if ai_letting_type == LettingSeverity.NONE:
            if human_point_loss < 2.0:
                self.scores["Stability"] += 1
                evaluation = "Good: Held ground against strong AI"
            elif human_point_loss > 5.0:
                self.scores["Stability"] -= 1
                evaluation = "Bad: Collapsed under pressure"

        # 2. 應對 AI 的「小讓/緩手」 (考驗官子/穩健)
        elif ai_letting_type == LettingSeverity.MICRO:
            # 理論上 AI 虧了，人類不應該再虧回去
            if human_point_loss < 1.0:
                self.scores["Stability"] += 2 # 加倍獎勵
                evaluation = "Excellent: Secured the small advantage (Good Endgame)"
            elif human_point_loss > 3.0:
                # AI 送了 3 目，你虧了 3 目，等於沒送
                self.scores["Stability"] -= 2
                self.scores["MissedOpps"] += 1
                evaluation = "Poor: Gave back the gift"

        # 3. 應對 AI 的「大勺子」 (考驗技術/殺力)
        elif ai_letting_type == LettingSeverity.BLUNDER:
            # 大勺子通常意味著人類勝率/目數應該暴漲
            # human_point_loss 應該是負數 (賺大了)
            
            # 假設: AI 虧 20 目。如果人類應對正確，人類目數優勢應該 +20。
            # 如果 human_point_loss 接近 0 (代表人類只是正常下，沒去吃棋)，其實是虧了那個「本該賺到的 20 目」。
            # *註：這裡的 loss 定義為 (最佳手目數 - 實戰目數)*
            
            if human_point_loss < 2.0: 
                # 損失很小 -> 說明抓住了最佳手 -> 也就是抓住了勺子
                self.scores["Sharpness"] += 5
                evaluation = "BRILLIANT: Punished the blunder! (Good Technique)"
            elif human_point_loss > 10.0:
                # 損失巨大 -> 說明沒下到最佳手 -> 錯過了勺子
                self.scores["Sharpness"] -= 5
                self.scores["MissedOpps"] += 1
                evaluation = "BLIND: Missed the huge opportunity"

        self.history.append({
            "move": move_num,
            "context": ai_letting_type.name,
            "loss": human_point_loss,
            "eval": evaluation
        })

    def print_report(self):
        print("\n--- [ Human Performance Analysis ] ---")
        print(f"Stability (Endgame/Base): {self.scores['Stability']}")
        print(f"Sharpness (Tactics/Kill): {self.scores['Sharpness']}")
        print(f"Missed Opportunities:     {self.scores['MissedOpps']}")
        print("\nMove-by-Move Analysis:")
        for h in self.history:
            print(f"Move {h['move']} [{h['context'].ljust(8)}] Loss: {h['loss']:4.1f} -> {h['eval']}")

# ==========================================
# 模擬一盤棋 (Simulate a game)
# ==========================================
if __name__ == "__main__":
    evaluator = HumanEvaluator()
    
    # 模擬數據流: (Move, AI_Letting_Level, Human_Loss)
    game_stream = [
        (50, LettingSeverity.NONE, 1.5),    # 正常應對
        (52, LettingSeverity.MICRO, 0.5),   # AI 小讓，人穩住了 -> 官子好
        (54, LettingSeverity.NONE, 6.0),    # 人突然手滑
        (100, LettingSeverity.BLUNDER, 0.0), # AI 送大禮，人抓住了 (Loss=0 表示下到了最佳手) -> 技術好
        (102, LettingSeverity.NONE, 1.0),
        (150, LettingSeverity.MICRO, 4.0),  # AI 小讓，人沒接住 (虧回去)
        (200, LettingSeverity.BLUNDER, 15.0) # AI 送大禮，人無視了 (Loss大) -> 錯失良機
    ]
    
    print("Simulating Game Processing...")
    for move, let_type, loss in game_stream:
        evaluator.evaluate_move(move, let_type, loss)
        
    evaluator.print_report()
