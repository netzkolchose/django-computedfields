from typing import Any


# global app defaults
DEFAULTS = {
    # whether to render helper pages in admin
    'COMPUTEDFIELDS_ADMIN': False,

    # whether to allow intermodel field recursions
    'COMPUTEDFIELDS_ALLOW_RECURSION': False,

    # update mode to use
    'COMPUTEDFIELDS_UPDATEMODE': 'FAST',

    # batchsize for update
    'COMPUTEDFIELDS_BATCHSIZE': 5000,

    # batchsize of select queries done by resolver
    'COMPUTEDFIELDS_QUERYSIZE': 10000
}


class DefaultsProxy:
    """
    Defaults proxy to allow runtime overrides from settings.py.
    """
    def __init__(self, defaults):
        self.defaults = defaults

    def __getattr__(self, key) -> Any:
        from django.conf import settings
        return getattr(settings, key, self.defaults[key])


settings = DefaultsProxy(DEFAULTS)
