from django.core.management.base import BaseCommand, CommandError
from computedfields.models import ComputedFieldsModelType
from django.conf import settings
from computedfields.graph import ComputedModelsGraph
from django.utils.six.moves import cPickle as pickle


class Command(BaseCommand):
    help = 'Pickle dependency lookup map for computed fields to file.'

    def handle(self, *args, **options):
        if not hasattr(settings, 'COMPUTEDFIELDS_MAP'):
            raise CommandError('COMPUTEDFIELDS_MAP is not set in settings.py, abort.')

        with open(settings.COMPUTEDFIELDS_MAP, 'wb') as f:
            graph = ComputedModelsGraph(ComputedFieldsModelType._computed_models)
            graph.remove_redundant()
            pickle.dump(graph.generate_lookup_map(), f, pickle.HIGHEST_PROTOCOL)
