import typing as t

T = t.TypeVar('T')


class PrefixDict(dict[str, T]):
    def __getitem__(self, key: str) -> T:
        try:
            return super().__getitem__(key)
        except KeyError:
            if not key:
                raise
            key = key.strip().lower()
            try:
                return super().__getitem__(key)
            except KeyError:
                pass

            if 1 == len(m := [v for k, v in self.items() if k.lower().startswith(key)]):
                return m[0]
            raise
