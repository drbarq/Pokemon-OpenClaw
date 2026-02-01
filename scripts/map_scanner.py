#!/usr/bin/env python3
"""
Pokemon Red — Automated Map Scanner

BFS flood-fill scanner that discovers all reachable tiles from the player's
current position, tests movement in all 4 directions, detects warps, and
saves results as JSON map files.

Uses the PROVEN approach: save real PyBoy states at each tile, load them
to test movement. No RAM teleporting (that bypasses collision detection).

Usage:
    python scripts/map_scanner.py --save outside_after_parcel
    python scripts/map_scanner.py --save outside_after_parcel --chain
"""

import os
import sys
import io
import json
import time
import argparse
from pathlib import Path
from collections import deque
from typing import Dict, Any, Optional, Tuple, Set

sys.path.insert(0, os.path.dirname(__file__))
from game import PokemonGame, MAP_NAMES

PROJECT = Path(__file__).resolve().parent.parent
ROM_PATH = PROJECT / "PokemonRed.gb"
SAVES_DIR = PROJECT / "saves"
MAPS_DIR = PROJECT / "game_state" / "maps"
MAPS_DIR.mkdir(parents=True, exist_ok=True)

# Direction vectors
DIRECTIONS = {
    "up":    (0, -1),
    "down":  (0,  1),
    "left":  (-1, 0),
    "right": ( 1, 0),
}

# How many frames to advance after pressing a direction to let the game settle
MOVE_FRAMES = 16
SETTLE_FRAMES = 20


def map_name_to_filename(map_name: str) -> str:
    """Convert a map name like 'Pallet Town' to 'pallet_town'."""
    return map_name.lower().replace("'", "").replace(" ", "_").replace(".", "")


def get_map_path(map_name: str) -> Path:
    return MAPS_DIR / f"{map_name_to_filename(map_name)}.json"


def save_pyboy_state(game: PokemonGame) -> bytes:
    """Save the current PyBoy emulator state to bytes."""
    buf = io.BytesIO()
    game.pyboy.save_state(buf)
    return buf.getvalue()


def load_pyboy_state(game: PokemonGame, state_bytes: bytes):
    """Load a PyBoy emulator state from bytes."""
    game.pyboy.load_state(io.BytesIO(state_bytes))


def test_direction(game: PokemonGame, state_bytes: bytes, direction: str) -> Tuple[str, Optional[Dict]]:
    """
    From a saved state, try moving in the given direction.
    Returns: ("walk"|"blocked"|"warp", warp_info_or_None)
    
    warp_info is a dict with map_id, map_name, dest_x, dest_y if it's a warp.
    """
    # Load the state
    load_pyboy_state(game, state_bytes)
    game.tick(2)  # Let state settle
    
    # Read current position
    before_pos = game.get_player_position()
    before_x = before_pos["x"]
    before_y = before_pos["y"]
    before_map = before_pos["map_id"]
    
    # Press the direction button
    game.press_button(direction, hold_frames=8, wait_frames=SETTLE_FRAMES)
    game.tick(MOVE_FRAMES)
    
    # Read new position
    after_pos = game.get_player_position()
    after_x = after_pos["x"]
    after_y = after_pos["y"]
    after_map = after_pos["map_id"]
    
    # Check what happened
    if after_map != before_map:
        # Map changed — this is a warp
        return "warp", {
            "map_id": after_map,
            "map_name": MAP_NAMES.get(after_map, f"Unknown_0x{after_map:02X}"),
            "dest_x": after_x,
            "dest_y": after_y,
        }
    
    dx, dy = DIRECTIONS[direction]
    expected_x = before_x + dx
    expected_y = before_y + dy
    
    if after_x == expected_x and after_y == expected_y:
        return "walk", None
    else:
        return "blocked", None


def scan_map(game: PokemonGame, verbose: bool = True) -> Dict[str, Any]:
    """
    BFS flood-fill scan of the current map from the player's current position.
    
    For each reachable tile, tests all 4 directions and records whether
    movement is walk/blocked/warp.
    
    Returns a map data dict ready to save as JSON.
    """
    start_time = time.time()
    
    # Get initial position
    pos = game.get_player_position()
    start_x, start_y = pos["x"], pos["y"]
    map_id = pos["map_id"]
    map_name = MAP_NAMES.get(map_id, f"Unknown_0x{map_id:02X}")
    
    if verbose:
        print(f"Scanning: {map_name} (id={map_id}) starting at ({start_x}, {start_y})")
    
    # Data structures
    tiles: Dict[str, Dict[str, str]] = {}
    warps: Dict[str, Dict[str, Dict]] = {}
    tile_states: Dict[str, bytes] = {}  # (x,y) key -> saved state bytes
    
    # BFS queue: positions to explore
    queue = deque()
    visited: Set[Tuple[int, int]] = set()
    
    # Save initial state and start BFS
    initial_state = save_pyboy_state(game)
    start_key = f"{start_x},{start_y}"
    tile_states[start_key] = initial_state
    queue.append((start_x, start_y))
    visited.add((start_x, start_y))
    
    tile_count = 0
    
    while queue:
        cx, cy = queue.popleft()
        tile_key = f"{cx},{cy}"
        state = tile_states[tile_key]
        
        tile_count += 1
        if verbose and tile_count % 20 == 0:
            print(f"  Scanned {tile_count} tiles... (queue: {len(queue)})")
        
        tile_data = {}
        
        for direction in ["up", "down", "left", "right"]:
            result, warp_info = test_direction(game, state, direction)
            tile_data[direction] = result
            
            if result == "warp" and warp_info:
                if tile_key not in warps:
                    warps[tile_key] = {}
                warps[tile_key][direction] = warp_info
            
            elif result == "walk":
                # The neighbor tile is walkable — add it to BFS if not visited
                dx, dy = DIRECTIONS[direction]
                nx, ny = cx + dx, cy + dy
                if (nx, ny) not in visited:
                    visited.add((nx, ny))
                    # We need a state AT the neighbor tile
                    # Load the original state and walk there
                    load_pyboy_state(game, state)
                    game.tick(2)
                    game.press_button(direction, hold_frames=8, wait_frames=SETTLE_FRAMES)
                    game.tick(MOVE_FRAMES)
                    
                    # Verify we actually arrived
                    check_pos = game.get_player_position()
                    if check_pos["x"] == nx and check_pos["y"] == ny and check_pos["map_id"] == map_id:
                        neighbor_key = f"{nx},{ny}"
                        tile_states[neighbor_key] = save_pyboy_state(game)
                        queue.append((nx, ny))
        
        tiles[tile_key] = tile_data
    
    elapsed = time.time() - start_time
    
    # Calculate bounds
    all_x = [int(k.split(",")[0]) for k in tiles]
    all_y = [int(k.split(",")[1]) for k in tiles]
    
    map_data = {
        "map_name": map_name,
        "map_id": map_id,
        "bounds": {
            "min_x": min(all_x),
            "max_x": max(all_x),
            "min_y": min(all_y),
            "max_y": max(all_y),
        },
        "tiles": tiles,
        "warps": warps,
        "scan_seconds": round(elapsed, 1),
    }
    
    if verbose:
        print(f"Scan complete: {len(tiles)} tiles, {len(warps)} warps in {elapsed:.1f}s")
        for warp_key, warp_dirs in warps.items():
            for d, info in warp_dirs.items():
                print(f"  Warp: {warp_key} {d} → {info['map_name']} ({info['dest_x']},{info['dest_y']})")
    
    return map_data, tile_states


def save_map(map_data: Dict[str, Any], verbose: bool = True) -> Path:
    """Save map data to JSON file."""
    path = get_map_path(map_data["map_name"])
    with open(path, "w") as f:
        json.dump(map_data, f, indent=2)
    if verbose:
        print(f"Saved: {path}")
    return path


def scan_from_save(save_name: str, chain: bool = False, verbose: bool = True) -> Dict[str, Any]:
    """
    Load a save state, scan the current map, optionally chain-scan warp destinations.
    
    Args:
        save_name: Name of the save state (without .state extension)
        chain: If True, follow warps and scan connected maps too
        verbose: Print progress
    
    Returns:
        Dict of map_name -> map_data for all scanned maps
    """
    game = PokemonGame(str(ROM_PATH), headless=True, speed=0, save_dir=str(SAVES_DIR))
    if not game.start():
        raise RuntimeError("Failed to start emulator")
    
    try:
        if not game.load_state(save_name):
            raise RuntimeError(f"Failed to load save state: {save_name}")
        game.tick(30)
        
        scanned_maps: Dict[str, Any] = {}
        maps_to_scan: deque = deque()
        scanned_map_ids: Set[int] = set()
        
        # Start with current map
        pos = game.get_player_position()
        maps_to_scan.append({
            "save_name": save_name,
            "map_id": pos["map_id"],
        })
        
        while maps_to_scan:
            scan_info = maps_to_scan.popleft()
            
            if scan_info["map_id"] in scanned_map_ids:
                continue
            
            # Load the appropriate save state
            if not game.load_state(scan_info["save_name"]):
                print(f"  Skipping — couldn't load state for map_id {scan_info['map_id']}")
                continue
            game.tick(30)
            
            # Verify we're on the right map
            pos = game.get_player_position()
            if pos["map_id"] != scan_info["map_id"]:
                # If we need to reach this map via warp, we need a state on that map
                # This happens during chain scanning — we need to use warp states
                if "state_bytes" in scan_info:
                    load_pyboy_state(game, scan_info["state_bytes"])
                    game.tick(10)
                    pos = game.get_player_position()
                    if pos["map_id"] != scan_info["map_id"]:
                        print(f"  Skipping map_id {scan_info['map_id']} — can't reach it")
                        continue
                else:
                    print(f"  Skipping map_id {scan_info['map_id']} — wrong map after load")
                    continue
            
            # Scan this map
            map_data, tile_states = scan_map(game, verbose=verbose)
            scanned_map_ids.add(scan_info["map_id"])
            scanned_maps[map_data["map_name"]] = map_data
            save_map(map_data, verbose=verbose)
            
            # If chaining, queue up warp destinations
            if chain:
                for warp_key, warp_dirs in map_data["warps"].items():
                    for direction, warp_info in warp_dirs.items():
                        dest_map_id = warp_info["map_id"]
                        if dest_map_id not in scanned_map_ids:
                            _create_warp_state(game, map_data, warp_key, direction, 
                                             scan_info, dest_map_id, maps_to_scan, tile_states)
        
        return scanned_maps
    finally:
        game.stop()


def _create_warp_state(game, map_data, warp_key, direction, scan_info, dest_map_id, maps_to_scan, tile_states):
    """Helper to create a save state on the other side of a warp for chain scanning.
    
    Uses the tile_states dict (warp_key -> saved state bytes) to load the state 
    at the warp tile, then walks through the warp.
    """
    if warp_key not in tile_states:
        print(f"  Chain-scan: no saved state for warp tile {warp_key}")
        return
    
    try:
        # Load state at the warp tile
        load_pyboy_state(game, tile_states[warp_key])
        game.tick(5)
        
        # Walk through the warp
        game.press_button(direction, hold_frames=8, wait_frames=20)
        game.tick(40)
        
        # Mash B to dismiss any transition text
        for _ in range(5):
            game.press_button("b", hold_frames=4, wait_frames=10)
        game.tick(20)
        
        check = game.get_player_position()
        if check["map_id"] == dest_map_id:
            state_bytes = save_pyboy_state(game)
            maps_to_scan.append({
                "save_name": scan_info["save_name"],
                "map_id": dest_map_id,
                "state_bytes": state_bytes,
            })
            print(f"  Chain-scan: queued {MAP_NAMES.get(dest_map_id, f'0x{dest_map_id:02X}')} via warp {warp_key} {direction}")
        else:
            print(f"  Chain-scan: warp {warp_key} {direction} landed on map {check['map_id']}, expected {dest_map_id}")
    except Exception as e:
        print(f"  Chain-scan: error at warp {warp_key} {direction}: {e}")


def scan_current_map(game: PokemonGame) -> Dict[str, Any]:
    """
    Scan the map the player is currently on. 
    Saves and returns the map data.
    Used by llm_player for on-the-fly scanning.
    """
    pos = game.get_player_position()
    map_name = pos["map_name"]
    map_path = get_map_path(map_name)
    
    # Check if already scanned
    if map_path.exists():
        with open(map_path) as f:
            return json.load(f)
    
    # Scan it
    map_data, _tile_states = scan_map(game, verbose=False)
    save_map(map_data, verbose=False)
    return map_data


def main():
    parser = argparse.ArgumentParser(description="Pokemon Red Map Scanner")
    parser.add_argument("--save", required=True, help="Save state name (without .state)")
    parser.add_argument("--chain", action="store_true", help="Chain-scan through warps")
    parser.add_argument("--quiet", action="store_true", help="Less output")
    args = parser.parse_args()
    
    results = scan_from_save(args.save, chain=args.chain, verbose=not args.quiet)
    
    print(f"\n{'='*50}")
    print(f"Scan complete! {len(results)} map(s) scanned:")
    for name, data in results.items():
        print(f"  {name}: {len(data['tiles'])} tiles, {len(data['warps'])} warps")


if __name__ == "__main__":
    main()
