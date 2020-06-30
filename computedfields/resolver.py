from django.db import transaction
from django.db.models import QuerySet, IntegerField
from collections import OrderedDict
from computedfields.graph import ComputedModelsGraph, ComputedFieldsException
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from threading import RLock
from django.core.exceptions import AppRegistryNotReady


class ResolverException(ComputedFieldsException):
    """
    Exception raised during model and field registration or dependency resolving.
    """
    pass


class Resolver:
    """
    Holds the needed data for graph calculations and dependency resolving.

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
    _lock = RLock()


    def __init__(self):
        # collector phase data
        self.models = set()
        self.computedfields = set()
        self.sealed = False

        # resolving phase data and final maps
        self._graph = None
        self._computed_models = {}
        self._map = {}
        self._fk_map = {}
        self._local_mro = {}
        self._map_loaded = False
        self._batchsize = getattr(settings, 'COMPUTEDFIELDS_BATCHSIZE', 100)
    
    def seal(self):
        self.sealed = True

    def add_model(self, sender, **kwargs):
        """
        Endpoint of the class_prepared signal to collect models
        during ORM registration.
        """
        if self.sealed:
            raise ResolverException('cannot add models on sealed resolver')
        self.models.add(sender)

    def add_field(self, field):
        """
        Collects fields from decoration stage of @computed.
        """
        if self.sealed:
            raise ResolverException('cannot add computed fields on sealed resolver')
        self.computedfields.add(field)

    @property
    def models_with_computedfields(self):
        """
        Generator of all traced models and computed fields
        returning (model, list_of_computedfields).
        """
        if not self.sealed:
            raise ResolverException('resolver must be sealed before accessing model field associations')
        for model in self.models:
            fields = set()
            for field in model._meta.fields:
                if field in self.computedfields:
                    fields.add(field)
            yield (model, fields)
    
    @property
    def computedfields_with_models(self):
        """
        Generator of all traced models and computed fields
        returning (computedfield, list_of_models).
        """
        if not self.sealed:
            raise ResolverException('resolver must be sealed before accessing model field associations')
        for field in self.computedfields:
            models = set()
            for model in self.models:
                if field in model._meta.fields:
                    models.add(model)
            yield (field, models)

    def cf_mro(self, model, update_fields=None):
        """
        Return mro for local computed field methods for a given set of ``update_fields``.
        This method returns computed fields as self dependent to simplify field calculation in ``save``.
        """
        # TODO: investigate - memoization of update_fields result? (runs ~4 times faster)
        entry = self._local_mro[model]  # raise here, if model is not a CMFT - FIXME: can happen, if model has no cf
        if update_fields is None:
            return entry['base']
        update_fields = frozenset(update_fields)
        base = entry['base']
        fields = entry['fields']
        mro = 0
        for f in update_fields:
            mro |= fields.get(f, 0)
        return [name for pos, name in enumerate(base) if mro & (1 << pos)]
    
    def extract_computed_models(self):
        # pull _computed_fields from collector
        computed_models = {}
        for model, computedfields in self.models_with_computedfields:
            if not computedfields:
                continue
            computed_models[model] = {}
            _computed_fields = {}       # FIXME: remove from codebase
            for field in computedfields:
                computed_models[model][field.name] = field._computed['depends']
                _computed_fields[field.name] = field
            model._computed_fields = _computed_fields  # FIXME: to be removed
        return computed_models
    
    def initialize(self):
        # resolver must be sealed before doing any map calculations
        self.seal()
        # FIXME: skip this step in static map mode
        self._computed_models = self.extract_computed_models()
        self._resolve_dependencies()


    def _resolve_dependencies(self, force=False, _force=False):
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
        with self._lock:
            if self._map_loaded and not _force:  # pragma: no cover
                return
            if (getattr(settings, 'COMPUTEDFIELDS_MAP', False)
                    and not force and not _force):
                import pickle
                with open(settings.COMPUTEDFIELDS_MAP, 'rb') as f:
                    pickled_data = pickle.load(f)
                    self._map = pickled_data['lookup_map']
                    self._fk_map = pickled_data['fk_map']
                    self._local_mro = pickled_data['local_mro']
                    self._map_loaded = True
                return
            self._graph = ComputedModelsGraph(self._computed_models)
            if not getattr(settings, 'COMPUTEDFIELDS_ALLOW_RECURSION', False):
                self._graph.remove_redundant()
                self._graph.get_uniongraph().get_edgepaths()  # uniongraph cyclefree?
            self._map = self._graph.generate_lookup_map()
            self._fk_map = self._graph._fk_map
            self._local_mro = self._graph.generate_local_mro_map()  # also tests for cycles on modelgraphs
            self._map_loaded = True

    def _querysets_for_update(self, model, instance, update_fields=None, pk_list=False):
        """
        Returns a mapping of all dependent models, dependent fields and a
        queryset containing all dependent objects.
        """
        final = OrderedDict()
        modeldata = self._map.get(model)
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
        subquery = '__in' if isinstance(instance, QuerySet) else ''
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

    def preupdate_dependent(self, instance, model=None, update_fields=None):
        """
        Create a mapping of currently associated computed fields records,
        that would turn dirty by a follow-up bulk action.

        Feed the mapping back to ``update_dependent`` as ``old`` argument
        after your bulk action to update deassociated computed field records as well. 
        """
        if not model:
            model = instance.model if isinstance(instance, QuerySet) else type(instance)
        return self._querysets_for_update(model, instance, pk_list=True)
    
    def preupdate_dependent_multi(self, instances):
        """
        Same as ``preupdate_dependent``, but for multiple bulk actions at once.

        After done with the bulk actions, feed the mapping back to ``update_dependent_multi``
        as ``old`` argument to update deassociated computed field records as well.
        """
        final = {}
        for instance in instances:
            model = instance.model if isinstance(instance, QuerySet) else type(instance)
            updates = self._querysets_for_update(model, instance, pk_list=True)
            for model, data in updates.items():
                m = final.setdefault(model, [model.objects.none(), set()])
                m[0] |= data[0]       # or'ed querysets
                m[1].update(data[1])  # add fields
        return final

    def update_dependent(self, instance, model=None, update_fields=None, old=None, update_local=True):
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
            if isinstance(instance, QuerySet):
                model = instance.model
            else:
                model = type(instance)
        
        # Note: update_local is always off for updates triggered from the resolver
        # but True by default to avoid accidentally skipping updates called by user
        if update_local and self.has_computedfields(model):
            # We skip a transaction here in the same sense, as local cf updates are not guarded either.
            qs = instance if isinstance(instance, QuerySet) else model.objects.filter(pk__in=[instance.pk])
            if update_fields: # caution - might update update_fields, we ensure here, that it is always a set type
                update_fields = set(update_fields)
            self._bulker(qs, update_fields, local_only=True)
        
        updates = self._querysets_for_update(model, instance, update_fields).values()
        if updates:
            with transaction.atomic():
                pks_updated = {}
                for qs, fields in updates:
                    pks_updated[qs.model] = self._bulker(qs, fields, True)
                if old:
                    for model, data in old.items():
                        pks, fields = data
                        qs = model.objects.filter(pk__in=pks-pks_updated[model])
                        self._bulker(qs, fields)

    def update_dependent_multi(self, instances, old=None, update_local=True):
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
            model = instance.model if isinstance(instance, QuerySet) else type(instance)

            if update_local and self.has_computedfields(model):
                qs = instance if isinstance(instance, QuerySet) else model.objects.filter(pk__in=[instance.pk])
                self._bulker(qs, None, local_only=True)

            updates = self._querysets_for_update(model, instance, None)
            for model, data in updates.items():
                m = final.setdefault(model, [model.objects.none(), set()])
                m[0] |= data[0]       # or'ed querysets
                m[1].update(data[1])  # add fields
        if final:
            with transaction.atomic():
                pks_updated = {}
                for qs, fields in final.values():
                    pks_updated[qs.model] = self._bulker(qs, fields, True)
                if old:
                    for model, data in old.items():
                        pks, fields = data
                        qs = model.objects.filter(pk__in=pks-pks_updated[model])
                        self._bulker(qs, fields)

    def _bulker(self, qs, update_fields, return_pks=False, local_only=False):
        """
        Update computed fields with `bulk_update`, which gives a speedup of 10-35%.
        """
        qs = qs.distinct()

        # correct update_fields by local mro
        mro = self.cf_mro(qs.model, update_fields)
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
                    new_value = self._compute(el, comp_field)
                    if new_value != getattr(el, comp_field):
                        has_changed = True
                        setattr(el, comp_field, new_value)
                if has_changed:
                    change.append(el)
                if len(change) >= self._batchsize:
                    qs.model.objects.bulk_update(change, fields)
                    change = []
            qs.model.objects.bulk_update(change, fields)

        # trigger dependent comp field updates on all records
        if not local_only:
            self.update_dependent(qs, qs.model, fields, update_local=False)
        if return_pks:
            return set(el.pk for el in qs)
        return
    
    def _compute(self, instance, fieldname):
        """
        Returns the computed field value for ``fieldname``.
        Note that this is just a shorthand method for calling the underlying computed
        field method and does not deal with local MRO, thus should only be used,
        if the MRO is respected by other means.
        For quick inspection of a single computed field value that gonna be written
        to the database, always use ``compute(fieldname)`` instead.
        """
        field = instance._computed_fields[fieldname]
        return field._computed['func'](instance)

    def compute(self, instance, fieldname):
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
        entries = self._local_mro[type(instance)]['fields']
        mro = self.cf_mro(type(instance), None)
        if not fieldname in mro:
            return getattr(instance, fieldname)
        pos = 1 << mro.index(fieldname)
        stack = []
        for field in mro:
            if field == fieldname:
                ret = self._compute(instance, fieldname)
                for field, old in stack:
                    # reapply old stack values
                    setattr(instance, field, old)
                return ret
            f_mro = entries.get(field, 0)
            if f_mro & pos:
                # append old value to stack for later rewinding
                # calc and set new value for field, if the requested one depends on it
                stack.append((field, getattr(instance, field)))
                setattr(instance, field, self._compute(instance, field))

    def get_contributing_fks(self):
        """
        Get a mapping of models and their local fk fields,
        that are part of a computed fields dependency chain.

        Whenever a bulk action changes one of the fields listed here, you have to create
        a listing of the currently associated  records with ``preupdate_dependent`` and,
        after doing the bulk change, feed the listing back to ``update_dependent``.

        This mapping can also be inspected as admin view,
        if ``COMPUTEDFIELDS_ADMIN`` is set to ``True``.
        """
        if not self._map_loaded:  # pragma: no cover
            raise AppRegistryNotReady
        return self._fk_map

    def computed(self, field, depends=None, select_related=None, prefetch_related=None):
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
            field.editable = False
            self.add_field(field)
            return field
        return wrap

    def has_computedfields(self, model):
        """
        Indicate whether a model has computed fields.
        """
        return model in self._computed_models

    def update_computedfields(self, instance, update_fields=None):
        """
        Update values of local computed fields of ``instance``. The values are written
        to the instance itself (other than for ``compute(fieldname)``). This method is helpful
        to get updated computed field values in a custom `save` method..............................

        Returns ``None`` or an updated set of field names for ``update_fields``.
        """
        model = type(instance)
        cf_mro = self.cf_mro(model, update_fields)
        if update_fields:
            update_fields = set(update_fields)
            update_fields.update(set(cf_mro))
        for fieldname in cf_mro:
            setattr(instance, fieldname, self._compute(instance, fieldname))
        if update_fields:
            return update_fields
        return None


# active_resolver is currently treated as global singleton (used in imports)
active_resolver = Resolver()

# BOOT_RESOLVER: resolver that holds all startup declarations and resolve maps
# gets deactivated after startup, thus it is currently not possible to define
# new computed fields and add their resolve rules at runtime
# TODO: investigate on custom resolvers at runtime to be bootstrapped from BOOT_RESOLVER
BOOT_RESOLVER = active_resolver
