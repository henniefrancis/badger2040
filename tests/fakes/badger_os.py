"""Fake badger_os with an in-memory /state store."""
import json

store = {}
running_cleared = []
fail_load = False
fail_save = False


def reset():
    store.clear()
    running_cleared[:] = []
    global fail_load, fail_save
    fail_load = False
    fail_save = False


def state_load(app, defaults):
    if fail_load:
        raise ValueError("corrupt")
    raw = store.get(app)
    if raw is None:
        return False
    data = json.loads(raw)
    if isinstance(data, dict):
        defaults.update(data)
        return True
    return False


def state_save(app, data):
    if fail_save:
        raise OSError("flash full")
    store[app] = json.dumps(data)


def state_clear_running():
    running_cleared.append(True)
    return True


def get_disk_usage():
    return 0, 0, 0
