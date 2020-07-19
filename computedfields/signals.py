from django.dispatch import Signal

resolver_update_done = Signal(providing_args=['changeset', 'update_fields', 'data'])
