# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.db.models.base import ModelBase
from django.db import models
from django.db.models.signals import post_save
from collections import OrderedDict
from computedfields.graph import ComputedModelsGraph


def my_callback(sender, instance, **kwargs):
    #TODO
    pass


post_save.connect(my_callback, sender=None, weak=False, dispatch_uid='COMP_FIELD')


class ComputedFieldsModelType(ModelBase):
    _graph = None
    _computed_models = OrderedDict()

    def __new__(mcs, name, bases, attrs):
        computed_fields = {}
        dependent_fields = {}
        for k, v in attrs.iteritems():
            if getattr(v, '_computed', None):
                computed_fields.update({k: v})
                v.editable = False
                v._computed.update({'attr': k})
                depends = v._computed['kwargs'].get('depends')
                if depends:
                    dependent_fields[k] = depends
        cls = super(ComputedFieldsModelType, mcs).__new__(mcs, name, bases, attrs)
        cls._computed_fields = computed_fields
        if dependent_fields:
            mcs._computed_models[cls] = dependent_fields
        return cls

    @staticmethod
    def _resolve_dependencies():
        ComputedFieldsModelType._graph = ComputedModelsGraph(
            ComputedFieldsModelType._computed_models)
        ComputedFieldsModelType._graph.remove_redundant_paths()


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
