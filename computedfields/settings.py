from typing import Any


# global app defaults
DEFAULTS = {
    # whether to render helper pages in admin
    'COMPUTEDFIELDS_ADMIN': False,

    # whether to allow intermodel field recursions
    'COMPUTEDFIELDS_ALLOW_RECURSION': False,

    # batchsize for bulk_update
    'COMPUTEDFIELDS_BATCHSIZE': 100,

    # batchsize for fast_update
    'COMPUTEDFIELDS_BATCHSIZE_FAST': 1000,

    # whether to use fast_update
    'COMPUTEDFIELDS_FASTUPDATE': False,

    # path to pickled map file
    'COMPUTEDFIELDS_MAP': None,

    # batchsize of select queries done by resolver
    'COMPUTEDFIELDS_QUERYSIZE': 2000
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
