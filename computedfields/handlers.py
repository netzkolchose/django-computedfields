from computedfields.models import ComputedFieldsModelType as CFMT
from threading import local

STORAGE = local()
STORAGE.DELETES = {}
STORAGE.M2M_REMOVE = {}
STORAGE.M2M_CLEAR = {}

DELETES = STORAGE.DELETES
M2M_REMOVE = STORAGE.M2M_REMOVE
M2M_CLEAR = STORAGE.M2M_CLEAR


def postsave_handler(sender, instance, **kwargs):
    # do not update for fixtures
    if not kwargs.get('raw'):
        CFMT.update_dependent(instance, sender, kwargs.get('update_fields'))


def predelete_handler(sender, instance, **kwargs):
    # get the querysets as pk lists to hold them in storage
    data = CFMT._querysets_for_update(sender, instance, pk_list=True)
    if data:
        DELETES[instance] = data


def postdelete_handler(sender, instance, **kwargs):
    # after deletion we can update the associated computed fields
    updates = DELETES.pop(instance, {})
    for model, data in updates.items():
        pks, fields = data
        qs = model.objects.filter(pk__in=pks)
        for el in qs.distinct():
            el.save(update_fields=fields)


def m2m_handler(sender, instance, **kwargs):
    action = kwargs.get('action')
    model = kwargs['model']
    if action == 'post_add':
        pks = kwargs['pk_set']
        CFMT.update_dependent(model.objects.filter(pk__in=pks), model)
    elif action == 'pre_remove':
        # although going over the pk_set selects to many objects to be updated
        # this is faster than going over instance here
        pks = frozenset(kwargs['pk_set'])
        data = CFMT._querysets_for_update(model, model.objects.filter(pk__in=pks), pk_list=True)
        if data:
            M2M_REMOVE[frozenset([model, pks])] = data
    elif action == 'post_remove':
        pks = frozenset(kwargs['pk_set'])
        updates = M2M_REMOVE.pop(frozenset([model, pks]), {})
        for model, data in updates.items():
            pks, fields = data
            qs = model.objects.filter(pk__in=pks)
            for el in qs.distinct():
                el.save(update_fields=fields)
    elif action == 'pre_clear':
        # geez have to get pks ourself
        inst_model = type(instance)
        field = filter(lambda f: f.rel.through==sender, inst_model._meta.many_to_many)[0]
        data = CFMT._querysets_for_update(model, getattr(instance, field.name).all(), pk_list=True)
        if data:
            M2M_CLEAR[instance] = data
    elif action == 'post_clear':
        updates = M2M_CLEAR.pop(instance, {})
        for model, data in updates.items():
            pks, fields = data
            qs = model.objects.filter(pk__in=pks)
            for el in qs.distinct():
                el.save(update_fields=fields)
