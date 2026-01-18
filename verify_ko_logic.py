
from ko_crawler import analyze_game

# 1. Create a synthetic SGF with a clear Ko fight
# Board setup: Black sets up a Ko shape, White captures, Black threatens, White answers...
# Let's verify if the regex parses standard SGF format correctly first.

# Minimal 19x19 SGF with a Ko sequence.
# Positions:
# Black at B2 (bb), White at B3 (bc), Black at C3 (cc), White at C2 (cb) -> 2x2 shape is not ko.
# Simple Ko:
# Black: B2 (bb), D2 (db), C1 (ca), C3 (cc) -> Surrounds C2
# White: C2 (cb) captures nothing yet.
# Let's just write moves.

# Coordinates:
# a b c d e ...
# 1
# 2   X O
# 3 X . X O
# 4   X O 

# Let's make a simple Ko at C3 (cc) / D3 (dc).
# B: C4(cd), E3(ec), D2(db)
# W: D4(dd), F3(fc), E2(eb)
# ... this is hard to visualize mentally.

# Let's just use the logic:
# Ko at (2, 2) which is 'cc'.
# Black plays 'cc', White captures at 'dc' ? No.

# Simple Ko Shape:
#   B O B
# B O . O W
#   B O B

# Let's just write an SGF where we forcefully say moves happen.
# The analyzer relies on the Board logic to determine captures.
# So valid stones must be placed.

# Setup a Ko at row 2, col 2 ('cc')
# Neighboring stones must exist.
# Black stones at: (2,1) 'bc', (1,2) 'cb', (2,3) 'dc', (3,2) 'db' -> actually this captures the center 'cc'.
# Let's build a cross shape for Black.
# B: bc, cb, dc, db. 
# W: plays cc. -> Captures nothing. Self-atari?
# No, Ko is: 
#   B
# B W .
#   B

# Black: bc(2,1), cb(1,2), db(3,2).
# White: cc(2,2). 
# If Black plays dc(2,3), White at cc is captured? No, White at cc has liberty at dc? 
# If Black plays dc, W is surrounded.
# Let's automate the moves:
# 1. B[cb]
# 2. B[bc]
# 3. B[db]
# 4. B[ed] (dummy)
# 5. W[cc] (White is now at 2,2. Liberties: dc(2,3))
# 6. B[dc] (Atari. White has 0 liberties? No, W[cc] has 4 neighbors: cb(B), bc(B), db(B), dc(B). Yes, captured.)
#    -> Black captures W[cc]. Ko is at cc.

# Sequence:
# Setup:
# ;B[cb];B[bc];B[db];B[dd];W[ce];W[be];W[de] (White surrounds the black stones roughly to make them alive/safe)
#
# Real Ko start:
# ;W[cc] (White plays center)
# ;B[dc] (Black plays neighbor, capturing cc). Ko created at cc.
#   -> Ko capture 1.
# ;W[aa] (Threat)
# ;B[ab] (Answer)
# ;W[cc] (Recapture Ko at cc). Capture Black at dc?
#   Wait, if B captured W[cc] by playing dc... B is at dc.
#   For W to recapture B[dc], W must play at cc.
#   Does W capture B?
#   B[dc] neighbors: cc(W), dd(B), db(B). 
#   This is not a simple Ko. A simple ko is 1 stone vs 1 stone.

# Correct Simple Ko Shape:
#   B B
# B W . B
#   B B
#
# W is at (2,1). B is at (2,0), (1,1), (3,1).
# Spot (2,2) is empty.
# If B plays (2,2), W is captured.
# Then (2,1) is empty.
# If W plays (2,1), B is captured.

fake_sgf_moves = [
    # Setup Black "Cup"
    "B[cb]", "B[db]", "B[ec]", # B surrounds (2,2) from top, bottom, right.
    # Setup White "Cup" facing it?
    # Let's just surround the area.
    "B[bb]", # (1,1)
    "W[ca]", # (2,0) - White stone to be ko'd? No.
    
    # Simple Ko coordinates: (2,2) and (2,3) i.e. cc and dc
    # B at cb(2,1), db(2,3) -> No
    
    # 19x19 coords: a=0, b=1, c=2, d=3
    # Target Ko pair: [2,2] (cc) and [2,3] (dc)
    
    # Black Stones for shape:
    "B[bc]", # (1,2)
    "B[cd]", # (2,3) ... wait, let's use numeric logic to be sure.
    # We need:
    #   X O
    # X . O Y
    #   X O
    
    # Let's use the provided Board class logic to just find a valid ko.
    # Or just construct moves that we KNOW work.
    
    # P1 (Black) stones: (5,5), (5,7), (4,6)
    # P2 (White) stones: (6,6), (6,8), (7,7) ... this is getting messy.
    
    # Let's use the standard "Ponnuki" ko shape.
    #      B
    #    B W B
    #      .
    #    W B W
    #      W
    
    # Setup:
    "B[cc]", "B[ec]", "B[db]", # Surrounds dc(3,2) from top, bottom, left.
    "W[dd]", "W[fd]", "W[ee]", # Surrounds ed(4,3) ...
    
    # Let's try a linear approach.
    # B plays A. W plays B.
    # ...
    # Let's write a python script that USES the GoBoard class to Generate the SGF moves for us!
    # Much smarter.
]

def generate_ko_sgf():
    # We will generate a string.
    # Stones:
    # Black: (2,1) [bc], (1,2) [cb], (3,2) [db]
    # White: (2,4) [be]? No.
    
    # Shape:
    #   B(1,2)
    # B(2,1) . (2,2) W(2,3)
    #   B(3,2)
    #
    #   W(1,3)
    # W(2,2) ? (2,3) W(2,4)
    #   W(3,3)
    
    # This implies (2,2) and (2,3) are the fighting spots.
    
    # Black surrounds (2,2) except for (2,3).
    # White surrounds (2,3) except for (2,2).
    
    setup_moves = [
        # Black containment of (2,2)
        "B[cb]", # (1,2)
        "B[bc]", # (2,1)
        "B[db]", # (3,2)
        
        # White containment of (2,3)
        "W[cd]", # (2,3) - This is the key stone initially placed? 
                 # No, we want (2,3) to be empty initially or capture-able.
        
        # White surrounding (2,3)
        "W[cc]", # (2,2) - Wait, this is the other spot.
        # If W is at cc, and B plays dc (2,3).
        # We want B to capture W[cc].
        
        # So W must be at cc.
        # W[cc] needs 1 liberty at dc.
        # So W must be surrounded at (1,2), (2,1), (3,2)? 
        # Yes, B has stones there.
        
        # So:
        # 1. B places cups: cb, bc, db.
        # 2. W places cups: ad, bd, cd? No.
        
        # Let's look at the "Ko" logic in the file:
        # if len(captured) == 1 and new_group_liberties == 1: ko.
        
        # Setup:
        # B at (1,0), (0,1), (2,1). Empty (1,1).
        # W at (1,2), (0,2), (2,2).
        
        # Coordinates:
        # (r, c)
        # Spot A: (1,1). Spot B: (1,2).
        # B surrounds A: (0,1), (1,0), (2,1).
        # W surrounds B: (0,2), (1,3), (2,2).
        
        # Sequence:
        # 1. B plays (0,1) [ab]
        "B[ab]",
        # 2. B plays (1,0) [ba]
        "B[ba]",
        # 3. B plays (2,1) [cb]
        "B[cb]",
        
        # 4. W plays (0,2) [ac]
        "W[ac]",
        # 5. W plays (1,3) [bd]
        "W[bd]",
        # 6. W plays (2,2) [cc]
        "W[cc]",
        
        # Now:
        # Spot (1,1) 'bb' is empty. Surrounded by B(ab, ba, cb) and W(bb? no empty) and W?
        # Spot (1,2) 'bc' is... 
        # We want W to have a stone at (1,2) 'bc'.
        # And B to have a stone at (1,1) 'bb'.
        
        # Let's place W at 'bc' (1,2).
        "W[bc]",
        # Now W[bc] neighbors:
        # (0,2)W, (1,3)W, (2,2)W, (1,1)EMPTY.
        # So W[bc] is connected to the other whites?
        # NO. We want W[bc] to be ISOLATED and in Atari.
        # So (0,2), (1,3), (2,2) must be BLACK?
        # Yes!
        
        # RESTART SETUP
        # Target: W stone at (1,2) 'bc' captured by B play at (1,1) 'bb'.
        # W[bc] must have 0 liberties after B plays 'bb'.
        # Neighbors of bc(1,2): (0,2)ac, (1,3)bd, (2,2)cc, (1,1)bb.
        # So ac, bd, cc must be BLACK.
    ]
    
    moves = []
    # Black surrounds 'bc' (1,2)
    moves.append("B[ac]") # (0,2)
    moves.append("B[bd]") # (1,3)
    moves.append("B[cc]") # (2,2)
    
    # White surrounds 'bb' (1,1)
    # Neighbors of bb(1,1): (0,1)ab, (1,0)ba, (2,1)cb, (1,2)bc.
    # We want B to play 'bb' and be in Atari immediately.
    # So ab, ba, cb must be WHITE.
    moves.append("W[ab]") # (0,1)
    moves.append("W[ba]") # (1,0)
    moves.append("W[cb]") # (2,1)
    
    # Now the stage is set.
    # Spot (1,1) 'bb' is empty.
    # Spot (1,2) 'bc' is empty.
    
    # Move 10: W plays 'bc'.
    # W[bc] liberties: 'bb' (empty), 'ac'(B), 'bd'(B), 'cc'(B).
    # So W[bc] has 1 liberty at 'bb'.
    moves.append("W[bc]")
    
    # Move 11: B plays 'bb'.
    # B[bb] liberties: 'ba'(W), 'ab'(W), 'cb'(W), 'bc'(W).
    # But wait, B captures 'bc' first!
    # W[bc] is surrounded by B[ac], B[bd], B[cc] and now B[bb].
    # So W[bc] is captured. 
    # B[bb] remains.
    # B[bb] liberties: 'ba'(W), 'ab'(W), 'cb'(W), 'bc'(EMPTY now).
    # So B[bb] has 1 liberty at 'bc'.
    # This is a Ko!
    moves.append("B[bb]") # CAPTURE 1
    
    # Move 12: W makes threat.
    moves.append("W[dd]") 
    
    # Move 13: B answers.
    moves.append("B[de]")
    
    # Move 14: W recaptures at 'bc'.
    # Spot 'bc' is empty.
    # W plays 'bc'.
    # Neighbors: ac(B), bd(B), cc(B), bb(B).
    # But B[bb] has 0 liberties?
    # B[bb] neighbors: ab(W), ba(W), cb(W), bc(W-new).
    # Yes, B[bb] is captured!
    # W[bc] remains. Liberties: 1 at 'bb'.
    # Ko again!
    moves.append("W[bc]") # CAPTURE 2
    
    # Repeat...
    for i in range(10):
        # B threat
        moves.append("B[jj]")
        # W answer
        moves.append("W[kj]")
        # B recapture
        moves.append("B[bb]")
        
        # W threat
        moves.append("W[jk]")
        # B answer
        moves.append("B[kk]")
        # W recapture
        moves.append("W[bc]")
        
    return ";".join(moves)

full_sgf = "(;SZ[19];" + generate_ko_sgf() + ")"
print("Generated SGF:", full_sgf)

# Run analysis
try:
    results = analyze_game(full_sgf)
    print("Results:", results)
except Exception as e:
    print("Analysis failed:", e)
