from django.core.management.base import BaseCommand
from computedfields.models import active_resolver


class Command(BaseCommand):
    help = 'Update data for computed fields.'

    def handle(self, *args, **options):
        # simply run save on all computed models for now
        # dependencies will be resolved by the post_save handler
        for model in active_resolver.computed_models:
            for obj in model.objects.all():
                obj.save()
