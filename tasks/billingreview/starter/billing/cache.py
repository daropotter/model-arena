"""A small in-process TTL cache."""

import threading


class TTLCache:
    def __init__(self, ttl, clock):
        self.ttl = ttl
        self.clock = clock
        self._data = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            value, expires = entry
            if expires <= self.clock():
                del self._data[key]
                return None
            return value

    def set(self, key, value):
        with self._lock:
            self._data[key] = (value, self.clock() + self.ttl)

    def delete(self, key):
        with self._lock:
            self._data.pop(key, None)
