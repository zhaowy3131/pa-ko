import sqlite3
import random
import json

# ================= CONFIGURATION =================
DB_FILE = 'analysis.db'
SAMPLE_SIZE = 30 # Simulate a player with 30 games history
# =================================================

def get_random_games(conn, limit=30):
    c = conn.cursor()
    # Get all game_ids
    c.execute("SELECT DISTINCT game_id FROM game_skills")
    all_games = [row[0] for row in c.fetchall()]
    
    if not all_games:
        return []
        
    return random.sample(all_games, min(limit, len(all_games)))

def generate_report(player_name="VirtualPlayer_A"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Simulate History
    game_ids = get_random_games(conn, SAMPLE_SIZE)
    if not game_ids:
        print("No games found in database to analyze.")
        return

    print(f"Generating Diagnostic Report for {player_name}...")
    print(f"Based on {len(game_ids)} recent games.\n")

    # 2. Aggregate Skills
    # Dimensions: Opening, Fighting, Resilience, Endgame, Technique
    stats = {
        'Opening': 0,
        'Fighting': 0,
        'Resilience': 0,
        'Endgame': 0,
        'Technique': 0
    }
    
    # Details for evidence
    highlights = []

    placeholders = ','.join(['?'] * len(game_ids))
    query = f"SELECT game_id, skill_id, skill_value, description FROM game_skills WHERE game_id IN ({placeholders})"
    
    c.execute(query, game_ids)
    rows = c.fetchall()
    
    skill_counts = {}
    
    for gid, skill, val, desc in rows:
        skill_counts[skill] = skill_counts.get(skill, 0) + 1
        
        # Mapping Skills to Dimensions
        if skill in ['PERFECT_OPENING', 'PUNISHER', 'COSMIC_FLOW']:
            stats['Opening'] += 10 # Weighted score
        
        elif skill in ['DRAGON_SLAYER', 'SHARP_SHOOTER']:
            stats['Fighting'] += 15
            
        elif skill in ['MUD_FIGHTER']:
            stats['Resilience'] += 12
            
        elif skill in ['ENDGAME_WIZARD']:
            stats['Endgame'] += 20 # High value because rare
            
        elif skill in ['KO_MASTER']:
            stats['Technique'] += 10
            
        highlights.append(f"- Game {gid}: {desc} ({skill})")

    # 3. Normalize Scores (0-100 scale simulation)
    # Simple baseline: max possible score in sample size
    # This is arbitrary for the demo
    print(f"[DEBUG] Raw Stats: {stats}")
    radar_scores = {}
    for k, v in stats.items():
        # Cap at 100, normalize roughly
        score = min(100, int(v * 1.5)) 
        radar_scores[k] = score

    # 4. Generate Advice
    # Find weakest link
    weakest = min(radar_scores, key=radar_scores.get)
    strongest = max(radar_scores, key=radar_scores.get)
    
    advice_map = {
        'Opening': "Your opening game is shaky. You often fall behind early. \n   -> Recommended: Study 'Balanced' games from the Opening Database.",
        'Fighting': "You shy away from complex battles or miss killing opportunities. \n   -> Recommended: Solve 10 'Sharp Shooter' puzzles daily.",
        'Resilience': "You tend to collapse when the game gets messy. \n   -> Recommended: Review 'Mud Fighter' games to learn how to hang on.",
        'Endgame': "You are losing won games in the final 100 moves. \n   -> Recommended: Focus on 'Endgame Wizard' scenarios.",
        'Technique': "You lack specific tools like Ko handling. \n   -> Recommended: Watch 'Ko Master' replays."
    }

    # ================= OUTPUT =================
    print("--- [ PLAYER PROFILE ] ---")
    print(f"Style Tag: {strongest} Specialist")
    print(f"Weakness: {weakest}\n")
    
    print("--- [ 5-DIMENSION RADAR ] ---")
    print(json.dumps(radar_scores, indent=2))
    print("")
    
    print("--- [ DIAGNOSTIC & ADVICE ] ---")
    print(f"Diagnosis: {advice_map[weakest]}")
    print("")
    
    print(f"--- [ EVIDENCE ({len(highlights)} tags found) ] ---")
    # Show top 5 highlights
    for h in highlights[:5]:
        print(h)
    if len(highlights) > 5:
        print(f"... and {len(highlights)-5} more.")

    conn.close()

if __name__ == "__main__":
    generate_report()
