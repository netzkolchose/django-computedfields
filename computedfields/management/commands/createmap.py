from django.core.management.base import BaseCommand, CommandError
from computedfields.models import ComputedFieldsModelType
from django.conf import settings
from computedfields.graph import ComputedModelsGraph
from django.utils.six.moves import cPickle as pickle


class Command(BaseCommand):
    help = 'Create lookup map for computed fields.'

    def handle(self, *args, **options):
        if not hasattr(settings, 'COMPUTEDFIELDS_MAP'):
            raise CommandError('COMPUTEDFIELDS_MAP is not set in settings.py, abort.')

        mapfile = settings.COMPUTEDFIELDS_MAP
        graph = ComputedModelsGraph(ComputedFieldsModelType._computed_models)
        graph.remove_redundant()
        map = graph.generate_lookup_map()
        with open(mapfile, 'w') as f:
            pickle.dump(map, f, pickle.HIGHEST_PROTOCOL)
