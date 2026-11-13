class Reset(Exception):
    pass


def reset():
    raise Reset()
