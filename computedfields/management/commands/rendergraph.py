from django.core.management.base import BaseCommand
from computedfields.models import ComputedFieldsModelType


class Command(BaseCommand):
    help = 'Show dependency graph for computed fields.'

    def add_arguments(self, parser):
        parser.add_argument('filename', nargs='+', type=str)

    def handle(self, *args, **options):
        ComputedFieldsModelType._graph.render(filename=options['filename'][0])
