import typing as t

T = t.TypeVar('T')


class PrefixDict(dict[str, T]):
    def __getitem__(self, key: str) -> T:
        try:
            return super().__getitem__(key)
        except KeyError:
            pass

        error = 'unknown'
        if key := key.strip().lower():
            try:
                return super().__getitem__(key)
            except KeyError:
                pass

            matches = [v for k, v in self.items() if k.lower().startswith(key)]
            if len(matches) == 1:
                return matches[0]
            if matches:
                error = 'ambiguous'

        raise KeyError(key, error)
