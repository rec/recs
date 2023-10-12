import string

PUNCTUATION = ' ()+,-.=[]_'
CHARS = (string.ascii_letters + string.digits + PUNCTUATION).encode()


def legal_filename(s) -> str:
    """Encode any string so it is safe for filenames"""

    def enc(i) -> str:
        if i in CHARS:
            return chr(i)
        if i < 0x100:
            return f'%{i:02x}'
        return f'%u{i:04x}'

    return ''.join(enc(i) for i in s.encode())
