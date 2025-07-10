from threading import local

_STORAGE = local()

# thread local storage to hold pk lists
# for deletes/updates from signal handlers

def get_DELETES():
    try:
        return _STORAGE.DELETES
    except AttributeError:
        _STORAGE.DELETES = {}
    return _STORAGE.DELETES

def get_M2M_REMOVE():
    try:
        return _STORAGE.M2M_REMOVE
    except AttributeError:
        _STORAGE.M2M_REMOVE = {}
    return _STORAGE.M2M_REMOVE

def get_M2M_CLEAR():
    try:
        return _STORAGE.M2M_CLEAR
    except AttributeError:
        _STORAGE.M2M_CLEAR = {}
    return _STORAGE.M2M_CLEAR

def get_UPDATE_OLD():
    try:
        return _STORAGE.UPDATE_OLD
    except AttributeError:
        _STORAGE.UPDATE_OLD = {}
    return _STORAGE.UPDATE_OLD


# get/set not_computed context
def get_not_computed_context():
    return getattr(_STORAGE, 'not_computed_context', None)

def set_not_computed_context(ctx):
    _STORAGE.not_computed_context = ctx
