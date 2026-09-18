"""A configuration mapping that records which keys the code actually reads.

The point is to stop inferring behaviour from source text. Asking "does the
string 'max_retries' appear somewhere in the code?" answers a question about
the source, not about the program: the key can be quoted in a comment, or read
under a different section, or spelled in a f-string that never executes. This
records real `__getitem__` / `.get()` calls made while the code runs.
"""


class RecordingDict(dict):
    """A dict that remembers every key looked up, at any depth.

    Nested dicts are wrapped lazily on access, so a section is only marked as
    read when the code descends into it.
    """

    def __init__(self, data, path=(), seen=None):
        super().__init__(data)
        self._path = path
        self.seen = {} if seen is None else seen

    def _record(self, key):
        self.seen[".".join((*self._path, str(key)))] = True

    def _wrap(self, key, value):
        if isinstance(value, dict):
            return RecordingDict(value, (*self._path, str(key)), self.seen)
        return value

    def __getitem__(self, key):
        self._record(key)
        return self._wrap(key, super().__getitem__(key))

    def get(self, key, default=None):
        self._record(key)
        if key not in self:
            return default
        return self._wrap(key, super().__getitem__(key))

    def __contains__(self, key):
        # `if 'scaling' not in config` is a read: the code is asking about it.
        self._record(key)
        return super().__contains__(key)

    def keys(self):
        # Iterating a section reads everything in it.
        for key in super().keys():
            self._record(key)
        return super().keys()

    def items(self):
        for key in super().keys():
            self._record(key)
        return super().items()

    @property
    def keys_read(self):
        return set(self.seen)
