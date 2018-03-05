# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.db.models.base import ModelBase
from django.db import models
from django.db.models.signals import post_save
from collections import OrderedDict
from computedfields.graph import ComputedModelsGraph
from django.conf import settings
from django.utils.encoding import python_2_unicode_compatible
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _


def postsave_handler(sender, instance, **kwargs):
    if kwargs.get('raw'):
        return
    if sender not in ComputedFieldsModelType._map:
        return
    mapping = ComputedFieldsModelType._map
    modeldata = mapping[sender]
    if not modeldata:
        return
    update_fields = kwargs.get('update_fields')
    if not update_fields:
        if '#' not in modeldata:
            updates = set(fieldname for fieldname in modeldata)
        else:
            updates = {'#'}
    else:
        updates = set()
        for fieldname in update_fields:
            if fieldname in modeldata:
                updates.add(fieldname)
            else:
                updates.add('#')
    for update in updates:
        for model, funcs in modeldata[update].items():
            for func in funcs:
                func(instance)


post_save.connect(postsave_handler, sender=None, weak=False, dispatch_uid='COMP_FIELD')


class ComputedFieldsModelType(ModelBase):
    _graph = None
    _computed_models = OrderedDict()
    _map = {}

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

    @staticmethod
    def _resolve_dependencies(force=False):
        map = None
        if hasattr(settings, 'COMPUTEDFIELDS_MAP'):
            try:
                from importlib import import_module
                module = import_module(settings.COMPUTEDFIELDS_MAP)
                map = module.map
            except (ImportError, AttributeError, Exception):
                pass
        if map and not force and not settings.DEBUG:
            ComputedFieldsModelType._map = map
        else:
            ComputedFieldsModelType._graph = ComputedModelsGraph(
                ComputedFieldsModelType._computed_models)
            ComputedFieldsModelType._graph.remove_redundant_paths()
            ComputedFieldsModelType._map = ComputedFieldsModelType._graph.generate_lookup_map()


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
                    # TODO: define own signal to circumvent side effects?
                    post_save.send(sender=self.__class__, instance=self, created=False,
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
        verbose_name = _('Computed Fields Model')
        verbose_name_plural = _('Computed Fields Models')
        proxy = True
        managed = False
        ordering = ('app_label', 'model')

    def __str__(self):
        return self.model
