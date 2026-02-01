#!/usr/bin/env python3
"""
Pokemon Red — A* Pathfinding

Loads map JSON files and finds optimal paths between tiles.
Supports single-map pathfinding, warp-to-map routing, and cross-map routing.

Usage:
    from pathfinder import find_path, find_path_to_warp, find_route
    
    # Single map
    path = find_path("Pallet Town", 12, 12, 10, 0)
    # → ['left', 'left', 'up', 'up', ...]
    
    # Find warp to another map
    path = find_path_to_warp("Pallet Town", 9, 12, "Route 1")
    # → ['up', 'up', ...]
    
    # Cross-map routing
    route = find_route("Pallet Town", 9, 12, "Viridian City", 15, 8)
    # → [("Pallet Town", [...steps...]), ("Route 1", [...steps...]), ...]
"""

import os
import sys
import json
import heapq
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set
from collections import defaultdict

PROJECT = Path(__file__).resolve().parent.parent
MAPS_DIR = PROJECT / "game_state" / "maps"

# Direction vectors (matching map_scanner)
DIRECTIONS = {
    "up":    (0, -1),
    "down":  (0,  1),
    "left":  (-1, 0),
    "right": ( 1, 0),
}

OPPOSITE = {
    "up": "down", "down": "up",
    "left": "right", "right": "left",
}


def map_name_to_filename(map_name: str) -> str:
    """Convert a map name like 'Pallet Town' to 'pallet_town'."""
    return map_name.lower().replace("'", "").replace(" ", "_").replace(".", "")


def load_map(map_name: str) -> Optional[Dict[str, Any]]:
    """Load a map JSON file by name. Returns None if not found."""
    path = MAPS_DIR / f"{map_name_to_filename(map_name)}.json"
    if not path.exists():
        # Try exact filename match
        for f in MAPS_DIR.glob("*.json"):
            with open(f) as fh:
                data = json.load(fh)
                if data.get("map_name") == map_name:
                    return data
        return None
    with open(path) as f:
        return json.load(f)


def load_all_maps() -> Dict[str, Dict[str, Any]]:
    """Load all available map files. Returns dict of map_name -> map_data."""
    maps = {}
    for f in MAPS_DIR.glob("*.json"):
        try:
            with open(f) as fh:
                data = json.load(fh)
                maps[data["map_name"]] = data
        except (json.JSONDecodeError, KeyError):
            continue
    return maps


def _heuristic(x1: int, y1: int, x2: int, y2: int) -> int:
    """Manhattan distance heuristic for A*."""
    return abs(x1 - x2) + abs(y1 - y2)


def find_path(map_name: str, start_x: int, start_y: int, 
              goal_x: int, goal_y: int, 
              map_data: Optional[Dict] = None) -> Optional[List[str]]:
    """
    A* pathfinding on a single map.
    
    Args:
        map_name: Name of the map to pathfind on
        start_x, start_y: Starting tile coordinates
        goal_x, goal_y: Goal tile coordinates
        map_data: Optional pre-loaded map data (skips file load)
    
    Returns:
        List of direction strings ['up', 'right', ...] or None if no path found
    """
    if map_data is None:
        map_data = load_map(map_name)
    if map_data is None:
        raise ValueError(f"Map '{map_name}' not found in {MAPS_DIR}")
    
    tiles = map_data["tiles"]
    start_key = f"{start_x},{start_y}"
    goal_key = f"{goal_x},{goal_y}"
    
    # Verify start and goal exist in tile data
    if start_key not in tiles:
        raise ValueError(f"Start tile {start_key} not in map data for {map_name}")
    if goal_key not in tiles:
        raise ValueError(f"Goal tile {goal_key} not in map data for {map_name}")
    
    # A* search
    # Priority queue: (f_score, counter, x, y)
    counter = 0
    open_set = [(0 + _heuristic(start_x, start_y, goal_x, goal_y), counter, start_x, start_y)]
    came_from: Dict[Tuple[int, int], Tuple[int, int, str]] = {}  # (x,y) -> (prev_x, prev_y, direction)
    g_score: Dict[Tuple[int, int], int] = {(start_x, start_y): 0}
    closed: Set[Tuple[int, int]] = set()
    
    while open_set:
        f, _, cx, cy = heapq.heappop(open_set)
        
        if cx == goal_x and cy == goal_y:
            # Reconstruct path
            path = []
            cur = (goal_x, goal_y)
            while cur in came_from:
                px, py, direction = came_from[cur]
                path.append(direction)
                cur = (px, py)
            path.reverse()
            return path
        
        if (cx, cy) in closed:
            continue
        closed.add((cx, cy))
        
        tile_key = f"{cx},{cy}"
        tile = tiles.get(tile_key)
        if tile is None:
            continue
        
        for direction, (dx, dy) in DIRECTIONS.items():
            # Check if this direction is walkable (walk or warp counts as passable on same map)
            movement = tile.get(direction, "blocked")
            if movement == "blocked":
                continue
            
            # For warps, they leave the map — don't follow them in single-map pathfinding
            # unless the warp destination is actually the goal (edge case)
            if movement == "warp":
                # Check if stepping in this direction reaches the goal
                # Warps change maps, so normally skip. But the warp tile itself
                # might be the goal — that's already handled since we arrive AT the tile.
                continue
            
            nx, ny = cx + dx, cy + dy
            neighbor_key = f"{nx},{ny}"
            
            if neighbor_key not in tiles:
                continue
            if (nx, ny) in closed:
                continue
            
            new_g = g_score[(cx, cy)] + 1
            if new_g < g_score.get((nx, ny), float('inf')):
                g_score[(nx, ny)] = new_g
                f_score = new_g + _heuristic(nx, ny, goal_x, goal_y)
                counter += 1
                heapq.heappush(open_set, (f_score, counter, nx, ny))
                came_from[(nx, ny)] = (cx, cy, direction)
    
    return None  # No path found


def find_path_to_warp(map_name: str, start_x: int, start_y: int, 
                      target_map_name: str,
                      map_data: Optional[Dict] = None) -> Optional[List[str]]:
    """
    Find path to the nearest warp that leads to target_map_name.
    
    The returned path includes the final step INTO the warp.
    
    Returns:
        List of direction strings, or None if no path/warp found
    """
    if map_data is None:
        map_data = load_map(map_name)
    if map_data is None:
        raise ValueError(f"Map '{map_name}' not found")
    
    warps = map_data.get("warps", {})
    
    # Find all warp tiles that lead to target map
    warp_targets = []
    for warp_key, warp_dirs in warps.items():
        for direction, info in warp_dirs.items():
            if info.get("map_name") == target_map_name:
                wx, wy = [int(c) for c in warp_key.split(",")]
                warp_targets.append((wx, wy, direction))
    
    if not warp_targets:
        return None
    
    # Find shortest path to any warp tile, then add the warp step
    best_path = None
    
    for wx, wy, warp_direction in warp_targets:
        try:
            path = find_path(map_name, start_x, start_y, wx, wy, map_data=map_data)
            if path is not None:
                # Add the warp step
                full_path = path + [warp_direction]
                if best_path is None or len(full_path) < len(best_path):
                    best_path = full_path
        except ValueError:
            continue
    
    return best_path


def _build_map_graph() -> Dict[str, List[Tuple[str, str, int, int]]]:
    """
    Build a graph of map connections from all available map data.
    Returns: dict of map_name -> list of (dest_map_name, warp_tile_key, dest_x, dest_y)
    """
    all_maps = load_all_maps()
    graph: Dict[str, List[Tuple[str, str, int, int]]] = defaultdict(list)
    
    for map_name, data in all_maps.items():
        for warp_key, warp_dirs in data.get("warps", {}).items():
            for direction, info in warp_dirs.items():
                dest_name = info.get("map_name", "")
                dest_x = info.get("dest_x", 0)
                dest_y = info.get("dest_y", 0)
                graph[map_name].append((dest_name, warp_key, dest_x, dest_y))
    
    return graph


def find_route(current_map: str, cx: int, cy: int,
               dest_map: str, dx: int, dy: int) -> Optional[List[Tuple[str, List[str]]]]:
    """
    Cross-map routing: find a route from (current_map, cx, cy) to (dest_map, dx, dy).
    
    Uses BFS on the map graph to find the sequence of maps to traverse,
    then A* within each map to get the step-by-step path.
    
    Returns:
        List of (map_name, path_steps) tuples, or None if no route found.
        The path_steps for the last segment end at the destination.
        Intermediate segments end with a warp step.
    """
    if current_map == dest_map:
        # Same map — just pathfind directly
        path = find_path(current_map, cx, cy, dx, dy)
        if path is not None:
            return [(current_map, path)]
        return None
    
    # BFS on the map graph to find sequence of maps
    graph = _build_map_graph()
    all_maps = load_all_maps()
    
    # BFS: find shortest chain of maps from current_map to dest_map
    from collections import deque
    queue = deque()
    queue.append((current_map, [(current_map, cx, cy)]))
    visited_maps: Set[str] = {current_map}
    
    map_chains = []
    
    while queue:
        cur_map, chain = queue.popleft()
        
        if cur_map == dest_map:
            map_chains.append(chain)
            continue  # Keep searching for alternatives
        
        for dest_name, warp_key, dest_x, dest_y in graph.get(cur_map, []):
            if dest_name not in visited_maps and dest_name in all_maps:
                visited_maps.add(dest_name)
                new_chain = chain + [(dest_name, dest_x, dest_y)]
                queue.append((dest_name, new_chain))
    
    if not map_chains:
        return None
    
    # Use the shortest chain
    best_chain = min(map_chains, key=len)
    
    # Now build the actual paths for each segment
    route = []
    
    for i in range(len(best_chain)):
        seg_map, seg_x, seg_y = best_chain[i]
        
        if i == len(best_chain) - 1:
            # Last segment: pathfind to final destination
            if seg_map == dest_map:
                path = find_path(seg_map, seg_x, seg_y, dx, dy)
                if path is None:
                    return None
                route.append((seg_map, path))
        else:
            # Intermediate: pathfind to warp leading to next map
            next_map = best_chain[i + 1][0]
            path = find_path_to_warp(seg_map, seg_x, seg_y, next_map)
            if path is None:
                return None
            route.append((seg_map, path))
    
    return route


def print_path_visual(map_name: str, path: List[str], start_x: int, start_y: int):
    """Print a visual representation of the path on the map grid."""
    map_data = load_map(map_name)
    if not map_data:
        print("Can't visualize — map not loaded")
        return
    
    bounds = map_data["bounds"]
    
    # Trace the path
    path_tiles = set()
    x, y = start_x, start_y
    path_tiles.add((x, y))
    for step in path:
        dx, dy = DIRECTIONS[step]
        x, y = x + dx, y + dy
        path_tiles.add((x, y))
    
    # Print grid
    tiles = map_data["tiles"]
    for row_y in range(bounds["min_y"], bounds["max_y"] + 1):
        row = ""
        for col_x in range(bounds["min_x"], bounds["max_x"] + 1):
            key = f"{col_x},{row_y}"
            if (col_x, row_y) == (start_x, start_y):
                row += "S "
            elif (col_x, row_y) == (x, y):  # Using final x,y from path trace
                # Actually use last position
                pass
            if col_x == start_x and row_y == start_y:
                row = row[:-2] + "S "
            elif (col_x, row_y) in path_tiles:
                row = row[:-2] if len(row) >= 2 else row
                row += "* "
            elif key in tiles:
                row += ". "
            else:
                row += "# "
        print(row)


def main():
    """CLI for testing pathfinding."""
    import argparse
    parser = argparse.ArgumentParser(description="Pokemon Red Pathfinder")
    parser.add_argument("--map", required=True, help="Map name (e.g., 'Pallet Town')")
    parser.add_argument("--from", dest="start", required=True, help="Start coords 'x,y'")
    parser.add_argument("--to", dest="goal", required=True, help="Goal coords 'x,y'")
    parser.add_argument("--visual", action="store_true", help="Show visual path")
    parser.add_argument("--to-map", help="Find path to warp leading to this map")
    args = parser.parse_args()
    
    sx, sy = [int(c) for c in args.start.split(",")]
    
    if args.to_map:
        path = find_path_to_warp(args.map, sx, sy, args.to_map)
        print(f"Path to {args.to_map}: {path}")
    else:
        gx, gy = [int(c) for c in args.goal.split(",")]
        path = find_path(args.map, sx, sy, gx, gy)
        print(f"Path ({len(path)} steps): {path}")
    
    if path and args.visual:
        print()
        print_path_visual(args.map, path, sx, sy)


if __name__ == "__main__":
    main()
