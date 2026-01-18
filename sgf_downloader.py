import requests
from bs4 import BeautifulSoup
import re
import os
import time

# ================= CONFIGURATION =================
GAMES_INDEX_URL = 'https://katagotraining.org/games/'
BASE_DIR = 'sgf_downloads'
HISTORY_FILE = 'downloaded_history.txt'

MAX_PAGES = 100000 
# 設為極大值，確保不會因為重複而提早停止，除非真的全部爬完
STOP_THRESHOLD = 999999999 
DELAY = 0.5 
# =================================================

def load_history():
    processed = set()
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                processed.add(line.strip())
    return processed

def save_history(game_id):
    with open(HISTORY_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{game_id}\n")

def get_all_network_urls():
    """
    獲取首頁表格中所有 Network 的 Training 和 Rating 連結
    """
    print(f"正在獲取所有 Network 列表: {GAMES_INDEX_URL}")
    networks = []
    try:
        resp = requests.get(GAMES_INDEX_URL, timeout=15)
        if resp.status_code != 200:
            return []
            
        soup = BeautifulSoup(resp.text, 'html.parser')
        table = soup.find('table')
        if not table:
            return []
            
        rows = table.find_all('tr')[1:]
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 3: continue
            
            # 優先添加 Rating 連結 (Index 2)
            rating_link = cols[2].find('a')
            if rating_link:
                networks.append(f"https://katagotraining.org{rating_link['href']}")
            
            # 再添加 Training 連結 (Index 1)
            train_link = cols[1].find('a')
            if train_link:
                networks.append(f"https://katagotraining.org{train_link['href']}")
        
        return networks
    except Exception as e:
        print(f"獲取列表失敗: {e}")
        return []

def crawl_url(start_url, processed_ids):
    print(f"\n[開始任務] {start_url}")
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Compatible; SGFDownloader/1.3)'})
    
    # 修正：檢查 'training-games' 關鍵字，避免被域名中的 'katagotraining' 誤導
    sub_dir = 'training' if 'training-games' in start_url else 'rating'
    save_dir = os.path.join(BASE_DIR, sub_dir)
    os.makedirs(save_dir, exist_ok=True)

    base_url_clean = start_url.split('?')[0]
    total_new = 0
    consecutive_skips = 0
    TASK_STOP_THRESHOLD = 100 # 單個任務內連續跳過 100 個則停止
    
    for page in range(1, MAX_PAGES + 1):
        url = f"{base_url_clean}?page={page}"
        print(f"  正在讀取第 {page} 頁...", end='\r')
        
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                print(f"\n  無法讀取頁面 (Status {resp.status_code})，結束此 Network。\n")
                break
        except Exception as e:
            print(f"\n  網絡錯誤: {e}")
            break

        soup = BeautifulSoup(resp.text, 'html.parser')
        table = soup.find('table')
        if not table:
            print(f"\n  [Debug] Page {page}: No table found.")
            break
            
        rows = table.find_all('tr')[1:]
        if not rows:
            print(f"\n  [Debug] Page {page}: No rows found.")
            break

        # print(f"\n  [Debug] Page {page}: Found {len(rows)} rows.")

        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 11:
                # print(f"  [Debug] Row has {len(cols)} cols, skipping.")
                continue
            
            game_id = cols[0].text.strip()
            
            # 關鍵：不重複下載
            if game_id in processed_ids:
                consecutive_skips += 1
                continue
            
            # 發現新遊戲，重置計數
            consecutive_skips = 0
            
            link = cols[10].find('a')
            if not link:
                print(f"  [Debug] ID {game_id}: No link in col 10.")
                continue
            
            sgf_url = f"https://katagotraining.org{link['href']}"
            
            try:
                sgf_resp = session.get(sgf_url, timeout=10)
                if sgf_resp.status_code == 200:
                    content = sgf_resp.text
                    # 修正正則表達式警告
                    sz_match = re.search(r'SZ\[(\d+)\]', content)
                    is_valid = False
                    size_label = "未知"
                    
                    if sz_match:
                        size = int(sz_match.group(1))
                        if size == 19:
                            is_valid = True
                            size_label = "19路"
                        else:
                            if 'rating' in sub_dir:
                                print(f"    [跳過] {sub_dir} {game_id} 非19路 ({size})")
                    else:
                        # 找不到 SZ 標籤，可能是格式特殊，先下載再說
                        is_valid = True
                        size_label = "未知尺寸"
                        print(f"    [警示] {sub_dir} {game_id} 無法解析 SZ，強制下載。Header: {content[:20]}...")

                    if is_valid:
                        file_path = os.path.join(save_dir, f"{game_id}.sgf")
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        print(f"    [下載] {game_id} ({sub_dir} - {size_label})")
                        total_new += 1
                    
                    processed_ids.add(game_id)
                    save_history(game_id)
                else:
                    print(f"    Status {sgf_resp.status_code} for {game_id}")
                
                time.sleep(DELAY)
            except Exception as e:
                print(f"\n    [錯誤] {game_id}: {e}")

        # 檢查是否需要停止當前任務
        if consecutive_skips >= TASK_STOP_THRESHOLD:
            print(f"\n  [跳過] 連續 {consecutive_skips} 個已存在，結束此任務。")
            break

    print(f"  [完成] 此連結新增: {total_new} 個 SGF")

def main():
    processed_ids = load_history()
    print(f"歷史記錄: {len(processed_ids)} 筆")
    
    all_targets = get_all_network_urls()
    print(f"共發現 {len(all_targets)} 個任務目標（Network x 2 種類型）")
    
    for target_url in all_targets:
        crawl_url(target_url, processed_ids)
        
    print("\n[所有歷史任務完成]")

if __name__ == "__main__":
    main()
