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
    function after the update with the queryset containing the changed
    objects. The queryset may not be finalized by `distinct` or any other means.

    Example:

        >>> Entry.objects.filter(pub_date__year=2010).update(comments_on=False)
        >>> update_dependent(Entry.objects.filter(pub_date__year=2010))

    This can also be used with `bulk_create`. Since `bulk_create` returns
    the objects in a python container, you have to create the queryset
    yourself, e.g. with the pks:

        >>> objs = Entry.objects.bulk_create([
        ...     Entry(headline='This is a test'),
        ...     Entry(headline='This is only a test'),
        ... ])
        >>> pks = set((obj.pk for obj in objs))
        >>> update_dependent(Entry.objects.filter(pk__in=pks))

    NOTE: This function cannot be used to update computed fields on a
    computed fields model itself (this might change with future versions).
    For computed fields models always use `save` on the model objects.
    You still can use `update` or `bulk_create` but have to call
    `save` afterwards (which defeats the purpose):

        >>> objs = SomeComputedFieldsModel.objects.bulk_create([
        ...     SomeComputedFieldsModel(headline='This is a test'),
        ...     SomeComputedFieldsModel(headline='This is only a test'),
        ... ])
        >>> for obj in objs:
        ...     obj.save()

    For completeness `instance` can also be a single model instance.
    Since calling `save` on a model instance will trigger this function by
    the `post_save` signal it is not needed for single instances.
    """
    if not model:
        if isinstance(instance, models.QuerySet):
            model = instance.model
        else:
            model = type(instance)
    for data in get_querysets_for_update(model, instance, update_fields).values():
        save_qs(*data)


def postsave_handler(sender, instance, **kwargs):

    if not kwargs.get('raw'):
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
    if kwargs.get('action') == 'post_add':
        update_dependent(kwargs['model'].objects.filter(pk__in=kwargs['pk_set']), kwargs['model'])


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
    """
    Base class for a computed fields model.

    To use computed fields derive your model from this
    base class and use the `computed` decorator:

        >>> from django.db import models
        >>> from computedfields.models import ComputedFieldsModel, computed
        >>> class Person(ComputedFieldsModel):
        ...     forename = models.CharField(max_length=32)
        ...     surname = models.CharField(max_length=32)
        ...     @computed(models.CharField(max_length=32))
        ...     def combined(self):
        ...         return u'%s, %s' % (self.surname, self.forename)

    `combined` will be turned into a real database field and can be accessed
    and searched like any other field. Upon `save` the value gets calculated and the
    result is written to the database. With the method `compute(fieldname)`
    you can inspect the value that will be written (useful if you have pending changes):

        >>> person = Person(forename='Leeroy', surname='Jenkins')
        >>> person.combined             # empty since not saved yet
        >>> person.compute('combined')  # outputs 'Jenkins, Leeroy'
        >>> person.save()
        >>> person.combined             # outputs 'Jenkins, Leeroy'
        >>> Person.objects.filter(combined__<some condition>)  # used in a queryset
    """
    __metaclass__ = ComputedFieldsModelType

    class Meta:
        abstract = True

    def compute(self, fieldname):
        """
        Returns the computed field value for `fieldname`.
        :param fieldname:
        :return: computed field value
        """
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
                    # no save needed, we still need to update dependent objects
                    update_dependent(self, type(self), update_fields)
                    return
                super(ComputedFieldsModel, self).save(*args, **kwargs)
                return
        for fieldname in self._computed_fields:
            result = self.compute(fieldname)
            field = self._computed_fields[fieldname]
            setattr(self, field._computed['attr'], result)
        super(ComputedFieldsModel, self).save(*args, **kwargs)


def computed(field, **kwargs):
    """
    Decorator for computed fields.

    `field` should be a model field suitable to hold the result
    of the method. The decorator understands an optional
    keyword argument `depends` to indicate dependencies to
    related model fields. Listed dependencies get updated
    automatically.

    Examples:

        create a char field with no outer dependencies

            >>> computed(models.CharField(max_length=32))

        create a char field with one dependency to the name
        field of a foreign key relation `fk`

            >>> computed(models.CharField(max_length=32), depends=['fk#name'])

    List the dependencies as strings in this fashion:
        ['rel_a.rel_b#fieldname', ...]
    Meaning: The computed field gets a value from a field 'fieldname',
    which is accessible through the relations 'rel_a' --> 'rel_b'.
    The relation can be any relation type (foreign keys, m2m, one2one
    and their corresponding back relations).
    The fieldname at the end separated by '#' is mandatory for the
    dependency resolver to decide, whether the updates depend on other
    computed fields. For multiple dependencies to non computed fields
    of the same model you have to list only one fieldname
    (others are covered automatically):

        >>> computed(models.CharField(max_length=32), depends=['fk#name'])

    '#name' itself is not a computed field. Listing it will ensure,
    that any changes to the object behind 'fk' will update your computed field.

    Dependencies to computed fields must be listed separately
    to make sure your computed field gets properly updated:

        >>> computed(models.CharField(max_length=32), depends=['fk#comp1', 'fk#comp2'])

    Here 'comp1' and 'comp2' are computed fields itself and must be listed both,
    if your computed field depends on those.

    NOTE: With the auto resolving of the dependencies you can easily create
    recursive dependencies by accident. Imagine the following simple case:

        >>> class A(ComputedFieldsModel):
        >>>     @computed(models.CharField(max_length=32), depends=['b_set#comp'])
        >>>     def comp(self):
        >>>         return ''.join(b.comp for b in self.b_set.all())
        >>>
        >>> class B(ComputedFieldsModel):
        >>>     a = models.ForeignKey(A)
        >>>     @computed(models.CharField(max_length=32), depends=['a#comp'])
        >>>     def comp(self):
        >>>         return a.comp

    Neither A nor B can be saved, since the `comp` fields depend on each other.
    While this sounds logically for this simple case it might be hard to spot
    for more complicated dependencies. Thus the dependency resolver tries
    to detect cyclic dependencies and raises a `CycleNodeException`.
    """
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
