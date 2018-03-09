# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.db.models.base import ModelBase
from django.db import models
from django.db.models.signals import post_save, m2m_changed, pre_delete, post_delete
from collections import OrderedDict
from computedfields.graph import ComputedModelsGraph
from django.conf import settings
from django.utils.encoding import python_2_unicode_compatible
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _
from threading import RLock, local


def get_dependent_queryset(instance, paths_resolved, model):
    for func in paths_resolved:
        instance = func(instance)
        # early exit for empty relation objects
        # test for QuerySet type beforehand to avoid triggering db interaction
        if not isinstance(instance, models.QuerySet) and not instance:
            return model.objects.none()
    # turn single model instance into a queryset
    if not isinstance(instance, models.QuerySet):
        return model.objects.filter(pk=instance.pk)
    # we got a pk list queryset from values_list
    if not instance.model == model:
        return model.objects.filter(pk__in=instance)
    return instance


def save_qs(qs, fields):
    for el in qs.distinct():
        el.save(update_fields=fields)


def get_querysets_for_update(model, instance, update_fields=None, pk_list=False):
    final = OrderedDict()
    modeldata = ComputedFieldsModelType._map.get(model)
    if not modeldata:
        return final
    if not update_fields:
        updates = set(modeldata.keys())
    else:
        updates = set()
        for fieldname in update_fields:
            if fieldname in modeldata:
                updates.add(fieldname)
    for update in updates:
        for model, resolvers in modeldata[update].items():
            qs = model.objects.none()
            fields = set()
            for field, paths_resolved in resolvers:
                # join all queryets to a final one with all update fields
                qs |= get_dependent_queryset(instance, paths_resolved, model)
                fields.add(field)
            if pk_list:
                # need pks for post_delete since the real queryset will be empty
                # after deleting the instance in question
                # since we need to interact with the db anyways
                # we can already drop empty results here
                qs = list(qs.values_list('pk', flat=True))
                if not qs:
                    continue
            final[model] = [qs, fields]
    return final


def update_dependent(instance, model=None, update_fields=None):
    """
    Function to update all dependent computed fields model objects.
    This is needed if you have computed fields that depend on the model
    you would like to update with `QuerySet.update`. Simply call this
    function after the update with the same queryset (The queryset
    may not be finalized by `distinct` or any other means.).

    For completeness `instance` can also be a single model instance.
    Since calling `save` on a model instance will trigger this function by
    the post_save signal it is not needed for single instances.

    Example:
        >>> Entry.objects.filter(pub_date__year=2010).update(comments_on=False)
        >>> update_dependent(Entry.objects.filter(pub_date__year=2010))
    """
    if not model:
        if isinstance(instance, models.QuerySet):
            model = instance.model
        else:
            model = type(instance)
    for data in get_querysets_for_update(model, instance, update_fields).values():
        save_qs(*data)


def postsave_handler(sender, instance, **kwargs):
    if kwargs.get('raw'):
        return
    update_dependent(instance, sender, kwargs.get('update_fields'))


post_save.connect(postsave_handler, sender=None, weak=False, dispatch_uid='COMP_FIELD')


# FIXME: make this thread local
DELETES = {}


def predelete_handler(sender, instance, **kwargs):
    querysets = get_querysets_for_update(sender, instance, pk_list=True)
    if querysets:
        DELETES[instance] = querysets


pre_delete.connect(predelete_handler, sender=None, weak=False, dispatch_uid='COMP_FIELD_PREDELETE')


def postdelete_handler(sender, instance, **kwargs):
    updates = DELETES.pop(instance, None)
    if updates:
        for model, data in updates.items():
            pks, fields = data
            qs = model.objects.filter(pk__in=pks)
            save_qs(qs, fields)


post_delete.connect(postdelete_handler, sender=None, weak=False, dispatch_uid='COMP_FIELD_POSTDELETE')


def m2m_handler(sender, instance, **kwargs):
    # FIXME: dirty hack spot changes on m2m realtions
    if kwargs.get('action') == 'post_add':
        model = kwargs['model']
        pk = next(iter(kwargs['pk_set']))
        inst = model.objects.get(pk=pk)
        post_save.send(sender=model, instance=inst, created=False, update_fields=None,
                       raw=False, using=kwargs.get('using'))


m2m_changed.connect(m2m_handler, sender=None, weak=False, dispatch_uid='COMP_FIELD_M2M')


class ComputedFieldsModelType(ModelBase):
    _graph = None
    _computed_models = OrderedDict()
    _map = {}
    _lock = RLock()

    def __new__(mcs, name, bases, attrs):
        computed_fields = {}
        dependent_fields = {}
        if name != 'ComputedFieldsModel':
            for k, v in attrs.items():
                if getattr(v, '_computed', None):
                    computed_fields.update({k: v})
                    v.editable = False
                    v._computed.update({'attr': k})
                    depends = v._computed['kwargs'].get('depends')
                    if depends:
                        dependent_fields[k] = depends
        cls = super(ComputedFieldsModelType, mcs).__new__(mcs, name, bases, attrs)
        if name != 'ComputedFieldsModel':
            cls._computed_fields = computed_fields
            mcs._computed_models[cls] = dependent_fields or {}
        return cls

    @classmethod
    def _resolve_dependencies(mcs, force=False, _force=False):
        with mcs._lock:
            if mcs._map and not _force:
                return
            map = None
            if hasattr(settings, 'COMPUTEDFIELDS_MAP'):
                try:
                    from importlib import import_module
                    module = import_module(settings.COMPUTEDFIELDS_MAP)
                    map = module.map
                except (ImportError, AttributeError, Exception):
                    pass
            if map and not force and not settings.DEBUG:
                mcs._map = map
            else:
                mcs._graph = ComputedModelsGraph(mcs._computed_models)
                # automatically checks for cycles
                mcs._graph.remove_redundant_paths()
                mcs._map = ComputedFieldsModelType._graph.generate_lookup_map()


class ComputedFieldsModel(models.Model):
    __metaclass__ = ComputedFieldsModelType

    class Meta:
        abstract = True

    def compute(self, fieldname):
        field = self._computed_fields[fieldname]
        return field._computed['func'](self)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if update_fields:
            update_fields = set(update_fields)
            all_computed = not (update_fields - set(self._computed_fields.keys()))
            if all_computed:
                has_changed = False
                for fieldname in update_fields:
                    result = self.compute(fieldname)
                    field = self._computed_fields[fieldname]
                    if result != getattr(self, field._computed['attr']):
                        has_changed = True
                        setattr(self, field._computed['attr'], result)
                if not has_changed:
                    # we are actually not saving, but must fire
                    # post_save to trigger all dependent updates
                    # FIXME: use own signal here to circumvent side effects
                    post_save.send(
                        sender=self.__class__, instance=self, created=False,
                        update_fields=kwargs.get('update_fields'),
                        raw=kwargs.get('raw'), using=kwargs.get('using'))
                    return
                super(ComputedFieldsModel, self).save(*args, **kwargs)
                return
        for fieldname in self._computed_fields:
            result = self.compute(fieldname)
            field = self._computed_fields[fieldname]
            setattr(self, field._computed['attr'], result)
        super(ComputedFieldsModel, self).save(*args, **kwargs)


def computed(field, **kwargs):
    def wrap(f):
        field._computed = {'func': f, 'kwargs': kwargs}
        return field
    return wrap


class ComputedModelManager(models.Manager):
    def get_queryset(self):
        objs = ContentType.objects.get_for_models(
            *ComputedFieldsModelType._computed_models.keys()).values()
        pks = [model.pk for model in objs]
        return ContentType.objects.filter(pk__in=pks)


@python_2_unicode_compatible
class ComputedFieldsAdminModel(ContentType):
    objects = ComputedModelManager()

    class Meta:
        proxy = True
        managed = False
        verbose_name = _('Computed Fields Model')
        verbose_name_plural = _('Computed Fields Models')
        ordering = ('app_label', 'model')

    def __str__(self):
        return self.model
