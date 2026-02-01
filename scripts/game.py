#!/usr/bin/env python3
"""
Pokemon Red - PyBoy Wrapper for OpenClaw
Headless Game Boy emulator with screenshot capture, button input, and memory reading.
"""

import os
import sys
import json
import time
import base64
import io
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

try:
    from pyboy import PyBoy
    from PIL import Image
except ImportError:
    print("Missing dependencies. Install with: pip install pyboy pillow")
    sys.exit(1)


# ============================================================
# Pokemon Red Memory Addresses (International/English version)
# Source: https://datacrystal.tcrf.net/wiki/Pokémon_Red/Blue:RAM_map
# ============================================================

ADDR = {
    # Player position
    "player_y": 0xD361,
    "player_x": 0xD362,
    "map_id": 0xD35E,
    "player_direction": 0xC109,  # 0=down, 4=up, 8=left, 0xC=right

    # Party
    "party_count": 0xD163,
    "party_species": [0xD164, 0xD165, 0xD166, 0xD167, 0xD168, 0xD169],

    # Pokemon 1 (party slot 1)
    "pkmn1_species": 0xD16B,
    "pkmn1_hp": (0xD16C, 0xD16D),      # 2-byte big-endian
    "pkmn1_max_hp": (0xD18D, 0xD18E),
    "pkmn1_level": 0xD18C,
    "pkmn1_status": 0xD16F,
    "pkmn1_moves": [0xD173, 0xD174, 0xD175, 0xD176],
    "pkmn1_pp": [0xD188, 0xD189, 0xD18A, 0xD18B],

    # Badges
    "badges": 0xD356,

    # Money (BCD encoded, 3 bytes)
    "money": (0xD347, 0xD348, 0xD349),

    # Items
    "item_count": 0xD31D,
    "items_start": 0xD31E,  # Each item = 2 bytes (ID, quantity)

    # Game state
    "text_box_id": 0xD125,   # Non-zero when text box is active
    "battle_type": 0xD057,    # 0=no battle, 1=wild, 2=trainer
    "menu_item": 0xCC26,      # Currently selected menu item

    # Battle state
    "enemy_species": 0xCFD8,
    "enemy_hp": (0xCFE6, 0xCFE7),
    "enemy_level": 0xCFE8,
    "player_battle_hp": (0xD015, 0xD016),
    "player_battle_level": 0xD022,

    # Event flags / progress
    "oak_parcel_flag": 0xD74E,  # Bit 1 = got parcel
    "pokedex_owned_count": 0xD2F7,
}

# Pokemon species names (index -> name, Gen 1 internal IDs)
POKEMON_NAMES = {
    0x01: "Rhydon", 0x02: "Kangaskhan", 0x03: "Nidoran♂", 0x04: "Clefairy",
    0x05: "Spearow", 0x06: "Voltorb", 0x07: "Nidoking", 0x08: "Slowbro",
    0x09: "Ivysaur", 0x0A: "Exeggutor", 0x0B: "Lickitung", 0x0C: "Exeggcute",
    0x0D: "Grimer", 0x0E: "Gengar", 0x0F: "Nidoran♀", 0x10: "Nidoqueen",
    0x11: "Cubone", 0x12: "Rhyhorn", 0x13: "Lapras", 0x14: "Arcanine",
    0x15: "Mew", 0x16: "Gyarados", 0x17: "Shellder", 0x18: "Tentacool",
    0x19: "Gastly", 0x1A: "Scyther", 0x1B: "Staryu", 0x1C: "Blastoise",
    0x1D: "Pinsir", 0x1E: "Tangela", 0x21: "Growlithe", 0x22: "Onix",
    0x23: "Fearow", 0x24: "Pidgey", 0x25: "Slowpoke", 0x26: "Kadabra",
    0x27: "Graveler", 0x28: "Chansey", 0x29: "Machoke", 0x2A: "Mr. Mime",
    0x2B: "Hitmonlee", 0x2C: "Hitmonchan", 0x2D: "Arbok", 0x2E: "Parasect",
    0x2F: "Psyduck", 0x30: "Drowzee", 0x31: "Golem", 0x33: "Magmar",
    0x35: "Electabuzz", 0x36: "Magneton", 0x37: "Koffing", 0x39: "Mankey",
    0x3A: "Seel", 0x3B: "Diglett", 0x3C: "Tauros", 0x40: "Farfetch'd",
    0x41: "Venonat", 0x42: "Dragonite", 0x46: "Doduo", 0x47: "Poliwag",
    0x48: "Jynx", 0x49: "Moltres", 0x4A: "Articuno", 0x4B: "Zapdos",
    0x4C: "Ditto", 0x4D: "Meowth", 0x4E: "Krabby", 0x52: "Vulpix",
    0x53: "Ninetales", 0x54: "Pikachu", 0x55: "Raichu", 0x58: "Dratini",
    0x59: "Dragonair", 0x5A: "Kabuto", 0x5B: "Kabutops", 0x5C: "Horsea",
    0x5D: "Seadra", 0x60: "Sandshrew", 0x61: "Sandslash", 0x62: "Omanyte",
    0x63: "Omastar", 0x65: "Jigglypuff", 0x66: "Wigglytuff",
    0x67: "Eevee", 0x68: "Flareon", 0x69: "Jolteon", 0x6A: "Vaporeon",
    0x6B: "Machop", 0x6C: "Zubat", 0x6D: "Ekans", 0x6E: "Paras",
    0x6F: "Poliwhirl", 0x70: "Poliwrath", 0x71: "Weedle", 0x72: "Kakuna",
    0x73: "Beedrill", 0x74: "Dodrio", 0x75: "Primeape", 0x76: "Dugtrio",
    0x77: "Venomoth", 0x78: "Dewgong", 0x7B: "Caterpie", 0x7C: "Metapod",
    0x7D: "Butterfree", 0x7E: "Machamp", 0x80: "Golduck", 0x81: "Hypno",
    0x82: "Golbat", 0x83: "Mewtwo", 0x84: "Snorlax", 0x85: "Magikarp",
    0x88: "Muk", 0x8A: "Kingler", 0x8B: "Cloyster", 0x8D: "Electrode",
    0x8E: "Clefable", 0x8F: "Weezing", 0x90: "Persian", 0x91: "Marowak",
    0x93: "Haunter", 0x94: "Abra", 0x95: "Alakazam", 0x96: "Pidgeotto",
    0x97: "Pidgeot", 0x98: "Starmie", 0x99: "Bulbasaur", 0x9A: "Venusaur",
    0x9B: "Tentacruel", 0x9D: "Goldeen", 0x9E: "Seaking",
    0xA3: "Ponyta", 0xA4: "Rapidash", 0xA5: "Rattata", 0xA6: "Raticate",
    0xA7: "Nidorino", 0xA8: "Nidorina", 0xA9: "Geodude",
    0xAA: "Porygon", 0xAB: "Aerodactyl", 0xAD: "Magnemite",
    0xB0: "Charmander", 0xB1: "Squirtle", 0xB2: "Charmeleon",
    0xB3: "Wartortle", 0xB4: "Charizard", 0xB9: "Oddish",
    0xBA: "Gloom", 0xBB: "Vileplume", 0xBC: "Bellsprout",
    0xBD: "Weepinbell", 0xBE: "Victreebel",
}

# Move names (partial list of common moves)
MOVE_NAMES = {
    0x01: "Pound", 0x02: "Karate Chop", 0x03: "Double Slap", 0x04: "Comet Punch",
    0x05: "Mega Punch", 0x06: "Pay Day", 0x07: "Fire Punch", 0x08: "Ice Punch",
    0x09: "Thunder Punch", 0x0A: "Scratch", 0x0B: "Vice Grip", 0x0C: "Guillotine",
    0x0D: "Razor Wind", 0x0E: "Swords Dance", 0x0F: "Cut", 0x10: "Gust",
    0x11: "Wing Attack", 0x12: "Whirlwind", 0x13: "Fly", 0x14: "Bind",
    0x15: "Slam", 0x16: "Vine Whip", 0x17: "Stomp", 0x18: "Double Kick",
    0x19: "Mega Kick", 0x1A: "Jump Kick", 0x1B: "Rolling Kick",
    0x1C: "Sand Attack", 0x1D: "Headbutt", 0x1E: "Horn Attack",
    0x21: "Tackle", 0x22: "Body Slam", 0x23: "Wrap", 0x24: "Take Down",
    0x25: "Thrash", 0x26: "Double-Edge", 0x27: "Tail Whip", 0x28: "Poison Sting",
    0x2B: "Bite", 0x2C: "Growl", 0x2D: "Roar",
    0x2F: "Sing", 0x30: "Supersonic", 0x31: "Sonic Boom",
    0x33: "Acid", 0x34: "Ember", 0x35: "Flamethrower",
    0x37: "Water Gun", 0x38: "Hydro Pump", 0x39: "Surf",
    0x3A: "Ice Beam", 0x3B: "Blizzard", 0x3C: "Psybeam",
    0x3D: "Bubble Beam", 0x3E: "Aurora Beam",
    0x40: "Hyper Beam", 0x41: "Peck", 0x42: "Drill Peck",
    0x44: "Strength", 0x45: "Absorb", 0x46: "Mega Drain",
    0x47: "Leech Seed", 0x48: "Growth", 0x49: "Razor Leaf",
    0x4A: "Solar Beam", 0x4B: "Poison Powder", 0x4C: "Stun Spore",
    0x4D: "Sleep Powder", 0x4F: "Petal Dance",
    0x55: "Dig", 0x56: "Toxic", 0x57: "Confusion",
    0x58: "Psychic", 0x59: "Hypnosis", 0x5A: "Meditate",
    0x5B: "Agility", 0x5C: "Quick Attack", 0x5D: "Rage",
    0x5E: "Teleport", 0x5F: "Night Shade", 0x60: "Mimic",
    0x61: "Screech", 0x62: "Double Team", 0x63: "Recover",
    0x64: "Harden", 0x65: "Minimize", 0x66: "Smokescreen",
    0x67: "Confuse Ray", 0x68: "Withdraw", 0x69: "Defense Curl",
    0x6B: "Flash", 0x6F: "Rest",
    0x73: "Thunder Wave", 0x75: "Thunder", 0x76: "Thunderbolt",
    0x79: "Earthquake", 0x7A: "Fissure",
    0x7C: "Rock Slide", 0x7E: "Tri Attack",
    0x81: "Explosion", 0x82: "Fury Swipes",
    0x87: "Dream Eater", 0x8A: "Metronome",
    0x8D: "Self-Destruct", 0x92: "Skull Bash",
    0x99: "Softboiled",
}

# Map ID -> Name (partial, key areas)
MAP_NAMES = {
    0x00: "Pallet Town", 0x01: "Viridian City", 0x02: "Pewter City",
    0x03: "Cerulean City", 0x04: "Lavender Town", 0x05: "Vermilion City",
    0x06: "Celadon City", 0x07: "Fuchsia City", 0x08: "Cinnabar Island",
    0x09: "Indigo Plateau", 0x0A: "Saffron City", 0x0C: "Route 1",
    0x0D: "Route 2", 0x0E: "Route 3", 0x0F: "Route 4",
    0x10: "Route 5", 0x11: "Route 6", 0x12: "Route 7",
    0x13: "Route 8", 0x14: "Route 9", 0x15: "Route 10",
    0x16: "Route 11", 0x17: "Route 12", 0x18: "Route 13",
    0x19: "Route 14", 0x1A: "Route 15", 0x1B: "Route 16",
    0x1C: "Route 17", 0x1D: "Route 18", 0x1E: "Route 19",
    0x1F: "Route 20", 0x20: "Route 21", 0x21: "Route 22",
    0x22: "Route 23", 0x23: "Route 24", 0x24: "Route 25",
    0x25: "Player's House 1F", 0x26: "Player's House 2F",
    0x27: "Rival's House", 0x28: "Oak's Lab",
    0x29: "Viridian Pokecenter", 0x2A: "Viridian Mart",
    0x2B: "Viridian School", 0x2C: "Viridian House",
    0x2D: "Viridian Gym",
    0x36: "Pewter Gym", 0x3A: "Pewter Museum 1F",
    0x3C: "Cerulean Gym",
    0x32: "Viridian Forest Gate South", 0x33: "Viridian Forest",
    0xC3: "Mt. Moon 1F", 0xC4: "Mt. Moon B1F", 0xC5: "Mt. Moon B2F",
    0xF5: "Pokemon Tower 1F",
    0xEB: "SS Anne",
}


class PokemonGame:
    """Wrapper around PyBoy for Pokemon Red gameplay."""

    VALID_BUTTONS = ["up", "down", "left", "right", "a", "b", "start", "select"]

    def __init__(self, rom_path: str, headless: bool = True, speed: int = 1,
                 save_dir: str = "saves", screenshot_dir: str = "screenshots"):
        self.rom_path = rom_path
        self.headless = headless
        self.speed = speed
        self.save_dir = Path(save_dir)
        self.screenshot_dir = Path(screenshot_dir)
        self.save_dir.mkdir(exist_ok=True)
        self.screenshot_dir.mkdir(exist_ok=True)

        self.pyboy: Optional[PyBoy] = None
        self.frame_count = 0
        self.action_log: List[Dict] = []

    def start(self) -> bool:
        """Initialize and start the emulator."""
        if not os.path.exists(self.rom_path):
            print(f"ERROR: ROM not found at {self.rom_path}")
            return False

        try:
            if self.headless:
                self.pyboy = PyBoy(self.rom_path, window="null")
            else:
                self.pyboy = PyBoy(self.rom_path)

            self.pyboy.set_emulation_speed(self.speed)
            print(f"Game started: {self.pyboy.cartridge_title}")
            return True
        except Exception as e:
            print(f"ERROR starting emulator: {e}")
            return False

    def stop(self):
        """Stop the emulator."""
        if self.pyboy:
            self.pyboy.stop()
            self.pyboy = None

    def tick(self, frames: int = 1, render: bool = True) -> bool:
        """Advance the emulator by N frames."""
        if not self.pyboy:
            return False
        for _ in range(frames):
            if not self.pyboy.tick(1, render):
                return False
            self.frame_count += 1
        return True

    def press_button(self, button: str, hold_frames: int = 8, wait_frames: int = 8):
        """Press and release a button, then wait."""
        button = button.lower()
        if button not in self.VALID_BUTTONS:
            print(f"Invalid button: {button}")
            return
        self.pyboy.button_press(button)
        self.tick(hold_frames)
        self.pyboy.button_release(button)
        self.tick(wait_frames)

    def press_buttons(self, buttons: List[str], hold_frames: int = 8, wait_frames: int = 8):
        """Press a sequence of buttons."""
        for btn in buttons:
            self.press_button(btn, hold_frames, wait_frames)

    def screenshot(self, save: bool = False, filename: str = None) -> Image.Image:
        """Capture the current screen as a PIL Image."""
        img = self.pyboy.screen.image
        if save:
            if filename is None:
                filename = f"frame_{self.frame_count:08d}.png"
            path = self.screenshot_dir / filename
            img.save(str(path))
        return img

    def screenshot_base64(self) -> str:
        """Capture screenshot and return as base64 PNG string."""
        img = self.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    # ==========================================
    # Memory Reading
    # ==========================================

    def _read_byte(self, addr: int) -> int:
        return self.pyboy.memory[addr]

    def _read_word(self, addr_pair: Tuple[int, int]) -> int:
        """Read 2-byte big-endian value."""
        return (self.pyboy.memory[addr_pair[0]] << 8) | self.pyboy.memory[addr_pair[1]]

    def _read_bcd(self, addrs: Tuple[int, ...]) -> int:
        """Read BCD-encoded value."""
        result = 0
        for addr in addrs:
            byte = self.pyboy.memory[addr]
            result = result * 100 + ((byte >> 4) * 10 + (byte & 0x0F))
        return result

    def get_player_position(self) -> Dict[str, Any]:
        """Get player's current position."""
        map_id = self._read_byte(ADDR["map_id"])
        return {
            "x": self._read_byte(ADDR["player_x"]),
            "y": self._read_byte(ADDR["player_y"]),
            "map_id": map_id,
            "map_name": MAP_NAMES.get(map_id, f"Unknown (0x{map_id:02X})"),
            "facing": {0: "down", 4: "up", 8: "left", 0xC: "right"}.get(
                self._read_byte(ADDR["player_direction"]), "unknown"
            ),
        }

    def get_party(self) -> List[Dict[str, Any]]:
        """Get the player's Pokemon party."""
        count = self._read_byte(ADDR["party_count"])
        party = []

        # Base address for each party pokemon's detailed data
        # Each pokemon data block is 44 bytes (0x2C), starting at D16B
        PKMN_DATA_START = 0xD16B
        PKMN_DATA_SIZE = 0x2C

        for i in range(min(count, 6)):
            base = PKMN_DATA_START + (i * PKMN_DATA_SIZE)
            species_id = self.pyboy.memory[base]
            hp = (self.pyboy.memory[base + 1] << 8) | self.pyboy.memory[base + 2]
            level = self.pyboy.memory[base + 0x21]  # Actual level offset
            max_hp = (self.pyboy.memory[base + 0x22] << 8) | self.pyboy.memory[base + 0x23]
            status = self.pyboy.memory[base + 4]

            moves = []
            for j in range(4):
                move_id = self.pyboy.memory[base + 8 + j]
                if move_id > 0:
                    moves.append({
                        "id": move_id,
                        "name": MOVE_NAMES.get(move_id, f"Move_{move_id:02X}"),
                        "pp": self.pyboy.memory[base + 0x1D + j],
                    })

            party.append({
                "species_id": species_id,
                "name": POKEMON_NAMES.get(species_id, f"Pokemon_{species_id:02X}"),
                "level": level,
                "hp": hp,
                "max_hp": max_hp,
                "status": self._decode_status(status),
                "moves": moves,
            })

        return party

    def get_badges(self) -> Dict[str, bool]:
        """Get badge collection status."""
        badge_byte = self._read_byte(ADDR["badges"])
        badge_names = ["Boulder", "Cascade", "Thunder", "Rainbow",
                       "Soul", "Marsh", "Volcano", "Earth"]
        return {name: bool(badge_byte & (1 << i)) for i, name in enumerate(badge_names)}

    def get_money(self) -> int:
        """Get player's money."""
        return self._read_bcd(ADDR["money"])

    def get_battle_state(self) -> Optional[Dict[str, Any]]:
        """Get current battle state, or None if not in battle."""
        battle_type = self._read_byte(ADDR["battle_type"])
        if battle_type == 0:
            return None

        enemy_species = self._read_byte(ADDR["enemy_species"])
        return {
            "type": {1: "wild", 2: "trainer"}.get(battle_type, f"unknown_{battle_type}"),
            "enemy": {
                "species_id": enemy_species,
                "name": POKEMON_NAMES.get(enemy_species, f"Pokemon_{enemy_species:02X}"),
                "hp": self._read_word(ADDR["enemy_hp"]),
                "level": self._read_byte(ADDR["enemy_level"]),
            },
            "player": {
                "hp": self._read_word(ADDR["player_battle_hp"]),
                "level": self._read_byte(ADDR["player_battle_level"]),
            },
        }

    def is_in_battle(self) -> bool:
        return self._read_byte(ADDR["battle_type"]) != 0

    def is_text_active(self) -> bool:
        """Check if a text box / dialogue is currently showing."""
        return self._read_byte(ADDR["text_box_id"]) != 0

    def _decode_status(self, status_byte: int) -> str:
        if status_byte == 0:
            return "OK"
        statuses = []
        if status_byte & 0x40:
            statuses.append("PAR")
        if status_byte & 0x20:
            statuses.append("FRZ")
        if status_byte & 0x10:
            statuses.append("BRN")
        if status_byte & 0x08:
            statuses.append("PSN")
        if status_byte & 0x07:
            statuses.append(f"SLP({status_byte & 0x07})")
        return "/".join(statuses) if statuses else "OK"

    def get_full_state(self) -> Dict[str, Any]:
        """Get comprehensive game state for the AI."""
        state = {
            "position": self.get_player_position(),
            "party": self.get_party(),
            "badges": self.get_badges(),
            "money": self.get_money(),
            "in_battle": self.is_in_battle(),
            "text_active": self.is_text_active(),
            "frame": self.frame_count,
        }
        battle = self.get_battle_state()
        if battle:
            state["battle"] = battle
        return state

    # ==========================================
    # Save/Load
    # ==========================================

    def save_state(self, name: str = "quicksave"):
        """Save emulator state."""
        path = self.save_dir / f"{name}.state"
        with open(path, "wb") as f:
            self.pyboy.save_state(f)
        print(f"State saved: {path}")

    def load_state(self, name: str = "quicksave") -> bool:
        """Load emulator state."""
        path = self.save_dir / f"{name}.state"
        if not path.exists():
            print(f"Save state not found: {path}")
            return False
        with open(path, "rb") as f:
            self.pyboy.load_state(f)
        print(f"State loaded: {path}")
        return True

    # ==========================================
    # High-level helpers
    # ==========================================

    def wait_frames(self, n: int = 60):
        """Just advance N frames without input."""
        self.tick(n)

    def mash_a(self, times: int = 5, wait: int = 16):
        """Mash A button to advance dialogue."""
        for _ in range(times):
            self.press_button("a", hold_frames=4, wait_frames=wait)

    def format_state_for_ai(self) -> str:
        """Format game state as a readable string for the AI prompt."""
        state = self.get_full_state()
        lines = []

        pos = state["position"]
        lines.append(f"📍 Location: {pos['map_name']} ({pos['x']}, {pos['y']}) facing {pos['facing']}")

        badges = state["badges"]
        earned = [name for name, has in badges.items() if has]
        lines.append(f"🏅 Badges: {len(earned)}/8 — {', '.join(earned) if earned else 'None'}")
        lines.append(f"💰 Money: ¥{state['money']}")

        if state["party"]:
            lines.append(f"🎮 Party ({len(state['party'])} Pokemon):")
            for p in state["party"]:
                moves_str = ", ".join(f"{m['name']}({m['pp']}pp)" for m in p["moves"])
                lines.append(f"  • {p['name']} Lv{p['level']} [{p['hp']}/{p['max_hp']}HP] {p['status']} — {moves_str}")

        if state.get("battle"):
            b = state["battle"]
            lines.append(f"⚔️ BATTLE ({b['type']}):")
            lines.append(f"  Enemy: {b['enemy']['name']} Lv{b['enemy']['level']} [{b['enemy']['hp']}HP]")
            lines.append(f"  Your: [{b['player']['hp']}HP] Lv{b['player']['level']}")

        if state["text_active"]:
            lines.append("💬 Text/dialogue box is active")

        return "\n".join(lines)


def main():
    """CLI for testing the game wrapper."""
    parser = argparse.ArgumentParser(description="Pokemon Red - PyBoy Wrapper")
    parser.add_argument("rom", help="Path to Pokemon Red ROM (.gb)")
    parser.add_argument("--visible", action="store_true", help="Show emulator window")
    parser.add_argument("--speed", type=int, default=1, help="Emulation speed multiplier")
    parser.add_argument("--screenshot", action="store_true", help="Take a screenshot and save")
    parser.add_argument("--state", action="store_true", help="Print game state")
    parser.add_argument("--frames", type=int, default=60, help="Frames to advance")
    args = parser.parse_args()

    game = PokemonGame(args.rom, headless=not args.visible, speed=args.speed)
    if not game.start():
        sys.exit(1)

    try:
        # Advance some frames to let the game initialize
        game.tick(args.frames)

        if args.screenshot:
            img = game.screenshot(save=True, filename="test_screenshot.png")
            print(f"Screenshot saved ({img.size[0]}x{img.size[1]})")

        if args.state:
            print(game.format_state_for_ai())
            print()
            print("Full state JSON:")
            print(json.dumps(game.get_full_state(), indent=2))

    finally:
        game.stop()


if __name__ == "__main__":
    main()
