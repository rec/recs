PART_SPLITTER = '+'


def split(s: str, splitter: str = PART_SPLITTER) -> list[str]:
    return [i.strip() for i in s.split(splitter)]
