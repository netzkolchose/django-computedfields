from django.dispatch import Signal

state = Signal(providing_args=['state'])
resolver_update_done = Signal(providing_args=['changeset', 'update_fields', 'data'])
