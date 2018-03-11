from django.core.management.base import BaseCommand, CommandError
from computedfields.models import ComputedFieldsModelType
from django.conf import settings
from importlib import import_module
from computedfields.graph import ComputedModelsGraph
from os import path
try:
    from cPickle import dumps
except ImportError:
    from pickle import dumps

TMPL = \
'''data = b"""%s"""
try:
    from cPickle import loads
except ImportError:
    from pickle import loads

map = loads(data)
'''

class Command(BaseCommand):
    help = 'Create lookup map for computed fields.'

    def handle(self, *args, **options):
        if not hasattr(settings, 'COMPUTEDFIELDS_MAP'):
            raise CommandError('COMPUTEDFIELDS_MAP is not set in settings.py, abort.')
        try:
            module = import_module(settings.COMPUTEDFIELDS_MAP)
            filename = module.__file__.replace('pyc', 'py')
        except (ImportError, AttributeError, Exception):
            try:
                name_splitted = settings.COMPUTEDFIELDS_MAP.split('.')
                package = '.'.join(name_splitted[:-1])
                modname = name_splitted[-1]
                module = import_module(package)
                filename = path.join(path.dirname(module.__file__), modname+'.py')
            except ImportError:
                raise CommandError('Cannot create map file.')
        if not filename:
            raise CommandError('Cannot create map file.')

        # build the map and save to file
        graph = ComputedModelsGraph(ComputedFieldsModelType._computed_models)
        graph.remove_redundant()
        map = graph.generate_lookup_map()
        with open(filename, 'w') as f:
            f.write(TMPL % dumps(map))
