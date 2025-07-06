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

def get_DELETES():
    try:
        return STORAGE.DELETES
    except AttributeError:
        STORAGE.DELETES = {}
    return STORAGE.DELETES

def get_M2M_REMOVE():
    try:
        return STORAGE.M2M_REMOVE
    except AttributeError:
        STORAGE.M2M_REMOVE = {}
    return STORAGE.M2M_REMOVE

def get_M2M_CLEAR():
    try:
        return STORAGE.M2M_CLEAR
    except AttributeError:
        STORAGE.M2M_CLEAR = {}
    return STORAGE.M2M_CLEAR

def get_UPDATE_OLD():
    try:
        return STORAGE.UPDATE_OLD
    except AttributeError:
        STORAGE.UPDATE_OLD = {}
    return STORAGE.UPDATE_OLD


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
        get_UPDATE_OLD()[instance] = data
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
            old=get_UPDATE_OLD().pop(instance, None),
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
        get_DELETES()[instance] = data


def postdelete_handler(sender: Type[Model], instance: Model, **kwargs) -> None:
    """
    ``post_delete`` handler.

    Loads the dependent objects from the previously saved pk lists
    and updates them.
    """
    # after deletion we can update the associated computed fields
    updates = get_DELETES().pop(instance, None)
    if updates:
        with transaction.atomic():
            for model, [pks, fields] in updates.items():
                active_resolver.bulk_updater(
                    model._base_manager.filter(pk__in=pks),
                    fields,
                    querysize=settings.COMPUTEDFIELDS_QUERYSIZE
                )


# M2M tests: test_full.tests.test05_m2m test_full.tests.test06_m2mback test_full.tests.test_43.TestBetterM2M test_full.tests.test_m2m_advanced test_full.tests.test_norelated.TestNoReverse test_full.tests.test_proxymodels.TestProxyModelsM2M
def m2m_handler(sender: Type[Model], instance: Model, **kwargs) -> None:
    """
    ``m2m_change`` handler.

    Works like the other handlers but on the corresponding
    m2m actions.
    """
    fields = active_resolver._m2m.get(sender)
    # exit early if we have no update rule on the through model
    if not fields:
        return

    reverse = kwargs['reverse']
    left = fields['right'] if reverse else fields['left']   # fieldname on instance
    right = fields['left'] if reverse else fields['right']  # fieldname on model
    action = kwargs.get('action')

    if action == 'post_add':
        active_resolver.update_dependent(
            sender.objects.filter(**{left: instance.pk, right+'__in': kwargs['pk_set']})
        )

    elif action == 'pre_remove':
        get_M2M_REMOVE()[instance] = active_resolver.preupdate_dependent(
            sender.objects.filter(**{left: instance.pk, right+'__in': kwargs['pk_set']})
        )

    elif action == 'post_remove':
        old = get_M2M_REMOVE().pop(instance, None)
        if old:
            active_resolver.update_dependent(
                sender.objects.none(),
                old=old
            )

    elif action == 'pre_clear':
        get_M2M_CLEAR()[instance] = active_resolver.preupdate_dependent(
            sender.objects.filter(**{left: instance.pk})
        )

    elif action == 'post_clear':
        old = get_M2M_CLEAR().pop(instance, None)
        if old:
            active_resolver.update_dependent(
                sender.objects.none(),
                old=old
            )
