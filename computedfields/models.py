from django.db.models.base import ModelBase
from django.db import models, transaction
from collections import OrderedDict
from computedfields.graph import ComputedModelsGraph
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _
from threading import RLock
from django.core.exceptions import AppRegistryNotReady
from itertools import chain


class ComputedFieldsModelType(ModelBase):
    """
    Metaclass for computed field models.

    Handles the creation of the db fields. Also holds the needed data for
    graph calculations and dependency resolving.

    After startup the method ``_resolve_dependencies`` gets called by
    ``app.ready`` to build the dependency resolving map.
    To avoid the expensive calculations in production mode the map
    can be pickled into a map file by setting ``COMPUTEDFIELDS_MAP``
    in settings.py to a writable file path and calling the management
    command ``createmap``.

    .. NOTE::

        The map file will not be updated automatically and therefore
        must be recreated by calling the management command
        ``createmap`` after model changes.
    """
    _graph = None
    _computed_models = OrderedDict()
    _map = {}
    _map_loaded = False
    _lock = RLock()

    def __new__(mcs, name, bases, attrs):
        computed_fields = OrderedDict()
        if name != 'ComputedFieldsModel':
            for k, v in attrs.items():
                if getattr(v, '_computed', None):
                    computed_fields.update({k: v})
                    v.editable = False
                    v._computed.update({'attr': k})
        cls = super(ComputedFieldsModelType, mcs).__new__(mcs, name, bases, attrs)
        if name != 'ComputedFieldsModel':
            if hasattr(cls, '_computed_fields'):
                cls._computed_fields.update(computed_fields)
            else:
                cls._computed_fields = computed_fields
            if not cls._meta.abstract:
                mcs._computed_models[cls] = dict((k, v._computed['depends'])
                    for k, v in cls._computed_fields.items())
        return cls

    @classmethod
    def cf_mro(mcs, cls, update_fields=None):
        """
        Return mro for local computed field methods for a given set of ``update_fields``.
        This method returns computed fields as self dependent to simplify field calculation in ``save``.
        """
        # TODO: investigate - memoization of update_fields result? (runs ~4 times faster)
        entry = mcs._local_mro[cls]  # raise here, if cls is not a CMFT
        if update_fields is None:
            return entry['base']
        update_fields = frozenset(update_fields)
        base = entry['base']
        fields = entry['fields']
        mro = 0
        for f in update_fields:
            mro |= fields.get(f, 0)
        return [name for pos, name in enumerate(base) if mro & (1 << pos)]

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
        mcs._batchsize = getattr(settings, 'COMPUTEDFIELDS_BATCHSIZE', 100)
        with mcs._lock:
            if mcs._map_loaded and not _force:  # pragma: no cover
                return
            if (getattr(settings, 'COMPUTEDFIELDS_MAP', False)
                    and not force and not _force):
                import pickle
                with open(settings.COMPUTEDFIELDS_MAP, 'rb') as f:
                    pickled_data = pickle.load(f)
                    mcs._map = pickled_data['lookup_map']
                    mcs._fk_map = pickled_data['fk_map']
                    mcs._local_mro = pickled_data['local_mro']
                    mcs._map_loaded = True
                return
            mcs._graph = ComputedModelsGraph(mcs._computed_models)
            if not getattr(settings, 'COMPUTEDFIELDS_ALLOW_RECURSION', False):
                mcs._graph.remove_redundant()
                mcs._graph.get_uniongraph().get_edgepaths()  # uniongraph cyclefree?
            mcs._map = ComputedFieldsModelType._graph.generate_lookup_map()
            mcs._fk_map = mcs._graph._fk_map
            mcs._local_mro = mcs._graph.generate_local_mro_map()  # also tests for cycles on modelgraphs
            mcs._map_loaded = True

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
            #if not updates:
            #    updates.add('#')
        subquery = '__in' if isinstance(instance, models.QuerySet) else ''
        model_updates = OrderedDict()
        for update in updates:
            # first aggregate fields and paths to cover
            # multiple comp field dependencies
            for model, resolver in modeldata[update].items():
                fields, paths = resolver
                m_fields, m_paths = model_updates.setdefault(model, [set(), set()])
                m_fields.update(fields)
                m_paths.update(paths)
        for model, data in model_updates.items():
            fields, paths = data
            qs = model.objects.none()
            for path in paths:
                qs |= model.objects.filter(**{path+subquery: instance})
            if pk_list:
                # need pks for post_delete since the real queryset will be empty
                # after deleting the instance in question
                # since we need to interact with the db anyways
                # we can already drop empty results here
                qs = set(qs.distinct().values_list('pk', flat=True))
                if not qs:
                    continue
            final[model] = [qs, fields]
        return final

    @classmethod
    def preupdate_dependent(mcs, instance, model=None, update_fields=None):
        """
        Create a mapping of currently associated computed fields records,
        that would turn dirty by a follow-up bulk action.

        Feed the mapping back to ``update_dependent`` as ``old`` argument
        after your bulk action to update deassociated computed field records as well. 
        """
        if not model:
            model = instance.model if isinstance(instance, models.QuerySet) else type(instance)
        return mcs._querysets_for_update(model, instance, pk_list=True)
    
    @classmethod
    def preupdate_dependent_multi(mcs, instances):
        """
        Same as ``preupdate_dependent``, but for multiple bulk actions at once.

        After done with the bulk actions, feed the mapping back to ``update_dependent_multi``
        as ``old`` argument to update deassociated computed field records as well.
        """
        final = {}
        for instance in instances:
            model = instance.model if isinstance(instance, models.QuerySet) else type(instance)
            updates = mcs._querysets_for_update(model, instance, pk_list=True)
            for model, data in updates.items():
                m = final.setdefault(model, [model.objects.none(), set()])
                m[0] |= data[0]       # or'ed querysets
                m[1].update(data[1])  # add fields
        return final

    @classmethod
    def update_dependent(mcs, instance, model=None, update_fields=None, old=None, update_local=True):
        """
        Updates all dependent computed fields model objects.

        This is needed if you have computed fields that depend on a model
        changed by bulk actions. Simply call this function after the update
        with the queryset containing the changed objects.

            >>> Entry.objects.filter(pub_date__year=2010).update(comments_on=False)
            >>> update_dependent(Entry.objects.filter(pub_date__year=2010))

        This can also be used with ``bulk_create``. Since ``bulk_create``
        returns the objects in a python container, you have to create the queryset
        yourself, e.g. with pks:

            >>> objs = Entry.objects.bulk_create([
            ...     Entry(headline='This is a test'),
            ...     Entry(headline='This is only a test'),
            ... ])
            >>> pks = set(obj.pk for obj in objs)
            >>> update_dependent(Entry.objects.filter(pk__in=pks))

        .. NOTE::

            Getting pks from `bulk_create` is not supported by all database adapters.
            With a local computed field you can "cheat" here by providing a sentinel:

                >>> MyComputedModel.objects.bulk_create([
                ...     MyComputedModel(comp='SENTINEL'), # here or as default field value
                ...     MyComputedModel(comp='SENTINEL'),
                ... ])
                >>> update_dependent(MyComputedModel.objects.filter(comp='SENTINEL'))

            If the sentinel is beyond reach of the method result, this even ensures to update
            only the newly added records.
        
        Special care is needed, if a bulk action contains foreign key changes,
        that are part of a computed field dependency chain. To correctly handle that case,
        provide the result of ``preupdate_dependent`` as ``old`` argument like this:

                >>> # given: some computed fields model depends somehow on Entry.fk_field
                >>> old_relations = preupdate_dependent(Entry.objects.filter(pub_date__year=2010))
                >>> Entry.objects.filter(pub_date__year=2010).update(fk_field=new_related_obj)
                >>> update_dependent(Entry.objects.filter(pub_date__year=2010), old=old_relations)


        For completeness - ``instance`` can also be a single model instance.
        Since calling ``save`` on a model instance will trigger this function by
        the ``post_save`` signal it should not be invoked for single model
        instances, if they get saved anyway.
        """
        if not model:
            if isinstance(instance, models.QuerySet):
                model = instance.model
            else:
                model = type(instance)
        
        # Note: update_local is always off for updates triggered from the resolver
        # but True by default to avoid accidentally skipping updates called by user
        if update_local and isinstance(model, ComputedFieldsModelType):
            # We skip a transaction here in the same sense, as local cf updates are not guarded either.
            qs = instance if isinstance(instance, models.QuerySet) else model.objects.filter(pk__in=[instance.pk])
            if update_fields: # caution - might update update_fields, we ensure here, that it is always a set type
                update_fields = set(update_fields)
            mcs._bulker(qs, update_fields, local_only=True)
        
        updates = mcs._querysets_for_update(model, instance, update_fields).values()
        if updates:
            with transaction.atomic():
                pks_updated = {}
                for qs, fields in updates:
                    pks_updated[qs.model] = mcs._bulker(qs, fields, True)
                if old:
                    for model, data in old.items():
                        pks, fields = data
                        qs = model.objects.filter(pk__in=pks-pks_updated[model])
                        mcs._bulker(qs, fields)

    @classmethod
    def update_dependent_multi(mcs, instances, old=None, update_local=True):
        """
        Updates all dependent computed fields model objects for multiple instances.

        This function avoids redundant updates if consecutive ``update_dependent``
        have intersections, example:

            >>> update_dependent(Foo.objects.filter(i='x'))  # updates A, B, C
            >>> update_dependent(Bar.objects.filter(j='y'))  # updates B, C, D
            >>> update_dependent(Baz.objects.filter(k='z'))  # updates C, D, E

        In the example the models ``B`` and ``D`` would be queried twice,
        ``C`` even three times. It gets even worse if the queries contain record
        intersections, those items would be queried and saved several times.

        The updates above can be rewritten as:

            >>> update_dependent_multi([
            ...     Foo.objects.filter(i='x'),
            ...     Bar.objects.filter(j='y'),
            ...     Baz.objects.filter(k='z')])

        where all dependent model objects get queried and saved only once.
        The underlying querysets are expanded accordingly.

        .. NOTE::

            ``instances`` can also contain model instances. Don't use
            this function for model instances of the same type, instead
            aggregate those to querysets and use ``update_dependent``
            (as shown for ``bulk_create`` above).
        
        Again special care is needed, if the bulk actions involve foreign key changes,
        that are part of computed field dependency chains. Use ``preupdate_dependent_multi``
        to create a record mapping of the current state and after your bulk changes feed it back as
        ``old`` argument to this function.
        """
        final = {}
        for instance in instances:
            model = instance.model if isinstance(instance, models.QuerySet) else type(instance)

            if update_local and isinstance(model, ComputedFieldsModelType):
                qs = instance if isinstance(instance, models.QuerySet) else model.objects.filter(pk__in=[instance.pk])
                mcs._bulker(qs, None, local_only=True)

            updates = mcs._querysets_for_update(model, instance, None)
            for model, data in updates.items():
                m = final.setdefault(model, [model.objects.none(), set()])
                m[0] |= data[0]       # or'ed querysets
                m[1].update(data[1])  # add fields
        if final:
            with transaction.atomic():
                pks_updated = {}
                for qs, fields in final.values():
                    pks_updated[qs.model] = mcs._bulker(qs, fields, True)
                if old:
                    for model, data in old.items():
                        pks, fields = data
                        qs = model.objects.filter(pk__in=pks-pks_updated[model])
                        mcs._bulker(qs, fields)

    @classmethod
    def _bulker(mcs, qs, update_fields, return_pks=False, local_only=False):
        """
        Update computed fields with `bulk_update`, which gives a speedup of 10-35%.
        """
        qs = qs.distinct()

        # correct update_fields by local mro
        mro = mcs.cf_mro(qs.model, update_fields)
        fields = set(mro)
        if update_fields:
            update_fields.update(fields)

        # FIXME: precalc and check prefetch/select related entries during map creation somehow?
        select = set()
        prefetch = []
        for field in fields:
            select.update(qs.model._computed_fields[field]._computed['select_related'] or [])
            prefetch.extend(qs.model._computed_fields[field]._computed['prefetch_related'] or [])
        if select:
            qs = qs.select_related(*select)
        if prefetch:
            qs = qs.prefetch_related(*prefetch)

        # do bulk_update on computed fields in question
        # set COMPUTEDFIELDS_BATCHSIZE in settings.py to adjust batchsize (default 100)
        if fields:
            change = []
            for el in qs:
                has_changed = False
                for comp_field in mro:
                    new_value = el._compute(comp_field)
                    if new_value != getattr(el, comp_field):
                        has_changed = True
                        setattr(el, comp_field, new_value)
                if has_changed:
                    change.append(el)
                if len(change) >= mcs._batchsize:
                    qs.model.objects.bulk_update(change, fields)
                    change = []
            qs.model.objects.bulk_update(change, fields)

        # trigger dependent comp field updates on all records
        if not local_only:
            update_dependent(qs, qs.model, fields, update_local=False)
        if return_pks:
            return set(el.pk for el in qs)
        return


update_dependent = ComputedFieldsModelType.update_dependent
update_dependent_multi = ComputedFieldsModelType.update_dependent_multi
preupdate_dependent = ComputedFieldsModelType.preupdate_dependent
preupdate_dependent_multi = ComputedFieldsModelType.preupdate_dependent_multi

def get_contributing_fks():
    """
    Get a mapping of models and their local fk fields,
    that are part of a computed fields dependency chain.

    Whenever a bulk action changes one of the fields listed here, you have to create
    a listing of the currently associated  records with ``preupdate_dependent`` and,
    after doing the bulk change, feed the listing back to ``update_dependent``.

    This mapping can also be inspected as admin view,
    if ``COMPUTEDFIELDS_ADMIN`` is set to ``True``.
    """
    if not ComputedFieldsModelType._map_loaded:  # pragma: no cover
        raise AppRegistryNotReady
    return ComputedFieldsModelType._fk_map


class ComputedFieldsModel(models.Model, metaclass=ComputedFieldsModelType):
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

            @computed(models.CharField(max_length=32), depends=[['self', ['surname', 'forename']]])
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
    class Meta:
        abstract = True

    def _compute(self, fieldname):
        """
        Returns the computed field value for ``fieldname``.
        Note that this is just a shorthand method for calling the underlying computed
        field method and does not deal with local MRO, thus should only be used,
        if the MRO is respected by other means.
        For quick inspection of a single computed field value that gonna be written
        to the database, always use ``compute(fieldname)`` instead.
        """
        field = self._computed_fields[fieldname]
        return field._computed['func'](self)

    def compute(self, fieldname):
        """
        Returns the computed field value for ``fieldname``. This method allows
        to inspect the new calculated value, that would be written to the database
        by a following ``save()``.
        """
        # Getting a single computed value prehand is quite complicated,
        # as we have to:
        # - resolve local MRO backwards (stored MRO data is optimized for forward deps)
        # - calc all local cfs, that the requested one depends on
        # - stack and rewind interim values, as we dont want to introduce side effects here
        #   (in fact the save/bulker logic might try to save db calls based on changes)
        entries = ComputedFieldsModelType._local_mro[type(self)]['fields']
        mro = ComputedFieldsModelType.cf_mro(type(self), None)
        if not fieldname in mro:
            return getattr(self, fieldname)
        pos = 1 << mro.index(fieldname)
        stack = []
        for field in mro:
            if field == fieldname:
                ret = self._compute(fieldname)
                for field, old in stack:
                    # reapply old stack values
                    setattr(self, field, old)
                return ret
            f_mro = entries.get(field, 0)
            if f_mro & pos:
                # append old value to stack for later rewinding
                # calc and set new value for field, if the requested one depends on it
                stack.append((field, getattr(self, field)))
                setattr(self, field, self._compute(field))

    def save(self, *args, **kwargs):
        """
        Save the current instance. Note that for ``update_fields=None`` (default)
        all computed fields on the instance will be re-evaluated.
        If `update_fields` is set, it might get expanded by computed fields
        that depend on fields listed there.
        """
        # TODO: eval correct dealing with update_fields in save:
        #
        # Problem:
        #   update_fields is defined as a positive list containing fields that should be written to database.
        #   We should not lightheartedly break with that meaning in ComputedFieldsModel.save by obscure auto-adding
        #   computed fields without further notion.
        #   On the other hand we already do this for intermodel dependencies without a way to intercept that behavior.
        #
        # Solution:
        #   To have a uniform default handling of dependency updates within computedfields, deviate here from django's
        #   default behavior - by default we gonna add dependent local computed fields automatically
        #   to incoming update_fields based on the mro rules. Furthermore implement a keyword argument for save to
        #   explicitly drop back to django's default behavior (something like `no_autoadd_computedfields`).
        #   Make a clear statement in the docs about this change in behavior.
        #
        # Unclear:
        #   Do we need a similar mechanism to temporarily switch off cf handling (skipping any signal handler)?
        #
        # FIXME: add custom kwargs to finetune cf handling
        update_fields = kwargs.get('update_fields')
        cls = type(self)
        cf_mro = ComputedFieldsModelType.cf_mro(cls, update_fields)
        if update_fields:
            update_fields = set(update_fields)
            # mro_plus: contains cfs, that additionally have to be updated
            # update_fields_corrected: update_fields expanded by additional cfs from mro
            mro_plus = set(cf_mro) - update_fields
            update_fields_corrected = set(update_fields)
            update_fields_corrected.update(mro_plus)
            # update update_fields by additional dependent local cfs
            kwargs['update_fields'] = update_fields_corrected
            all_computed = not (update_fields_corrected - set(self._computed_fields.keys()))
            if all_computed:
                has_changed = False
                for fieldname in cf_mro:
                    result = self._compute(fieldname)
                    if result != getattr(self, fieldname):
                        has_changed = True
                        setattr(self, fieldname, result)
                if not has_changed:
                    # no save needed, we still need to update dependent objects
                    update_dependent(self, cls, update_fields_corrected, update_local=False)
                    return
                super(ComputedFieldsModel, self).save(*args, **kwargs)
                return
        for fieldname in cf_mro:
            result = self._compute(fieldname)
            setattr(self, fieldname, result)
        super(ComputedFieldsModel, self).save(*args, **kwargs)


def computed(field, depends=None, select_related=None, prefetch_related=None):
    """
    Decorator to create computed fields.

    ``field`` should be a model concrete field instance suitable to hold the result
    of the decorated method. The decorator expects a
    keyword argument ``depends`` to indicate dependencies to
    model fields (local or related). Listed dependencies will automatically
    update the computed field.

    Examples:

        - create a char field with no further dependencies (not very useful)

          .. code-block:: python

            @computed(models.CharField(max_length=32), depends=[])
            def ...

        - create a char field with one dependency to the field
          ``name`` of a foreign key relation ``fk``

          .. code-block:: python

            @computed(models.CharField(max_length=32), depends=[['fk', ['name']]])
            def ...

    Dependencies should be listed as ``['relation_name', fieldnames_on_that_model]``.
    The relation can span serveral models, simply name the relation
    in python style with a dot (e.g. ``'a.b.c'``). A relation can be of any of
    foreign key, m2m, o2o and their back relations.
    The fieldnames should be a list of strings of concrete fields on the foreign model.

    With `select_related` and `prefetch_related` you can instruct the dependency resolver
    to apply certain optimizations on the select for update queryset later on
    `(currently alpha)`.

    .. NOTE::

        `select_related` and `prefetch_related` are stacked over computed fields
        of the same model during updates, that are going to be updated.
        They call the underlying queryset methods of the default model manager,
        e.g. ``default_manager.select_related(*(lookups_of_a | lookups_of_b))``.
        If your optimizations contain custom attributes (as with `to_attr` of a ``Prefetch`` object),
        these attributes will only be available during updates from the resolver, never during
        instance construction or instances from other queries, unless you applied the same
        lookups manually. To keep the computed field methods working under any circumstances,
        it is a good idea not to rely on lookups with custom attributes,
        or to test explicitly for them in the method.

    .. CAUTION::

        With the dependency auto resolver you can easily create
        recursive dependencies by accident. Imagine the following:

        .. code-block:: python

            class A(ComputedFieldsModel):
                @computed(models.CharField(max_length=32), depends=[['b_set', ['comp']]])
                def comp(self):
                    return ''.join(b.comp for b in self.b_set.all())

            class B(ComputedFieldsModel):
                a = models.ForeignKey(A)

                @computed(models.CharField(max_length=32), depends=[['a', ['comp']]])
                def comp(self):
                    return a.comp

        Neither an object of ``A`` or ``B`` can be saved, since the
        ``comp`` fields depend on each other. While it is quite easy
        to spot for this simple case it might get tricky for more
        complicated dependencies. Therefore the dependency resolver tries
        to detect cyclic dependencies and raises a ``CycleNodeException``
        in case a cycle was found.

        If you experience this in your project try to get in-depth cycle
        information, either by using the ``rendergraph`` management command or
        by directly accessing the graph objects:

        - intermodel dependency graph: ``your_model._graph``
        - mode local dependency graphs: ``your_model._graph.modelgraphs[your_model]``
        - union graph: ``your_model._graph.get_uniongraph()``

        Also see the graph documentation :ref:`here<graph>`.
    """
    def wrap(f):
        field._computed = {
            'func': f,
            'depends': depends,
            'select_related': select_related,
            'prefetch_related': prefetch_related
        }
        return field
    return wrap


class ComputedModelManager(models.Manager):
    def get_queryset(self):
        objs = ContentType.objects.get_for_models(
            *ComputedFieldsModelType._computed_models.keys()).values()
        pks = [model.pk for model in objs]
        return ContentType.objects.filter(pk__in=pks)


class ComputedFieldsAdminModel(ContentType):
    """
    Proxy model to list all ``ComputedFieldsModel`` models with their
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


class ModelsWithContributingFkFieldsManager(models.Manager):
    def get_queryset(self):
        objs = ContentType.objects.get_for_models(
            *ComputedFieldsModelType._fk_map.keys()).values()
        pks = [model.pk for model in objs]
        return ContentType.objects.filter(pk__in=pks)


class ContributingModelsModel(ContentType):
    """
    Proxy model to list all models in admin, that contain fk fields contributing to computed fields.
    This might be useful during development.
    To enable it, set ``COMPUTEDFIELDS_ADMIN`` in settings.py to ``True``.
    An fk field is considered contributing, if it is part of a computed field dependency,
    thus a change to it would impact a computed field.
    """
    objects = ModelsWithContributingFkFieldsManager()

    class Meta:
        proxy = True
        managed = False
        verbose_name = _('Model with contributing Fk Fields')
        verbose_name_plural = _('Models with contributing Fk Fields')
        ordering = ('app_label', 'model')
