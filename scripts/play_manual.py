#!/usr/bin/env python3
"""
Open Pokemon Red in a visible window for manual play.
Controls: Arrow keys = D-pad, Z = A, X = B, Enter = Start, Backspace = Select
Press Ctrl+C in terminal to save and quit.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.game import PokemonGame

rom = sys.argv[1] if len(sys.argv) > 1 else "PokemonRed.gb"
save = sys.argv[2] if len(sys.argv) > 2 else "ready"

game = PokemonGame(rom, headless=False, speed=1)
game.start()

# Load existing save if available
if Path(f"saves/{save}.state").exists():
    game.load_state(save)
    print(f"Loaded save: {save}")

print()
print("=== POKEMON RED — MANUAL PLAY ===")
print("Controls:")
print("  Arrow keys = Move")
print("  Z = A button")
print("  X = B button") 
print("  Enter = Start")
print("  Backspace = Select")
print()
print("Play through the intro, pick your starter, get outside.")
print("Press Ctrl+C in this terminal when done — it will save automatically.")
print("=" * 40)

try:
    while game.pyboy.tick():
        pass
except KeyboardInterrupt:
    pass

game.save_state(save)
print(f"\nSaved as '{save}'")
print(game.format_state_for_ai())
game.stop()
