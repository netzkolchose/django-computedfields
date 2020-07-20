from django.dispatch import Signal

#: Signal to indicate state changes of a resolver.
#: The resolver operates in 3 states:
#:
#: - 'initial'
#:    The initial state of the resolver for collecting models
#:    and computed field definitions. Resolver maps and ``computed_models``
#:    are not accessible yet.
#: - 'models_loaded'
#:    Second state of the resolver. Models and fields have been associated,
#:    ``computed_models`` is accessible. In this state it is not possible
#:    to add more models or fields. No resolver maps are loaded yet.
#: - 'maps_loaded'
#:    Third state of the resolver. The resolver is fully loaded and ready to go.
#:    Resolver maps were either loaded from pickle file or created from
#:    graph calculation.
#:
#: Arguments sent with this signal:
#:
#: - `sender`
#:    Resolver instance, that changed the state.
#: - `state`
#:    One of the state strings above.
#:
#: .. NOTE::
#:
#:     The signal for the boot resolver at state ``'initial'`` cannot be caught by
#:     a signal handler. For very early model/field setup work, inspect
#:     ``resolver.state`` instead.
state_changed = Signal(providing_args=['state'])

#: Signal to indicate updates done by the dependency tree resolver.
#:
#: Arguments sent with this signal:
#:
#: - `sender`
#:    Resolver instance, that was responsible for the updates.
#: - `changeset`
#:    Initial changeset, that triggered the computed field updates.
#:    This is equivalent to the first argument of ``update_dependent`` (model instance or queryset).
#: - `update_fields`
#:    Fields marked as changed in the changeset. Equivalent to `update_fields` in
#:    ``save(update_fields=...)`` or ``update_dependent(..., update_fields=...)``.
#: - `data`
#:    Mapping of models with instance updates of tracked computed fields.
#:    Since the tracking of individual instance updates in the dependecy tree is quite expensive,
#:    computed fields have to be enabled for update tracking by setting `signal_update=True`.
#:
#:    The returned mapping is in the form:
#:
#:    .. code-block:: python
#:
#:        {
#:            modelA: {
#:                        frozenset(updated_computedfields): set_of_affected_pks,
#:                        frozenset(['comp1', 'comp2']): {1, 2, 3},
#:                        frozenset(['comp2', 'compX']): {3, 45}
#:                    },
#:            modelB: {...}
#:        }
#:
#:    Note that a single computed field might be contained in several update sets (thus you have
#:    to aggregate further to pull all pks for a certain field update).
post_update = Signal(providing_args=['changeset', 'update_fields', 'data'])
