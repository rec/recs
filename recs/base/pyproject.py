from importlib.metadata import metadata


def message() -> str:
    project = metadata('recs')
    desc, name = project['Summary'], project['Name']

    icon, *d, icon2 = desc.split()
    assert icon == icon2 and d
    desc = ' '.join(d)
    return f'{icon} {name}: {desc} {icon}'
