import requests
import re
from bs4 import BeautifulSoup

url = "https://katagotraining.org/networks/kata1/kata1-b28c512nbt-s12253653760-d5671874532/rating-games/"
print(f"Fetching {url}")

resp = requests.get(url)
soup = BeautifulSoup(resp.text, 'html.parser')
rows = soup.find_all('tr')[1:]

for i, row in enumerate(rows[:3]): # Check first 3 rows
    cols = row.find_all('td')
    if len(cols) < 11: continue
    
    game_id = cols[0].text.strip()
    link = cols[10].find('a')
    if not link: continue
    
    sgf_url = f"https://katagotraining.org{link['href']}"
    print(f"\nChecking Game {game_id}: {sgf_url}")
    
    sgf_resp = requests.get(sgf_url)
    content = sgf_resp.text
    print(f"SGF Header: {content[:50]}...")
    
    sz_match = re.search(r'SZ\[(\d+)\]', content)
    if sz_match:
        print(f"Found SZ: {sz_match.group(1)}")
    else:
        print("SZ NOT FOUND!")
