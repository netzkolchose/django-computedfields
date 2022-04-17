from typing import cast
from django.core.management.base import BaseCommand
from django.db.models.fields.related import ForeignObjectRel
from computedfields.helper import modelname
from computedfields.models import active_resolver
from ._helpers import retrieve_models


#TODO: docs for created listing:
#   - src_model:
#       src_field: cf_model - cf_field
# - yellow field names are contributing fks


class Command(BaseCommand):
    help = 'Show computed field dependencies to related models.'

    def add_arguments(self, parser):
        parser.add_argument(
            'args', metavar='app_label[.ModelName]', nargs='*',
            help='Show computed field dependencies for specified app_label or app_label.ModelName.',
        )
    
    def handle(self, *app_labels, **options):
        models = retrieve_models(app_labels)
        for model in models:
            if not model in active_resolver._map:
                print(f'- {modelname(model)}: None')
                continue
            print(f'- {self.style.MIGRATE_LABEL(modelname(model))}:')
            for source_field, targets in active_resolver._map[model].items():
                real_source_field = model._meta.get_field(source_field)
                if real_source_field.is_relation and not real_source_field.concrete:
                    real_source_field = cast(ForeignObjectRel, real_source_field)
                    source_field = real_source_field.get_accessor_name() or ''
                if is_contrib(model, source_field):
                    source_field = self.style.WARNING(source_field)
                for target_model, target_tuple in targets.items():
                    target_fields, _ = target_tuple
                    print(f'    {source_field} -> {modelname(target_model)} [{", ".join(target_fields)}]')


def is_contrib(model, field):
    return field in active_resolver._fk_map.get(model, set())
