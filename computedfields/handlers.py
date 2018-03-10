from computedfields.models import ComputedFieldsModelType

# FIXME: make this thread local
DELETES = {}


def postsave_handler(sender, instance, **kwargs):
    if not kwargs.get('raw'):
        ComputedFieldsModelType.update_dependent(instance, sender, kwargs.get('update_fields'))


def predelete_handler(sender, instance, **kwargs):
    querysets = ComputedFieldsModelType._querysets_for_update(sender, instance, pk_list=True)
    if querysets:
        DELETES[instance] = querysets


def postdelete_handler(sender, instance, **kwargs):
    updates = DELETES.pop(instance, None)
    if updates:
        for model, data in updates.items():
            pks, fields = data
            qs = model.objects.filter(pk__in=pks)
            for el in qs.distinct():
                el.save(update_fields=fields)


def m2m_handler(sender, instance, **kwargs):
    if kwargs.get('action') == 'post_add':
        ComputedFieldsModelType.update_dependent(
            kwargs['model'].objects.filter(pk__in=kwargs['pk_set']), kwargs['model'])


