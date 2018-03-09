from django.core.management.base import BaseCommand
from computedfields.models import ComputedFieldsModelType


class Command(BaseCommand):
    help = 'Update data for computed fields.'

    def handle(self, *args, **options):
        # simply run save on all computed models for now
        # dependencies will be resolved by the post_save handler
        for model in ComputedFieldsModelType._computed_models:
            for obj in model.objects.all():
                obj.save()
