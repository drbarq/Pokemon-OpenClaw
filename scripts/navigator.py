#!/usr/bin/env python3
"""
Pokemon Red — High-Level Navigator

Provides named-destination navigation for the AI player.
Handles route execution, battle interruptions, and collision recovery.

Usage:
    from navigator import Navigator
    
    nav = Navigator(game)
    result = nav.navigate_to("Viridian Pokecenter")
    result = nav.go_heal()
    result = nav.go_to_map("Route 1")
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

sys.path.insert(0, os.path.dirname(__file__))
from game import PokemonGame, MAP_NAMES
from pathfinder import find_path, find_path_to_warp, find_route, load_map

PROJECT = Path(__file__).resolve().parent.parent
MAPS_DIR = PROJECT / "game_state" / "maps"

# ============================================================
# Destination Registry
# Maps human-readable names to (map_name, x, y) coordinates
# These are the tiles you stand ON, not the building itself
# ============================================================

DESTINATIONS = {
    # Pallet Town
    "oak's lab":            ("Pallet Town", 12, 12),    # Door tile (warp up)
    "oaks lab":             ("Pallet Town", 12, 12),
    "player's house":       ("Pallet Town", 5, 6),      # Door tile
    "players house":        ("Pallet Town", 5, 6),
    "home":                 ("Pallet Town", 5, 6),
    "rival's house":        ("Pallet Town", 13, 6),     # Door tile
    "rivals house":         ("Pallet Town", 13, 6),
    "pallet town":          ("Pallet Town", 9, 12),     # Center of town
    
    # Route 1 exits
    "route 1 south":        ("Pallet Town", 10, 0),     # North exit to Route 1
    "route 1":              ("Pallet Town", 10, 0),
    
    # Viridian City
    "viridian city":        ("Viridian City", 18, 20),  # Center area (walkable)
    "viridian pokecenter":  ("Viridian City", 23, 26),  # Pokecenter door (warp at 23,26 → up)
    "viridian mart":        ("Viridian City", 29, 20),  # Mart door (warp at 29,20 → up)
    "viridian gym":         ("Viridian City", 32, 7),   # Gym door
    
    # Pewter City
    "pewter city":          ("Pewter City", 15, 12),
    "pewter pokecenter":    ("Pewter City", 17, 12),    # Approximate
    "pewter gym":           ("Pewter City", 10, 12),    # Approximate
    "pewter museum":        ("Pewter City", 8, 4),      # Approximate
    
    # Cerulean City
    "cerulean city":        ("Cerulean City", 15, 12),
    "cerulean pokecenter":  ("Cerulean City", 17, 10),  # Approximate
    "cerulean gym":         ("Cerulean City", 14, 8),   # Approximate
}

# Pokecenter locations by map name (for go_heal)
POKECENTERS = {
    "Viridian City": ("Viridian City", 23, 26),
    "Pewter City": ("Pewter City", 17, 12),
    "Cerulean City": ("Cerulean City", 17, 10),
    "Vermilion City": ("Vermilion City", 15, 6),
    "Lavender Town": ("Lavender Town", 13, 6),
    "Celadon City": ("Celadon City", 17, 10),
    "Saffron City": ("Saffron City", 15, 12),
    "Fuchsia City": ("Fuchsia City", 17, 12),
    "Cinnabar Island": ("Cinnabar Island", 5, 4),
}


class NavigationResult:
    """Result of a navigation attempt."""
    
    def __init__(self, success: bool, message: str, 
                 battle_interrupted: bool = False,
                 steps_taken: int = 0,
                 final_position: Optional[Dict] = None):
        self.success = success
        self.message = message
        self.battle_interrupted = battle_interrupted
        self.steps_taken = steps_taken
        self.final_position = final_position
    
    def __repr__(self):
        status = "✅" if self.success else ("⚔️" if self.battle_interrupted else "❌")
        return f"{status} {self.message} (steps={self.steps_taken})"
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "message": self.message,
            "battle_interrupted": self.battle_interrupted,
            "steps_taken": self.steps_taken,
            "final_position": self.final_position,
        }


class Navigator:
    """High-level navigation for the Pokemon Red AI player."""
    
    def __init__(self, game: PokemonGame, verbose: bool = True):
        self.game = game
        self.verbose = verbose
        self._step_hold = 8
        self._step_wait = 20
        self._settle_frames = 10
    
    def _log(self, msg: str):
        if self.verbose:
            print(f"[NAV] {msg}")
    
    def _get_pos(self) -> Dict:
        return self.game.get_player_position()
    
    def _execute_step(self, direction: str) -> Tuple[bool, bool]:
        """
        Execute a single movement step.
        Returns: (moved_successfully, battle_started)
        """
        before = self._get_pos()
        
        # Dismiss any stray text first
        self.game.press_button("b", hold_frames=4, wait_frames=8)
        
        # Take the step
        self.game.press_button(direction, hold_frames=self._step_hold, wait_frames=self._step_wait)
        self.game.tick(self._settle_frames)
        
        # Check for battle
        if self.game.is_in_battle():
            return False, True
        
        after = self._get_pos()
        moved = (after["x"] != before["x"] or after["y"] != before["y"] or 
                 after["map_id"] != before["map_id"])
        
        return moved, False
    
    def execute_path(self, path: List[str], max_retries: int = 2) -> NavigationResult:
        """
        Execute a sequence of movement steps.
        Handles NPC blocking with retries and detects battles.
        
        Args:
            path: List of direction strings
            max_retries: Times to retry a blocked step before giving up
        
        Returns:
            NavigationResult
        """
        steps_taken = 0
        
        for i, direction in enumerate(path):
            retries = 0
            while True:
                moved, battle = self._execute_step(direction)
                
                if battle:
                    return NavigationResult(
                        success=False,
                        message=f"Battle interrupted at step {i+1}/{len(path)}",
                        battle_interrupted=True,
                        steps_taken=steps_taken,
                        final_position=self._get_pos(),
                    )
                
                if moved:
                    steps_taken += 1
                    break
                
                retries += 1
                if retries > max_retries:
                    return NavigationResult(
                        success=False,
                        message=f"Blocked at step {i+1}/{len(path)} going {direction} (NPC or obstacle?)",
                        steps_taken=steps_taken,
                        final_position=self._get_pos(),
                    )
                
                # Wait a bit and try again (NPC may move)
                self._log(f"Blocked going {direction}, retry {retries}...")
                self.game.tick(30)
        
        return NavigationResult(
            success=True,
            message=f"Arrived! {steps_taken} steps taken",
            steps_taken=steps_taken,
            final_position=self._get_pos(),
        )
    
    def navigate_to(self, destination: str) -> NavigationResult:
        """
        Navigate to a named destination.
        
        Args:
            destination: Human-readable name like "Viridian Pokecenter", "Oak's Lab"
        
        Returns:
            NavigationResult
        """
        dest_lower = destination.lower().strip()
        
        if dest_lower not in DESTINATIONS:
            # Try fuzzy match
            matches = [k for k in DESTINATIONS if dest_lower in k or k in dest_lower]
            if len(matches) == 1:
                dest_lower = matches[0]
            elif matches:
                return NavigationResult(
                    success=False,
                    message=f"Ambiguous destination '{destination}'. Did you mean: {matches}?",
                    final_position=self._get_pos(),
                )
            else:
                return NavigationResult(
                    success=False,
                    message=f"Unknown destination '{destination}'. Known: {list(DESTINATIONS.keys())}",
                    final_position=self._get_pos(),
                )
        
        target_map, target_x, target_y = DESTINATIONS[dest_lower]
        pos = self._get_pos()
        current_map = pos["map_name"]
        
        self._log(f"Navigating to {destination}: {current_map}({pos['x']},{pos['y']}) → {target_map}({target_x},{target_y})")
        
        if current_map == target_map:
            # Same map — simple pathfinding
            map_data = load_map(current_map)
            if map_data is None:
                return NavigationResult(
                    success=False,
                    message=f"Map data for '{current_map}' not found. Run scan_current_map() first.",
                    final_position=pos,
                )
            
            path = find_path(current_map, pos["x"], pos["y"], target_x, target_y, map_data=map_data)
            if path is None:
                return NavigationResult(
                    success=False,
                    message=f"No path found from ({pos['x']},{pos['y']}) to ({target_x},{target_y}) on {current_map}",
                    final_position=pos,
                )
            
            self._log(f"Path: {len(path)} steps")
            return self.execute_path(path)
        
        else:
            # Cross-map routing
            route = find_route(current_map, pos["x"], pos["y"], target_map, target_x, target_y)
            if route is None:
                return NavigationResult(
                    success=False,
                    message=f"No route found from {current_map} to {target_map}. Maps may not be scanned yet.",
                    final_position=pos,
                )
            
            total_steps = sum(len(p) for _, p in route)
            self._log(f"Route: {len(route)} segments, {total_steps} total steps")
            
            total_taken = 0
            for seg_map, seg_path in route:
                self._log(f"  Segment: {seg_map} ({len(seg_path)} steps)")
                result = self.execute_path(seg_path)
                total_taken += result.steps_taken
                
                if not result.success:
                    result.steps_taken = total_taken
                    return result
                
                # After a warp, wait for map transition
                self.game.tick(30)
                # Dismiss any text
                for _ in range(3):
                    self.game.press_button("b", hold_frames=4, wait_frames=8)
            
            return NavigationResult(
                success=True,
                message=f"Arrived at {destination}! {total_taken} steps across {len(route)} maps",
                steps_taken=total_taken,
                final_position=self._get_pos(),
            )
    
    def go_to_map(self, target_map_name: str) -> NavigationResult:
        """Navigate to a specific map via the nearest warp."""
        pos = self._get_pos()
        current_map = pos["map_name"]
        
        if current_map == target_map_name:
            return NavigationResult(
                success=True,
                message=f"Already on {target_map_name}",
                final_position=pos,
            )
        
        # Try direct warp first
        map_data = load_map(current_map)
        if map_data:
            path = find_path_to_warp(current_map, pos["x"], pos["y"], target_map_name, map_data=map_data)
            if path:
                self._log(f"Direct warp to {target_map_name}: {len(path)} steps")
                result = self.execute_path(path)
                if result.success:
                    # Wait for warp transition
                    self.game.tick(30)
                    for _ in range(3):
                        self.game.press_button("b", hold_frames=4, wait_frames=8)
                return result
        
        # No direct warp — try cross-map routing to center of target map
        # Just navigate to the first tile we have data for on that map
        target_data = load_map(target_map_name)
        if target_data and target_data.get("tiles"):
            # Pick the first warp entry point or a central tile
            first_tile = next(iter(target_data["tiles"]))
            tx, ty = [int(c) for c in first_tile.split(",")]
            
            return self.navigate_to_coords(target_map_name, tx, ty)
        
        return NavigationResult(
            success=False,
            message=f"No route to {target_map_name} — map data may be missing",
            final_position=pos,
        )
    
    def navigate_to_coords(self, map_name: str, x: int, y: int) -> NavigationResult:
        """Navigate to specific coordinates on any map."""
        pos = self._get_pos()
        
        if pos["map_name"] == map_name:
            path = find_path(map_name, pos["x"], pos["y"], x, y)
            if path:
                return self.execute_path(path)
            return NavigationResult(
                success=False,
                message=f"No path to ({x},{y}) on {map_name}",
                final_position=pos,
            )
        
        route = find_route(pos["map_name"], pos["x"], pos["y"], map_name, x, y)
        if route is None:
            return NavigationResult(
                success=False,
                message=f"No route from {pos['map_name']} to {map_name}({x},{y})",
                final_position=pos,
            )
        
        total_taken = 0
        for seg_map, seg_path in route:
            result = self.execute_path(seg_path)
            total_taken += result.steps_taken
            if not result.success:
                result.steps_taken = total_taken
                return result
            self.game.tick(30)
            for _ in range(3):
                self.game.press_button("b", hold_frames=4, wait_frames=8)
        
        return NavigationResult(
            success=True,
            message=f"Arrived at {map_name}({x},{y})",
            steps_taken=total_taken,
            final_position=self._get_pos(),
        )
    
    def go_heal(self) -> NavigationResult:
        """Navigate to nearest Pokecenter and heal."""
        pos = self._get_pos()
        current_map = pos["map_name"]
        
        # Check if we're already on a map with a Pokecenter
        if current_map in POKECENTERS:
            pc_map, pc_x, pc_y = POKECENTERS[current_map]
            result = self.navigate_to_coords(pc_map, pc_x, pc_y)
            if result.success:
                return self._interact_with_nurse(result)
            return result
        
        # Find nearest Pokecenter via route length
        best_result = None
        best_route_len = float('inf')
        
        for pc_city, (pc_map, pc_x, pc_y) in POKECENTERS.items():
            try:
                route = find_route(current_map, pos["x"], pos["y"], pc_map, pc_x, pc_y)
                if route:
                    route_len = sum(len(p) for _, p in route)
                    if route_len < best_route_len:
                        best_route_len = route_len
                        best_result = (pc_map, pc_x, pc_y, pc_city)
            except (ValueError, Exception):
                continue
        
        if best_result is None:
            return NavigationResult(
                success=False,
                message="No reachable Pokecenter found",
                final_position=pos,
            )
        
        pc_map, pc_x, pc_y, city = best_result
        self._log(f"Nearest Pokecenter: {city} ({best_route_len} steps)")
        result = self.navigate_to_coords(pc_map, pc_x, pc_y)
        
        if result.success:
            return self._interact_with_nurse(result)
        return result
    
    def _interact_with_nurse(self, nav_result: NavigationResult) -> NavigationResult:
        """After arriving at Pokecenter door, enter and talk to nurse."""
        self._log("Entering Pokecenter and healing...")
        
        # Walk into the Pokecenter (up through door)
        self.game.press_button("up", hold_frames=8, wait_frames=20)
        self.game.tick(30)
        
        # Walk up to the nurse (she's at the counter, usually top-center)
        for _ in range(4):
            self.game.press_button("up", hold_frames=8, wait_frames=20)
        
        # Talk to nurse
        self.game.press_button("a", hold_frames=8, wait_frames=20)
        self.game.tick(30)
        
        # Confirm healing
        self.game.press_button("a", hold_frames=8, wait_frames=20)
        self.game.tick(120)  # Healing animation
        
        # Dismiss dialogue
        for _ in range(5):
            self.game.press_button("a", hold_frames=8, wait_frames=20)
            self.game.tick(20)
        
        pos = self._get_pos()
        party = self.game.get_party()
        all_healed = all(p["hp"] == p["max_hp"] for p in party) if party else True
        
        return NavigationResult(
            success=all_healed,
            message="Healed at Pokecenter! Party: " + str([f"{p['name']}:{p['hp']}/{p['max_hp']}" for p in party]),
            steps_taken=nav_result.steps_taken,
            final_position=pos,
        )
    
    @staticmethod
    def list_destinations() -> List[str]:
        """List all known destination names."""
        return sorted(set(DESTINATIONS.keys()))
    
    @staticmethod
    def add_destination(name: str, map_name: str, x: int, y: int):
        """Add a new destination to the registry (runtime only)."""
        DESTINATIONS[name.lower().strip()] = (map_name, x, y)
