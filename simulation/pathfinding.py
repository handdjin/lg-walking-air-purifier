"""D* Lite shortest paths on a four-connected grid with unit movement cost.

D* Lite (Koenig & Likhachev, 2002) searches backward from the goal and keeps its
search tree between queries. When cells become blocked or free, or the robot moves,
only the affected part of the tree is repaired instead of planning from scratch.

`find_path()` keeps the original one-shot interface. `DStarLite` exposes the
incremental interface (`move_start()`, `update_cells()`) for replanning during travel.
"""

from heapq import heappop, heappush

from .house_map import coordinate


INF = float("inf")


class NoPathError(ValueError):
    """Raised when two walkable points are disconnected."""


def _manhattan(a, b):
    # Admissible and consistent because diagonal movement is unavailable.
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class DStarLite:
    """Incremental planner for a fixed goal on a HouseMap grid.

    g(s) is the current cost-to-goal estimate and rhs(s) the one-step lookahead
    value. A cell is consistent when g == rhs. The priority queue holds the
    inconsistent cells ordered by [min(g, rhs) + h(start, s) + km, min(g, rhs)].
    """

    def __init__(self, house_map, start, goal):
        start, goal = coordinate(start), coordinate(goal)
        if not house_map.is_walkable(start) or not house_map.is_walkable(goal):
            raise ValueError("Start and goal must both be walkable cells.")
        self._map = house_map
        self._blocked = set()  # Walkable map cells closed at run time
        self.start = start
        self.goal = goal
        self._last = start
        self._km = 0
        self._g = {}
        self._rhs = {goal: 0}
        self._queue = []        # Heap of (key, cell); stale entries are skipped lazily
        self._queued = {}       # cell -> its current key while the cell is in the queue
        self._push(goal)

    # ----- Grid helpers -----------------------------------------------------

    def _passable(self, cell):
        return cell not in self._blocked and self._map.is_walkable(cell)

    def _neighbors(self, cell):
        """Passable four-connected neighbors. Edges are symmetric with cost 1."""
        return [n for n in self._map.neighbors(cell) if n not in self._blocked]

    def _key(self, cell):
        best = min(self._g.get(cell, INF), self._rhs.get(cell, INF))
        return (best + _manhattan(self.start, cell) + self._km, best)

    # ----- Priority queue ---------------------------------------------------

    def _push(self, cell):
        key = self._key(cell)
        self._queued[cell] = key
        heappush(self._queue, (key, cell))

    def _top(self):
        """Return the smallest live entry, discarding outdated ones."""
        while self._queue:
            key, cell = self._queue[0]
            if self._queued.get(cell) == key:
                return key, cell
            heappop(self._queue)
        return (INF, INF), None

    # ----- Core D* Lite -----------------------------------------------------

    def _update_vertex(self, cell):
        if cell != self.goal:
            if self._passable(cell):
                self._rhs[cell] = min((1 + self._g.get(n, INF) for n in self._neighbors(cell)),
                                      default=INF)
            else:
                self._rhs[cell] = INF
        self._queued.pop(cell, None)
        if self._g.get(cell, INF) != self._rhs.get(cell, INF):
            self._push(cell)

    def _compute_shortest_path(self):
        while True:
            old_key, cell = self._top()
            start_g = self._g.get(self.start, INF)
            start_rhs = self._rhs.get(self.start, INF)
            if cell is None or (old_key >= self._key(self.start) and start_rhs == start_g):
                return
            new_key = self._key(cell)
            if old_key < new_key:
                self._push(cell)  # Key grew after km changed; reinsert with the fresh key
                continue
            heappop(self._queue)
            del self._queued[cell]
            g, rhs = self._g.get(cell, INF), self._rhs.get(cell, INF)
            if g > rhs:
                self._g[cell] = rhs
                for neighbor in self._neighbors(cell):
                    self._update_vertex(neighbor)
            else:
                self._g[cell] = INF
                self._update_vertex(cell)
                for neighbor in self._neighbors(cell):
                    self._update_vertex(neighbor)

    # ----- Public interface -------------------------------------------------

    def move_start(self, position):
        """Record that the robot moved; keys stay valid through the km offset."""
        position = coordinate(position)
        if not self._passable(position):
            raise ValueError("The new start must be a passable cell.")
        self._km += _manhattan(self._last, position)
        self._last = self.start = position

    def update_cells(self, blocked=(), cleared=()):
        """Close or reopen walkable map cells and repair the affected estimates."""
        changed = []
        for cell in map(coordinate, blocked):
            if cell == self.goal:
                raise ValueError("The goal cell cannot be blocked.")
            if self._map.is_walkable(cell) and cell not in self._blocked:
                self._blocked.add(cell)
                changed.append(cell)
        for cell in map(coordinate, cleared):
            if cell in self._blocked:
                self._blocked.discard(cell)
                changed.append(cell)
        for cell in changed:
            self._update_vertex(cell)
            for neighbor in self._map.neighbors(cell):
                self._update_vertex(neighbor)

    def path(self):
        """Return the current shortest path from start to goal, inclusive."""
        if not self._passable(self.start):
            raise NoPathError(f"{self.start} is blocked.")
        self._compute_shortest_path()
        if self._rhs.get(self.start, INF) == INF:
            raise NoPathError(f"{self.start} has no walkable route to {self.goal}.")
        current, route = self.start, [self.start]
        while current != self.goal:
            # Neighbor order from HouseMap.neighbors() breaks ties deterministically.
            current = min(self._neighbors(current), key=lambda n: self._g.get(n, INF))
            route.append(current)
            if len(route) > self._map.width * self._map.height:
                raise RuntimeError("D* Lite path extraction did not reach the goal.")
        return route


def find_path(house_map, start, goal):
    """Return the path coordinates, including the start and goal."""
    return DStarLite(house_map, start, goal).path()
