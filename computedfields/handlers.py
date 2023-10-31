"""
Module containing the database signal handlers.

The handlers are registered during application startup
in ``apps.ready``.

.. NOTE::

    The handlers are not registered in the managment
    commands ``makemigrations``, ``migrate`` and ``help``.
"""
from threading import local
from django.db import transaction
from .resolver import active_resolver
from .settings import settings

# typing imports
from typing import Any, Dict, Iterable, List, Set, Type, cast
from django.db.models import Model



# thread local storage to hold
# the pk lists for deletes/updates
STORAGE = local()
STORAGE.DELETES = {}
STORAGE.M2M_REMOVE = {}
STORAGE.M2M_CLEAR = {}
STORAGE.UPDATE_OLD = {}

DELETES = STORAGE.DELETES
M2M_REMOVE = STORAGE.M2M_REMOVE
M2M_CLEAR = STORAGE.M2M_CLEAR
UPDATE_OLD = STORAGE.UPDATE_OLD


def get_old_handler(sender: Type[Model], instance: Model, **kwargs) -> None:
    """
    ``get_old_handler`` handler.

    ``pre_save`` signal handler to spot incoming fk relation changes.
    This is needed to correctly update old relations after fk changes,
    that would contain dirty computed field values after a save.
    The actual updates on old relations are done during ``post_save``.
    Skipped during fixtures.
    """
    # do not handle fixtures
    if kwargs.get('raw'):
        return
    # exit early if instance is new
    # issue #67: also exit on empty pk (cloning does not reset state)
    if instance._state.adding or not instance.pk:
        return
    contributing_fks = active_resolver._fk_map.get(sender)
    # exit early if model contains no contributing fk fields
    if not contributing_fks:
        return
    candidates = set(contributing_fks)
    if kwargs.get('update_fields'):
        candidates &= set(cast(Iterable[str], kwargs.get('update_fields')))
    # exit early if no contributing fk field will be updated
    if not candidates:
        return
    # we got an update instance with possibly dirty fk fields
    # we do simply a full update on all old related fk records for now
    # FIXME: this might turn out as a major update bottleneck, if so
    #        filter by individual field changes instead? (tests are ~10% slower)
    data = active_resolver.preupdate_dependent(instance, sender)
    if data:
        UPDATE_OLD[instance] = data
    return


def postsave_handler(sender: Type[Model], instance: Model, **kwargs) -> None:
    """
    ``post_save`` handler.

    Directly updates dependent objects.
    Skipped during fixtures.
    """
    # do not update for fixtures
    if not kwargs.get('raw'):
        active_resolver.update_dependent(
            instance, sender, kwargs.get('update_fields'),
            old=UPDATE_OLD.pop(instance, None),
            update_local=False,
            querysize=settings.COMPUTEDFIELDS_QUERYSIZE
        )


def predelete_handler(sender: Type[Model], instance: Model, **_) -> None:
    """
    ``pre_delete`` handler.

    Gets all dependent objects as pk lists and saves
    them in thread local storage.
    """
    # get the querysets as pk lists to hold them in storage
    # we have to get pks here since the queryset will be empty after deletion
    data = active_resolver._querysets_for_update(sender, instance, pk_list=True)
    if data:
        DELETES[instance] = data


def postdelete_handler(sender: Type[Model], instance: Model, **kwargs) -> None:
    """
    ``post_delete`` handler.

    Loads the dependent objects from the previously saved pk lists
    and updates them.
    """
    # after deletion we can update the associated computed fields
    updates = DELETES.pop(instance, None)
    if updates:
        with transaction.atomic():
            for model, [pks, fields] in updates.items():
                active_resolver.bulk_updater(
                    model._base_manager.filter(pk__in=pks),
                    fields,
                    querysize=settings.COMPUTEDFIELDS_QUERYSIZE
                )


def merge_pk_maps(
    obj1: Dict[Type[Model], List[Any]],
    obj2: Dict[Type[Model], List[Any]]
) -> Dict[Type[Model], List[Any]]:
    """
    Merge pk map in `obj2` on `obj1`.
    Updates obj1 inplace and also returns it.
    """
    for model, data in obj2.items():
        m2_pks, m2_fields = data
        m1_pks, m1_fields = obj1.setdefault(model, [set(), set()])
        m1_pks.update(m2_pks)
        m1_fields.update(m2_fields)
    return obj1


def merge_qs_maps(
    obj1: Dict[Type[Model], List[Any]],
    obj2: Dict[Type[Model], List[Any]]
) -> Dict[Type[Model], List[Any]]:
    """
    Merge queryset map in `obj2` on `obj1`.
    Updates obj1 inplace and also returns it.
    """
    for model, [qs2, fields2] in obj2.items():
        query_field = obj1.setdefault(model, [model._base_manager.none(), set()])
        query_field[0] = query_field[0].union(qs2)  # or'ed querysets
        query_field[1].update(fields2)              # add fields
    return obj1

# M2M tests: test_full.tests.test05_m2m test_full.tests.test06_m2mback test_full.tests.test_43.TestBetterM2M test_full.tests.test_m2m_advanced test_full.tests.test_norelated.TestNoReverse test_full.tests.test_proxymodels.TestProxyModelsM2M
def m2m_handler(sender: Type[Model], instance: Model, **kwargs) -> None:
    """
    ``m2m_change`` handler.

    Works like the other handlers but on the corresponding
    m2m actions.

    .. NOTE::
        The handler triggers updates for both ends of the m2m relation,
        which might lead to massive database interaction.
    """
    fields = active_resolver._m2m.get(sender)
    # exit early if we have no update rule on the through model
    if not fields:
        return

    # since the graph does not handle the m2m through model
    # we have to trigger updates for both ends (left and right side)
    reverse = kwargs['reverse']
    left = fields['right'] if reverse else fields['left']   # fieldname on instance
    right = fields['left'] if reverse else fields['right']  # fieldname on model
    action = kwargs.get('action')
    model = kwargs['model']

    if action == 'post_add':
        pks_add: Set[Any] = kwargs['pk_set']
        data_add: Dict[Type[Model], List[Any]] = active_resolver._querysets_for_update(
            type(instance), instance, update_fields={left})
        other_add: Dict[Type[Model], List[Any]] = active_resolver._querysets_for_update(
            model, model._base_manager.filter(pk__in=pks_add), update_fields={right}, m2m=instance)
        if other_add:
            merge_qs_maps(data_add, other_add)
        if data_add:
            with transaction.atomic():
                for queryset, update_fields in data_add.values():
                    active_resolver.bulk_updater(
                        queryset,
                        update_fields,
                        querysize=settings.COMPUTEDFIELDS_QUERYSIZE
                    )

    elif action == 'pre_remove':
        pks_remove: Set[Any] = kwargs['pk_set']
        data_remove: Dict[Type[Model], List[Any]] = active_resolver._querysets_for_update(
            type(instance), instance, update_fields={left}, pk_list=True)
        other_remove: Dict[Type[Model], List[Any]] = active_resolver._querysets_for_update(
            model, model._base_manager.filter(pk__in=pks_remove), update_fields={right}, pk_list=True, m2m=instance)
        if other_remove:
            merge_pk_maps(data_remove, other_remove)
        if data_remove:
            M2M_REMOVE[instance] = data_remove

    elif action == 'post_remove':
        updates_remove: Dict[Type[Model], List[Any]] = M2M_REMOVE.pop(instance, None)
        if updates_remove:
            with transaction.atomic():
                for _model, [pks, update_fields] in updates_remove.items():
                    active_resolver.bulk_updater(
                        _model._base_manager.filter(pk__in=pks),
                        update_fields,
                        querysize=settings.COMPUTEDFIELDS_QUERYSIZE
                    )

    elif action == 'pre_clear':
        data: Dict[Type[Model], List[Any]] = active_resolver._querysets_for_update(
            type(instance), instance, update_fields={left}, pk_list=True)
        other: Dict[Type[Model], List[Any]] = active_resolver._querysets_for_update(
            model, getattr(instance, left).all(), update_fields={right}, pk_list=True, m2m=instance)
        if other:
            merge_pk_maps(data, other)
        if data:
            M2M_CLEAR[instance] = data

    elif action == 'post_clear':
        updates_clear: Dict[Type[Model], List[Any]] = M2M_CLEAR.pop(instance, None)
        if updates_clear:
            with transaction.atomic():
                for _model, [pks, update_fields] in updates_clear.items():
                    active_resolver.bulk_updater(
                        _model._base_manager.filter(pk__in=pks),
                        update_fields,
                        querysize=settings.COMPUTEDFIELDS_QUERYSIZE
                    )
