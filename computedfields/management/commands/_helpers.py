from django.core.management.base import CommandError
from django.apps import apps
from computedfields.models import active_resolver

class _Tqdm:
    def __init__(self, *args, **kwargs):
        pass
    def __enter__(self):
        return self
    def __exit__(self, type, value, traceback):
        pass
    def update(self, *args):
        pass


try:
    from tqdm import tqdm
except ImportError:
    tqdm = _Tqdm
HAS_TQDM = not tqdm == _Tqdm


def retrieve_computed_models(app_labels):
    computed_models = set(active_resolver.computed_models.keys())
    if not app_labels:
        return computed_models
    considered = set()
    for label in app_labels:
        app_model = label.split('.')
        try:
            app_config = apps.get_app_config(app_model[0])
        except LookupError as e:
            raise CommandError(str(e))
        if len(app_model) == 1:
            considered |= set(app_config.get_models()) & computed_models
        elif len(app_model) == 2:
            try:
                considered |= set([app_config.get_model(app_model[1])]) & computed_models
            except LookupError:
                raise CommandError(f'Unknown model: {label}')
        else:
            raise CommandError(f'Unsupported app_label.ModelName specification: {label}')
    return considered

def retrieve_models(app_labels):
    if not app_labels:
        return apps.get_models()
    considered = set()
    for label in app_labels:
        app_model = label.split('.')
        try:
            app_config = apps.get_app_config(app_model[0])
        except LookupError as e:
            raise CommandError(str(e))
        if len(app_model) == 1:
            considered |= set(app_config.get_models())
        elif len(app_model) == 2:
            try:
                considered |= set([app_config.get_model(app_model[1])])
            except LookupError:
                raise CommandError(f'Unknown model: {label}')
        else:
            raise CommandError(f'Unsupported app_label.ModelName specification: {label}')
    return considered
