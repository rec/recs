import string

PUNCTUATION = ' ()+,-.=[]_/'
CHARS = set(string.ascii_letters + string.digits + PUNCTUATION)


def legal_filename(s: str) -> str:
    """Encode any string so it is safe for filenames"""

    def enc(c: str) -> str:
        if c in CHARS:
            return c
        i = ord(c)
        if i < 0x100:
            return f'%{i:02x}'
        return f'%u{i:04x}'

    return ''.join(enc(i) for i in s)
