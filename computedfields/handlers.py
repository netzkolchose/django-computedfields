"""
Module containing the database signal handlers.

The handlers are registered during application startup
in ``apps.ready``.

.. NOTE::

    The handlers are not registered in the managment
    commands ``makemigrations``, ``migrate`` and ``help``.
"""
from computedfields.models import ComputedFieldsModelType as CFMT
from threading import local
from django.db.models.fields.reverse_related import ManyToManyRel
from collections import OrderedDict
import django
Django2 = False
if django.VERSION[0] >= 2:
    Django2 = True


# thread local storage to hold
# the pk lists for deletes
STORAGE = local()
STORAGE.DELETES = {}
STORAGE.M2M_REMOVE = {}
STORAGE.M2M_CLEAR = {}

DELETES = STORAGE.DELETES
M2M_REMOVE = STORAGE.M2M_REMOVE
M2M_CLEAR = STORAGE.M2M_CLEAR


def postsave_handler(sender, instance, **kwargs):
    """
    ``post_save`` handler.

    Directly updates dependent objects.
    Does nothing during fixtures.
    """
    # do not update for fixtures
    if not kwargs.get('raw'):
        CFMT.update_dependent(
            instance, sender, kwargs.get('update_fields'))


def predelete_handler(sender, instance, **kwargs):
    """
    ``pre_delete`` handler.

    Gets all dependent objects as pk lists and saves
    them in thread local storage.
    """
    # get the querysets as pk lists to hold them in storage
    # we have to get pks here since the queryset will be empty after deletion
    data = CFMT._querysets_for_update(sender, instance, pk_list=True)
    if data:
        DELETES[instance] = data


def postdelete_handler(sender, instance, **kwargs):
    """
    ``post_delete`` handler.

    Loads the dependent objects from the previously saved pk lists
    and updates them.
    """
    # after deletion we can update the associated computed fields
    updates = DELETES.pop(instance, {})
    for model, data in updates.items():
        pks, fields = data
        qs = model.objects.filter(pk__in=pks)
        for el in qs.distinct():
            el.save(update_fields=fields)


def m2m_handler(sender, instance, **kwargs):
    """
    ``m2m_change`` handler.

    Works like the other handlers but on the corresponding
    m2m actions.

    .. NOTE::
        The handler triggers updates for both ends of the m2m
        relation, which might lead to massive updates and thus
        heavy time consuming database interaction.
    """
    # since the graph does not handle the m2m through model
    # we have to trigger updates for both ends:
    #   - instance:   CFMT.update_dependent(instance, type(instance))
    #   - other side: CFMT.update_dependent(model.objects.filter(pk__in=pks), model)
    action = kwargs.get('action')
    model = kwargs['model']

    if action == 'post_add':
        pks = kwargs['pk_set']
        CFMT.update_dependent(instance, type(instance))
        CFMT.update_dependent(model.objects.filter(pk__in=pks), model)

    elif action == 'pre_remove':
        data = OrderedDict()

        # instance updates
        to_add = CFMT._querysets_for_update(
            type(instance), instance, pk_list=True)
        if to_add:
            data.update(to_add)

        # other side updates
        pks = kwargs['pk_set']
        to_add = CFMT._querysets_for_update(
            model, model.objects.filter(pk__in=pks), pk_list=True)
        if to_add:
            data.update(to_add)

        # final
        if data:
            M2M_REMOVE[instance] = data

    elif action == 'post_remove':
        updates = M2M_REMOVE.pop(instance, {})
        for model, data in updates.items():
            pks, fields = data
            qs = model.objects.filter(pk__in=pks)
            for el in qs.distinct():
                el.save(update_fields=fields)

    elif action == 'pre_clear':
        data = OrderedDict()

        # instance updates
        to_add = CFMT._querysets_for_update(type(instance), instance, pk_list=True)
        if to_add:
            data.update(to_add)

        # other side updates
        # geez - have to get pks of other side ourself
        inst_model = type(instance)
        if kwargs['reverse']:
            rel = list(filter(lambda f: isinstance(f, ManyToManyRel) and f.through == sender,
                         inst_model._meta.get_fields()))[0]
            to_add = CFMT._querysets_for_update(
                model, getattr(instance, rel.name).all(), pk_list=True)
        else:
            if Django2:
                field = list(filter(
                    lambda f: isinstance(f, ManyToManyRel) and f.through == sender,
                        model._meta.get_fields()))[0]
                to_add = CFMT._querysets_for_update(
                    model, getattr(instance, field.remote_field.name).all(), pk_list=True)
            else:
                field = list(filter(
                    lambda f: f.rel.through == sender, inst_model._meta.many_to_many))[0]
                to_add = CFMT._querysets_for_update(
                    model, getattr(instance, field.name).all(), pk_list=True)
        if to_add:
            data.update(to_add)

        # final
        if data:
            M2M_CLEAR[instance] = data

    elif action == 'post_clear':
        updates = M2M_CLEAR.pop(instance, {})
        for model, data in updates.items():
            pks, fields = data
            qs = model.objects.filter(pk__in=pks)
            for el in qs.distinct():
                el.save(update_fields=fields)
