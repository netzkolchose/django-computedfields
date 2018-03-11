# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.db.models.base import ModelBase
from django.db import models, transaction
from collections import OrderedDict
from computedfields.graph import ComputedModelsGraph
from django.conf import settings
from django.utils.encoding import python_2_unicode_compatible
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _
from threading import RLock


class ComputedFieldsModelType(ModelBase):
    """
    Metaclass for computed field models.

    Handles the creation of the db fields. Also holds the needed data for
    graph calculations and dependency resolving.

    After startup the method ``_resolve_dependencies`` gets called by
    ``app.ready`` to build the dependency resolver functions.
    To avoid the expensive calculations in production mode the resolver
    functions can be pickled into a map file by setting
    ``COMPUTEDFIELDS_MAP`` in settings.py to a writable file path
    and calling the management command ``createmap``.

    .. NOTE::

        The map file will not be updated automatically and therefore
        must be recreated by calling the management command
        ``createmap`` after code changes.
    """
    _graph = None
    _computed_models = OrderedDict()
    _map = {}
    _map_loaded = False
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
        """
        This method triggers all the ugly stuff.
        Without providing a map file the calculations are done
        once per process by ``app.ready``. The steps are:
            - create a graph of the dependencies
            - cycling check
            - remove redundant paths
            - create final resolver lookup map

        Since these steps are very expensive, you should consider
        using a map file for production mode. This method will
        transparently load the map file omitting the graph and map
        creation upon every process creation.

        NOTE: The test cases rely on runtime overrides of the
        computed model fields dependencies and therefore override the
        "once per process" rule with ``_force``. Dont use this
        for your regular model development. If you really need to
        force the recreation of the graph and map, use ``force`` instead.
        Never do this at runtime in a multithreaded environment or hell
        will break loose. You have been warned ;)
        """
        with mcs._lock:
            if mcs._map_loaded and not _force:
                return
            from_map = hasattr(settings, 'COMPUTEDFIELDS_MAP') and not force and not _force
            if from_map:
                try:
                    from importlib import import_module
                    module = import_module(settings.COMPUTEDFIELDS_MAP)
                    mcs._map = module.map
                    mcs._map_loaded = True
                    return
                except (ImportError, AttributeError, Exception):
                    raise
            mcs._graph = ComputedModelsGraph(mcs._computed_models)
            # automatically checks for cycles
            mcs._graph.remove_redundant_paths()
            mcs._map = ComputedFieldsModelType._graph.generate_lookup_map()
            mcs._map_loaded = True

    @classmethod
    def _get_dependent_queryset(mcs, instance, paths_resolved, model):
        """
        Returns a queryset containing all dependent objects of type ``model``
        for ``instance``.
        ``paths_resolved`` is a list of precalculated resolver functions.
        """
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

    @classmethod
    def _querysets_for_update(mcs, model, instance, update_fields=None, pk_list=False):
        """
        Returns a mapping of all dependent models, dependent fields and a
        queryset containing all dependent objects.
        """
        final = OrderedDict()
        modeldata = mcs._map.get(model)
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
                    qs |= mcs._get_dependent_queryset(instance, paths_resolved, model)
                    fields.add(field)
                if pk_list:
                    # need pks for post_delete since the real queryset will be empty
                    # after deleting the instance in question
                    # since we need to interact with the db anyways
                    # we can already drop empty results here
                    qs = list(qs.distinct().values_list('pk', flat=True))
                    if not qs:
                        continue
                final[model] = [qs, fields]
        return final

    @classmethod
    def update_dependent(mcs, instance, model=None, update_fields=None):
        """
        Updates all dependent computed fields model objects.

        This is needed if you have computed fields that depend on the model
        you would like to update with ``QuerySet.update``. Simply call this
        function after the update with the queryset containing the changed
        objects. The queryset may not be finalized by ``distinct`` or
        any other means.

            >>> Entry.objects.filter(pub_date__year=2010).update(comments_on=False)
            >>> update_dependent(Entry.objects.filter(pub_date__year=2010))

        This can also be used with ``bulk_create``. Since ``bulk_create``
        returns the objects in a python container, you have to create the queryset
        yourself, e.g. with pks:

            >>> objs = Entry.objects.bulk_create([
            ...     Entry(headline='This is a test'),
            ...     Entry(headline='This is only a test'),
            ... ])
            >>> pks = set((obj.pk for obj in objs))
            >>> update_dependent(Entry.objects.filter(pk__in=pks))

        .. NOTE::

            This function cannot be used to update computed fields on a
            computed fields model itself. For computed fields models always
            use ``save`` on the model objects. You still can use
            ``update`` or ``bulk_create`` but have to call
            ``save`` afterwards:

                >>> objs = SomeComputedFieldsModel.objects.bulk_create([
                ...     SomeComputedFieldsModel(headline='This is a test'),
                ...     SomeComputedFieldsModel(headline='This is only a test'),
                ... ])
                >>> for obj in objs:
                ...     obj.save()

            (This behavior might change with future versions.)

        For completeness - ``instance`` can also be a single model instance.
        Since calling ``save`` on a model instance will trigger this function by
        the ``post_save`` signal it should not be invoked for single model
        instances if they get saved explicitly.
        """
        if not model:
            if isinstance(instance, models.QuerySet):
                model = instance.model
            else:
                model = type(instance)
        updates = mcs._querysets_for_update(model, instance, update_fields).values()
        if not updates:
            return
        with transaction.atomic():
            for qs, fields in updates:
                for el in qs.distinct():
                    el.save(update_fields=fields)


update_dependent = ComputedFieldsModelType.update_dependent


class ComputedFieldsModel(models.Model):
    """
    Base class for a computed fields model.

    To use computed fields derive your model from this class
    and use the ``@computed`` decorator:

    .. code-block:: python

        from django.db import models
        from computedfields.models import ComputedFieldsModel, computed

        class Person(ComputedFieldsModel):
            forename = models.CharField(max_length=32)
            surname = models.CharField(max_length=32)

            @computed(models.CharField(max_length=32))
            def combined(self):
                return u'%s, %s' % (self.surname, self.forename)

    ``combined`` will be turned into a real database field and can be accessed
    and searched like any other field. During saving the value gets calculated and
    written to the database. With the method ``compute('fieldname')`` you can
    inspect the value that will be written, which is useful if you have pending
    changes:

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
        Returns the computed field value for ``fieldname``.
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
    Decorator to create computed fields.

    ``field`` should be a model field suitable to hold the result
    of the decorated method. The decorator understands an optional
    keyword argument ``depends`` to indicate dependencies to
    related model fields. Listed dependencies will be updated
    automatically.

    Examples:

        - create a char field with no outer dependencies

          .. code-block:: python

            @computed(models.CharField(max_length=32))
            def ...

        - create a char field with one dependency to the field
          ``name`` of a foreign key relation ``fk``

          .. code-block:: python

            @computed(models.CharField(max_length=32), depends=['fk#name'])
            def ...

    The format of the dependency strings is in the form
    ``'rel_a.rel_b#fieldname'`` where the computed field gets
    a value from a field ``fieldname``, which is accessible through
    the relations ``rel_a`` --> ``rel_b``.
    A relation can be any of the relation types foreign keys, m2m and their
    corresponding back relations. One2one is not yet implemented.

    The fieldname at the end separated by '#' is mandatory for the
    dependency resolver to decide, whether the updates depend on other
    computed fields. For multiple dependencies to ordinary fields
    of the same model you have to list only one fieldname:

    .. code-block:: python

        @computed(models.CharField(max_length=32), depends=['fk#name'])
        def some_field(self):
            return self.fk.name + self.fk.field_xy

    Here ``name`` and ``field_xy`` are ordinary fields. Listing one of them
    in ``depends`` is sufficient to get the computed field properly updated.

    On the contrary dependencies to other computed fields must always
    be listed separately to make sure your computed field gets properly updated:

    .. code-block:: python

        @computed(models.CharField(max_length=32), depends=['fk#computed1', 'fk#computed2'])
        def some_field(self):
            return self.fk.computed1 + self.fk.computed2

    .. CAUTION::

        With the auto resolving of the dependencies you can easily create
        recursive dependencies by accident. Imagine the following:

        .. code-block:: python

            class A(ComputedFieldsModel):
                @computed(models.CharField(max_length=32), depends=['b_set#comp'])
                def comp(self):
                    return ''.join(b.comp for b in self.b_set.all())

            class B(ComputedFieldsModel):
                a = models.ForeignKey(A)

                @computed(models.CharField(max_length=32), depends=['a#comp'])
                def comp(self):
                    return a.comp

        Neither an object of ``A`` or ``B`` can be saved, since the
        ``comp`` fields depend on each other. While this is quite easy
        to spot for this simple case it might get tricky for more
        complicated dependencies. Therefore the dependency resolver tries
        to detect cyclic dependencies and raises a ``CycleNodeException``
        if a cycle was found.

        If you experience this in your project try to get in-depth cycle
        information, either by using the ``rendergraph`` management command or
        by accessing the graph object directly under ``your_model._graph``.
        Also see the graph :ref:`documentation<graph>`.
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
    """
    Proxy model to list all computed fields models with their
    field dependencies in admin. This might be useful during development.
    To enable it, set ``COMPUTEDFIELDS_ADMIN`` in settings.py to ``True``.
    """
    objects = ComputedModelManager()

    class Meta:
        proxy = True
        managed = False
        verbose_name = _('Computed Fields Model')
        verbose_name_plural = _('Computed Fields Models')
        ordering = ('app_label', 'model')

    def __str__(self):
        return self.model
