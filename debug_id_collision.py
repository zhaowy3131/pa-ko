import requests
from bs4 import BeautifulSoup

HISTORY_FILE = 'downloaded_history.txt'
RATING_URL = "https://katagotraining.org/networks/kata1/kata1-b28c512nbt-s12253653760-d5671874532/rating-games/"

print("Loading history...")
history = set()
try:
    with open(HISTORY_FILE, 'r') as f:
        for line in f:
            history.add(line.strip())
    print(f"Loaded {len(history)} IDs.")
except FileNotFoundError:
    print("History file not found.")

print(f"Fetching Rating Page 1: {RATING_URL}")
resp = requests.get(RATING_URL)
soup = BeautifulSoup(resp.text, 'html.parser')
rows = soup.find_all('tr')[1:]

print(f"Found {len(rows)} games on page.")

collision_count = 0
for row in rows:
    cols = row.find_all('td')
    if len(cols) < 11: continue
    
    game_id = cols[0].text.strip()
    print(f"Checking Rating ID: {game_id}", end=" ... ")
    
    if game_id in history:
        print("COLLISION! Found in history.")
        collision_count += 1
    else:
        print("New ID.")

if collision_count == len(rows):
    print("\nCONCLUSION: ALL IDs on page 1 are already in history!")
    print("This confirms ID collision (or you already downloaded them).")
else:
    print(f"\nCONCLUSION: Found {len(rows) - collision_count} new IDs.")
