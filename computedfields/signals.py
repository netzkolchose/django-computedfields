from django.dispatch import Signal


# Signal sent upon start of the resolver. `sender` points to the resolver instance.
resolver_start = Signal()
"""Signal sent upon start of a tree update. `sender` points to the resolver instance."""


# Signal sent after a bulk update by the resolver.
resolver_update = Signal()
"""
Signal sent after a bulk update on a model.

Arguments sent with this signal:

- `sender`
    Resolver instance responsible for the updates.
- `model`
    The model class.
- `fields`
    Set of computed field names, that were updated.
- `pks`
    List of model instance pks, that were updated.

    
Note that this signal is sent immediately after the bulk update within the whole
(recursive) dependency tree update done by the resolver. Furthermore your handler
will be called under the update's transaction umbrella.

To not disrupt the resolver's tree update, you must avoid any raising code pattern
in your handler code. Database interactions should be avoided, as the state is not
fully resynced yet.

Also refer to the manual on how to use this signal in a safe way.
"""


# Signal sent upon exit of the resolver. `sender` points to the resolver instance.
resolver_exit = Signal()
"""Signal sent upon exit of a tree update. `sender` points to the resolver instance."""
