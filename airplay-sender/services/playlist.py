"""Playlist model — ordered file queue with shuffle and loop support."""

import os
import random
from typing import Optional


class Playlist:
    def __init__(self):
        self._items: list[str] = []
        self._current: int = -1
        self._shuffle = False
        self._loop = False
        self._shuffle_order: list[int] = []
        self._shuffle_pos: int = 0

    # ------------------------------------------------------------------
    # Content management
    # ------------------------------------------------------------------

    def add(self, path: str) -> None:
        self._items.append(path)
        if self._current < 0:
            self._current = 0
        if self._shuffle:
            self._rebuild_shuffle()

    def remove(self, index: int) -> None:
        if not 0 <= index < len(self._items):
            return
        self._items.pop(index)
        if self._current >= len(self._items):
            self._current = len(self._items) - 1
        elif self._current > index:
            self._current -= 1
        if self._shuffle:
            self._rebuild_shuffle()

    def move(self, index: int, delta: int) -> int:
        """Shift item at *index* by *delta* steps. Returns the new index."""
        new_index = max(0, min(len(self._items) - 1, index + delta))
        if new_index == index:
            return index
        item = self._items.pop(index)
        self._items.insert(new_index, item)
        if self._current == index:
            self._current = new_index
        elif index < self._current <= new_index:
            self._current -= 1
        elif new_index <= self._current < index:
            self._current += 1
        if self._shuffle:
            self._rebuild_shuffle()
        return new_index

    def clear(self) -> None:
        self._items.clear()
        self._current = -1
        self._shuffle_order.clear()
        self._shuffle_pos = 0

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    @property
    def items(self) -> list[str]:
        return list(self._items)

    @property
    def current_index(self) -> int:
        return self._current

    @property
    def current(self) -> Optional[str]:
        if 0 <= self._current < len(self._items):
            return self._items[self._current]
        return None

    def select(self, index: int) -> None:
        if 0 <= index < len(self._items):
            self._current = index
            if self._shuffle:
                try:
                    self._shuffle_pos = self._shuffle_order.index(index)
                except ValueError:
                    self._shuffle_pos = 0

    def advance(self) -> Optional[str]:
        """Advance to the next track and return its path, or None at end (no loop)."""
        if not self._items:
            return None

        if self._shuffle:
            self._shuffle_pos += 1
            if self._shuffle_pos >= len(self._shuffle_order):
                if self._loop:
                    self._rebuild_shuffle()  # re-randomise for next cycle
                    self._shuffle_pos = 0
                else:
                    return None
            self._current = self._shuffle_order[self._shuffle_pos]
        else:
            next_idx = self._current + 1
            if next_idx >= len(self._items):
                if self._loop:
                    next_idx = 0
                else:
                    return None
            self._current = next_idx

        return self._items[self._current]

    def has_next(self) -> bool:
        if not self._items:
            return False
        if self._loop:
            return True
        if self._shuffle:
            return self._shuffle_pos < len(self._shuffle_order) - 1
        return self._current < len(self._items) - 1

    # ------------------------------------------------------------------
    # Shuffle
    # ------------------------------------------------------------------

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @shuffle.setter
    def shuffle(self, value: bool) -> None:
        self._shuffle = value
        if value:
            self._rebuild_shuffle()

    def _rebuild_shuffle(self) -> None:
        indices = list(range(len(self._items)))
        if 0 <= self._current < len(self._items):
            indices.remove(self._current)
            random.shuffle(indices)
            self._shuffle_order = [self._current] + indices
            self._shuffle_pos = 0
        else:
            random.shuffle(indices)
            self._shuffle_order = indices
            self._shuffle_pos = 0

    # ------------------------------------------------------------------
    # Loop
    # ------------------------------------------------------------------

    @property
    def loop(self) -> bool:
        return self._loop

    @loop.setter
    def loop(self, value: bool) -> None:
        self._loop = value

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def display_name(self, index: int) -> str:
        return os.path.basename(self._items[index]) if 0 <= index < len(self._items) else ""

    def __len__(self) -> int:
        return len(self._items)
