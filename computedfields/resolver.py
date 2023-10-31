"""
Contains the resolver logic for automated computed field updates.
"""
import operator
from collections import OrderedDict
from functools import reduce
from itertools import zip_longest

from django.db import transaction
from django.db.models import QuerySet
from django.core.exceptions import FieldDoesNotExist

from .helpers import are_same
from .settings import settings
from .graph import ComputedModelsGraph, ComputedFieldsException, Graph, ModelGraph
from .helper import proxy_to_base_model, slice_iterator, subquery_pk
from . import __version__

from fast_update.fast import fast_update

# typing imports
from typing import (Any, Callable, Dict, Generator, Iterable, List, Optional, Sequence, Set,
                    Tuple, Type, Union, cast, overload)
from typing_extensions import TypedDict
from django.db.models import Field, Model
from .graph import IComputedField, IDepends, IFkMap, ILocalMroMap, ILookupMap, _ST, _GT, F


class IM2mData(TypedDict):
    left: str
    right: str
IM2mMap = Dict[Type[Model], IM2mData]


MALFORMED_DEPENDS = """
Your depends keyword argument is malformed.

The depends keyword should either be None, an empty listing or
a listing of rules as depends=[rule1, rule2, .. ruleN].

A rule is formed as ('relation.path', ['list', 'of', 'fieldnames']) tuple.
The relation path either contains 'self' for fieldnames on the same model,
or a string as 'a.b.c', where 'a' is a relation on the current model
descending over 'b' to 'c' to pull fieldnames from 'c'. The denoted fieldnames
must be concrete fields on the rightmost model of the relation path.

Example:
depends=[
    ('self', ['name', 'status']),
    ('parent.color', ['value'])
]
This has 2 path rules - one for fields 'name' and 'status' on the same model,
and one to a field 'value' on a foreign model, which is accessible from
the current model through self -> parent -> color relation.
"""


class ResolverException(ComputedFieldsException):
    """
    Exception raised during model and field registration or dependency resolving.
    """


class Resolver:
    """
    Holds the needed data for graph calculations and runtime dependency resolving.

    Basic workflow:

        - On django startup a resolver gets instantiated early to track all project-wide
          model registrations and computed field decorations (collector phase).
        - On `app.ready` the computed fields are associated with their models to build
          a resolver-wide map of models with computed fields (``computed_models``).
        - After that the resolver maps are created (see `graph.ComputedModelsGraph`).
    """

    def __init__(self):
        # collector phase data
        #: Models from `class_prepared` signal hook during collector phase.
        self.models: Set[Type[Model]] = set()
        #: Computed fields found during collector phase.
        self.computedfields: Set[IComputedField] = set()

        # resolving phase data and final maps
        self._graph: Optional[ComputedModelsGraph] = None
        self._computed_models: Dict[Type[Model], Dict[str, IComputedField]] = {}
        self._map: ILookupMap = {}
        self._fk_map: IFkMap = {}
        self._local_mro: ILocalMroMap = {}
        self._m2m: IM2mMap = {}
        self._proxymodels: Dict[Type[Model], Type[Model]] = {}
        self.use_fastupdate: bool = settings.COMPUTEDFIELDS_FASTUPDATE
        self._batchsize: int = (settings.COMPUTEDFIELDS_BATCHSIZE_FAST
            if self.use_fastupdate else settings.COMPUTEDFIELDS_BATCHSIZE_BULK)

        # some internal states
        self._sealed: bool = False        # initial boot phase
        self._initialized: bool = False   # initialized (computed_models populated)?
        self._map_loaded: bool = False    # final stage with fully loaded maps

    def add_model(self, sender: Type[Model], **kwargs) -> None:
        """
        `class_prepared` signal hook to collect models during ORM registration.
        """
        if self._sealed:
            raise ResolverException('cannot add models on sealed resolver')
        self.models.add(sender)

    def add_field(self, field: IComputedField) -> None:
        """
        Collects fields from decoration stage of @computed.
        """
        if self._sealed:
            raise ResolverException('cannot add computed fields on sealed resolver')
        self.computedfields.add(field)

    def seal(self) -> None:
        """
        Seal the resolver, so no new models or computed fields can be added anymore.

        This marks the end of the collector phase and is a basic security measure
        to catch runtime model creations with computed fields.

        (Currently runtime creation of models with computed fields is not supported,
        trying to do so will raise an exception. This might change in future versions.)
        """
        self._sealed = True

    @property
    def models_with_computedfields(self) -> Generator[Tuple[Type[Model], Set[IComputedField]], None, None]:
        """
        Generator of tracked models with their computed fields.

        This cannot be accessed during the collector phase.
        """
        if not self._sealed:
            raise ResolverException('resolver must be sealed before accessing models or fields')

        field_ids: List[int] = [f.creation_counter for f in self.computedfields]
        for model in self.models:
            fields = set()
            for field in model._meta.fields:
                # for some reason the in ... check does not work for Django >= 3.2 anymore
                # workaround: check for _computed and the field creation_counter
                if hasattr(field, '_computed') and field.creation_counter in field_ids:
                    fields.add(field)
            if fields:
                yield (model, fields)

    @property
    def computedfields_with_models(self) -> Generator[Tuple[IComputedField, Set[Type[Model]]], None, None]:
        """
        Generator of tracked computed fields and their models.

        This cannot be accessed during the collector phase.
        """
        if not self._sealed:
            raise ResolverException('resolver must be sealed before accessing models or fields')

        for field in self.computedfields:
            models = set()
            for model in self.models:
                for f in model._meta.fields:
                    if hasattr(field, '_computed') and f.creation_counter == field.creation_counter:
                        models.add(model)
            yield (field, models)

    @property
    def computed_models(self) -> Dict[Type[Model], Dict[str, IComputedField]]:
        """
        Mapping of `ComputedFieldModel` models and their computed fields.

        The data is the single source of truth for the graph reduction and
        map creations. Thus it can be used to decide at runtime whether
        the active resolver a certain as a model with computed fields.
        
        .. NOTE::
        
            The resolver will only list models here, that actually have
            a computed field defined. A model derived from `ComputedFieldsModel`
            without a computed field will not be listed.
        """
        if self._initialized:
            return self._computed_models
        raise ResolverException('resolver is not properly initialized')

    def extract_computed_models(self) -> Dict[Type[Model], Dict[str, IComputedField]]:
        """
        Creates `computed_models` mapping from models and computed fields
        found in collector phase.
        """
        computed_models: Dict[Type[Model], Dict[str, IComputedField]] = {}
        for model, computedfields in self.models_with_computedfields:
            if not issubclass(model, _ComputedFieldsModelBase):
                raise ResolverException(f'{model} is not a subclass of ComputedFieldsModel')
            computed_models[model] = {}
            for field in computedfields:
                computed_models[model][field.attname] = field

        return computed_models

    def initialize(self, models_only: bool = False) -> None:
        """
        Entrypoint for ``app.ready`` to seal the resolver and trigger
        the resolver map creation.

        Upon instantiation the resolver is in the collector phase, where it tracks
        model registrations and computed field decorations.

        After calling ``initialize`` no more models or fields can be registered
        to the resolver, and ``computed_models`` and the resolver maps get loaded.
        """
        # resolver must be sealed before doing any map calculations
        self.seal()
        self._computed_models = self.extract_computed_models()
        self._initialized = True
        if not models_only:
            self.load_maps()

    def load_maps(self, _force_recreation: bool = False) -> None:
        """
        Load all needed resolver maps. The steps are:

            - create intermodel graph of the dependencies
            - remove redundant paths with cycling check
            - create modelgraphs for local MRO
            - merge graphs to uniongraph with cycling check
            - create final resolver maps

                - `lookup_map`: intermodel dependencies as queryset access strings
                - `fk_map`: models with their contributing fk fields
                - `local_mro`: MRO of local computed fields per model
        """
        self._graph = ComputedModelsGraph(self.computed_models)
        if not getattr(settings, 'COMPUTEDFIELDS_ALLOW_RECURSION', False):
            self._graph.get_edgepaths()
            self._graph.get_uniongraph().get_edgepaths()
        self._map, self._fk_map = self._graph.generate_maps()
        self._local_mro = self._graph.generate_local_mro_map()
        self._extract_m2m_through()
        self._patch_proxy_models()
        self._map_loaded = True

    def _extract_m2m_through(self) -> None:
        """
        Creates M2M through model mappings with left/right field names.
        The map is used by the m2m_changed handler for faster name lookups.
        This cannot be pickled, thus is built for every resolver bootstrapping.
        """
        for model, fields in self.computed_models.items():
            for _, real_field in fields.items():
                depends = real_field._computed['depends']
                for path, _ in depends:
                    if path == 'self':
                        continue
                    cls: Type[Model] = model
                    for symbol in path.split('.'):
                        try:
                            rel: Any = cls._meta.get_field(symbol)
                            if rel.many_to_many:
                                if hasattr(rel, 'through'):
                                    self._m2m[rel.through] = {
                                        'left': rel.remote_field.name, 'right': rel.name}
                                else:
                                    self._m2m[rel.remote_field.through] = {
                                        'left': rel.name, 'right': rel.remote_field.name}
                        except FieldDoesNotExist:
                            descriptor = getattr(cls, symbol)
                            rel = getattr(descriptor, 'rel', None) or getattr(descriptor, 'related')
                        cls = rel.related_model

    def _patch_proxy_models(self) -> None:
        """
        Patch proxy models into the resolver maps.
        """
        for model in self.models:
            if model._meta.proxy:
                basemodel = proxy_to_base_model(model)
                if basemodel in self._map:
                    self._map[model] = self._map[basemodel]
                if basemodel in self._fk_map:
                    self._fk_map[model] = self._fk_map[basemodel]
                if basemodel in self._local_mro:
                    self._local_mro[model] = self._local_mro[basemodel]
                if basemodel in self._m2m:
                    self._m2m[model] = self._m2m[basemodel]
                self._proxymodels[model] = basemodel or model

    def get_local_mro(
        self,
        model: Type[Model],
        update_fields: Optional[Iterable[str]] = None
    ) -> List[str]:
        """
        Return `MRO` for local computed field methods for a given set of `update_fields`.
        The returned list of fieldnames must be calculated in order to correctly update
        dependent computed field values in one pass.

        Returns computed fields as self dependent to simplify local field dependency calculation.
        """
        # TODO: investigate - memoization of update_fields result? (runs ~4 times faster)
        entry = self._local_mro.get(model)
        if not entry:
            return []
        if update_fields is None:
            return entry['base']
        update_fields = frozenset(update_fields)
        base = entry['base']
        fields = entry['fields']
        mro = 0
        for field in update_fields:
            mro |= fields.get(field, 0)
        return [name for pos, name in enumerate(base) if mro & (1 << pos)]

    def _querysets_for_update(
        self,
        model: Type[Model],
        instance: Union[Model, QuerySet],
        update_fields: Optional[Iterable[str]] = None,
        pk_list: bool = False,
        m2m: Optional[Model] = None
    ) -> Dict[Type[Model], List[Any]]:
        """
        Returns a mapping of all dependent models, dependent fields and a
        queryset containing all dependent objects.
        """
        final: Dict[Type[Model], List[Any]] = OrderedDict()
        modeldata = self._map.get(model)
        if not modeldata:
            return final
        if not update_fields:
            updates: Set[str] = set(modeldata.keys())
        else:
            updates = set()
            for fieldname in update_fields:
                if fieldname in modeldata:
                    updates.add(fieldname)
        subquery = '__in' if isinstance(instance, QuerySet) else ''

        # fix #100
        # mysql does not support 'LIMIT & IN/ALL/ANY/SOME subquery'
        # thus we extract pks explicitly instead
        # TODO: cleanup type mess here including this workaround
        if isinstance(instance, QuerySet):
            from django.db import connections
            if not instance.query.can_filter() and connections[instance.db].vendor == 'mysql':
                instance = set(instance.values_list('pk', flat=True).iterator())

        model_updates: Dict[Type[Model], Tuple[Set[str], Set[str]]] = OrderedDict()
        for update in updates:
            # first aggregate fields and paths to cover
            # multiple comp field dependencies
            for model, resolver in modeldata[update].items():
                fields, paths = resolver
                m_fields, m_paths = model_updates.setdefault(model, (set(), set()))
                m_fields.update(fields)
                m_paths.update(paths)

        # generate narrowed down querysets for all cf dependencies
        for model, data in model_updates.items():
            fields, paths = data

            # queryset construction
            if m2m and self._proxymodels.get(type(m2m), type(m2m)) == model:
                # M2M optimization: got called through an M2M signal
                # narrow updates to the single signal instance
                queryset = model._base_manager.filter(pk=m2m.pk)
            else:
                queryset: Any = model._base_manager.none()
                query_pipe_method = self._choose_optimal_query_pipe_method(paths)
                queryset = reduce(
                    query_pipe_method,
                    (model._base_manager.filter(**{path+subquery: instance}) for path in paths),
                    queryset
                )
            if pk_list:
                # need pks for post_delete since the real queryset will be empty
                # after deleting the instance in question
                # since we need to interact with the db anyways
                # we can already drop empty results here
                queryset = set(queryset.values_list('pk', flat=True).iterator())
                if not queryset:
                    continue
            # FIXME: change to tuple or dict for narrower type
            final[model] = [queryset, fields]
        return final
    
    def _get_model(self, instance: Union[Model, QuerySet]) -> Type[Model]:
        return instance.model if isinstance(instance, QuerySet) else type(instance)

    def _choose_optimal_query_pipe_method(self, paths: Set[str]) -> Callable:
        """
            Choose optimal pipe method, to combine querystes.
            Returns `|` if there are only one element or the difference is only the fields name, on the same path.
            Otherwise, return union.
        """
        if len(paths) == 1:
            return operator.or_
        else:
            paths_by_parts = tuple(path.split("__") for path in paths)
            if are_same(*(len(path_in_parts) for path_in_parts in paths_by_parts)):
                max_depth = len(paths_by_parts[0]) - 1
                for depth, paths_parts in enumerate(zip(*paths_by_parts)):
                    if are_same(*paths_parts):
                        pass
                    else:
                        if depth == max_depth:
                            return operator.or_
                        else:
                            break
        return lambda x, y: x.union(y)

    def preupdate_dependent(
        self,
        instance: Union[QuerySet, Model],
        model: Optional[Type[Model]] = None,
        update_fields: Optional[Iterable[str]] = None,
    ) -> Dict[Type[Model], List[Any]]:
        """
        Create a mapping of currently associated computed field records,
        that might turn dirty by a follow-up bulk action.

        Feed the mapping back to ``update_dependent`` as `old` argument
        after your bulk action to update de-associated computed field records as well.
        """
        return self._querysets_for_update(
            model or self._get_model(instance), instance, update_fields, pk_list=True)

    def update_dependent(
        self,
        instance: Union[QuerySet, Model],
        model: Optional[Type[Model]] = None,
        update_fields: Optional[Iterable[str]] = None,
        old: Optional[Dict[Type[Model], List[Any]]] = None,
        update_local: bool = True,
        querysize: Optional[int] = None
    ) -> None:
        """
        Updates all dependent computed fields on related models traversing
        the dependency tree as shown in the graphs.

        This is the main entry hook of the resolver to do updates on dependent
        computed fields during runtime. While this is done automatically for
        model instance actions from signal handlers, you have to call it yourself
        after changes done by bulk actions.

        To do that, simply call this function after the update with the queryset
        containing the changed objects:

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

            Getting pks from ``bulk_create`` is not supported by all database adapters.
            With a local computed field you can "cheat" here by providing a sentinel:

                >>> MyComputedModel.objects.bulk_create([
                ...     MyComputedModel(comp='SENTINEL'), # here or as default field value
                ...     MyComputedModel(comp='SENTINEL'),
                ... ])
                >>> update_dependent(MyComputedModel.objects.filter(comp='SENTINEL'))

            If the sentinel is beyond reach of the method result, this even ensures to update
            only the newly added records.

        `instance` can also be a single model instance. Since calling ``save`` on a model instance
        will trigger this function by the `post_save` signal already it should not be called
        for single instances, if they get saved anyway.

        `update_fields` can be used to indicate, that only certain fields on the queryset changed,
        which helps to further narrow down the records to be updated.

        Special care is needed, if a bulk action contains foreign key changes,
        that are part of a computed field dependency chain. To correctly handle that case,
        provide the result of ``preupdate_dependent`` as `old` argument like this:

                >>> # given: some computed fields model depends somehow on Entry.fk_field
                >>> old_relations = preupdate_dependent(Entry.objects.filter(pub_date__year=2010))
                >>> Entry.objects.filter(pub_date__year=2010).update(fk_field=new_related_obj)
                >>> update_dependent(Entry.objects.filter(pub_date__year=2010), old=old_relations)

        `update_local=False` disables model local computed field updates of the entry node. 
        (used as optimization during tree traversal). You should not disable it yourself.
        """
        _model = model or self._get_model(instance)

        # bulk_updater might change fields, ensure we have set/None
        _update_fields = None if update_fields is None else set(update_fields)

        # Note: update_local is always off for updates triggered from the resolver
        # but True by default to avoid accidentally skipping updates called by user
        if update_local and self.has_computedfields(_model):
            # We skip a transaction here in the same sense,
            # as local cf updates are not guarded either.
            queryset = instance if isinstance(instance, QuerySet) \
                else _model._base_manager.filter(pk__in=[instance.pk])
            self.bulk_updater(queryset, _update_fields, local_only=True, querysize=querysize)

        updates = self._querysets_for_update(_model, instance, _update_fields).values()
        if updates:
            with transaction.atomic():  # FIXME: place transaction only once in tree descent
                pks_updated: Dict[Type[Model], Set[Any]] = {}
                for queryset, fields in updates:
                    _pks = self.bulk_updater(queryset, fields, return_pks=True, querysize=querysize)
                    if _pks:
                        pks_updated[queryset.model] = _pks
                if old:
                    for model2, data in old.items():
                        pks, fields = data
                        queryset = model2.objects.filter(pk__in=pks-pks_updated.get(model2, set()))
                        self.bulk_updater(queryset, fields, querysize=querysize)

    def bulk_updater(
        self,
        queryset: QuerySet,
        update_fields: Optional[Set[str]] = None,
        return_pks: bool = False,
        local_only: bool = False,
        querysize: Optional[int] = None
    ) -> Optional[Set[Any]]:
        """
        Update local computed fields and descent in the dependency tree by calling
        ``update_dependent`` for dependent models.

        This method does the local field updates on `queryset`:

            - eval local `MRO` of computed fields
            - expand `update_fields`
            - apply optional `select_related` and `prefetch_related` rules to `queryset`
            - walk all records and recalculate fields in `update_fields`
            - aggregate changeset and save as batched `bulk_update` to the database

        By default this method triggers the update of dependent models by calling
        ``update_dependent`` with `update_fields` (next level of tree traversal).
        This can be suppressed by setting `local_only=True`.

        If `return_pks` is set, the method returns a set of altered pks of `queryset`.
        """
        model: Type[Model] = queryset.model

        # distinct issue workaround
        # the workaround is needed for already sliced/distinct querysets coming from outside
        # TODO: distinct is a major query perf smell, and is in fact only needed on back relations
        #       may need some rework in _querysets_for_update
        #       ideally we find a way to avoid it for forward relations
        #       also see #101
        if queryset.query.can_filter() and not queryset.query.distinct_fields:
            if queryset.query.combinator != "union":
                queryset = queryset.distinct()
        else:
            queryset = model._base_manager.filter(pk__in=subquery_pk(queryset, queryset.db))

        # correct update_fields by local mro
        mro = self.get_local_mro(model, update_fields)
        fields: Any = set(mro)  # FIXME: narrow type once issue in django-stubs is resolved
        if update_fields:
            update_fields.update(fields)

        select = self.get_select_related(model, fields)
        prefetch = self.get_prefetch_related(model, fields)
        if select:
            queryset = queryset.select_related(*select)
        if prefetch:
            queryset = queryset.prefetch_related(*prefetch)

        pks = []
        if fields:
            q_size = self.get_querysize(model, fields, querysize)
            change: List[Model] = []
            for elem in slice_iterator(queryset, q_size):
                # note on the loop: while it is technically not needed to batch things here,
                # we still prebatch to not cause memory issues for very big querysets
                has_changed = False
                for comp_field in mro:
                    new_value = self._compute(elem, model, comp_field)
                    if new_value != getattr(elem, comp_field):
                        has_changed = True
                        setattr(elem, comp_field, new_value)
                if has_changed:
                    change.append(elem)
                    pks.append(elem.pk)
                if len(change) >= self._batchsize:
                    self._update(model._base_manager.all(), change, fields)
                    change = []
            if change:
                self._update(model._base_manager.all(), change, fields)

        # trigger dependent comp field updates from changed records
        # other than before we exit the update tree early, if we have no changes at all
        # also cuts the update tree for recursive deps (tree-like)
        if not local_only and pks:
            self.update_dependent(model._base_manager.filter(pk__in=pks), model, fields, update_local=False)
        return set(pks) if return_pks else None
    
    def _update(self, queryset: QuerySet, change: Sequence[Any], fields: Sequence[str]) -> Union[int, None]:
        # we can skip batch_size here, as it already was batched in bulk_updater
        if self.use_fastupdate:
            return fast_update(queryset, change, fields, None)
        return queryset.model._base_manager.bulk_update(change, fields)

    def _compute(self, instance: Model, model: Type[Model], fieldname: str) -> Any:
        """
        Returns the computed field value for ``fieldname``.
        Note that this is just a shorthand method for calling the underlying computed
        field method and does not deal with local MRO, thus should only be used,
        if the MRO is respected by other means.
        For quick inspection of a single computed field value, that gonna be written
        to the database, always use ``compute(fieldname)`` instead.
        """
        field = self._computed_models[model][fieldname]
        return field._computed['func'](instance)

    def compute(self, instance: Model, fieldname: str) -> Any:
        """
        Returns the computed field value for ``fieldname``. This method allows
        to inspect the new calculated value, that would be written to the database
        by a following ``save()``.

        Other than calling ``update_computedfields`` on an model instance this call
        is not destructive for old computed field values.
        """
        # Getting a single computed value prehand is quite complicated,
        # as we have to:
        # - resolve local MRO backwards (stored MRO data is optimized for forward deps)
        # - calc all local cfs, that the requested one depends on
        # - stack and rewind interim values, as we dont want to introduce side effects here
        #   (in fact the save/bulker logic might try to save db calls based on changes)
        mro = self.get_local_mro(type(instance), None)
        if not fieldname in mro:
            return getattr(instance, fieldname)
        entries = self._local_mro[type(instance)]['fields']
        pos = 1 << mro.index(fieldname)
        stack: List[Tuple[str, Any]] = []
        model = type(instance)
        for field in mro:
            if field == fieldname:
                ret = self._compute(instance, model, fieldname)
                for field2, old in stack:
                    # reapply old stack values
                    setattr(instance, field2, old)
                return ret
            f_mro = entries.get(field, 0)
            if f_mro & pos:
                # append old value to stack for later rewinding
                # calc and set new value for field, if the requested one depends on it
                stack.append((field, getattr(instance, field)))
                setattr(instance, field, self._compute(instance, model, field))

    # TODO: the following 3 lookups are very expensive at runtime adding ~2s for 1M calls
    #       --> all need pregenerated lookup maps
    # Note: the same goes for get_local_mro and _queryset_for_update...
    def get_select_related(
        self,
        model: Type[Model],
        fields: Optional[Iterable[str]] = None
    ) -> Set[str]:
        """
        Get defined select_related rules for `fields` (all if none given).
        """
        if fields is None:
            fields = self._computed_models[model].keys()
        select: Set[str] = set()
        for field in fields:
            select.update(self._computed_models[model][field]._computed['select_related'])
        return select

    def get_prefetch_related(
        self,
        model: Type[Model],
        fields: Optional[Iterable[str]] = None
    ) -> List:
        """
        Get defined prefetch_related rules for `fields` (all if none given).
        """
        if fields is None:
            fields = self._computed_models[model].keys()
        prefetch: List[Any] = []
        for field in fields:
            prefetch.extend(self._computed_models[model][field]._computed['prefetch_related'])
        return prefetch

    def get_querysize(
        self,
        model: Type[Model],
        fields: Optional[Iterable[str]] = None,
        override: Optional[int] = None
    ) -> int:
        base = settings.COMPUTEDFIELDS_QUERYSIZE if override is None else override
        if fields is None:
            fields = self._computed_models[model].keys()
        return min(self._computed_models[model][f]._computed['querysize'] or base for f in fields)

    def get_contributing_fks(self) -> IFkMap:
        """
        Get a mapping of models and their local foreign key fields,
        that are part of a computed fields dependency chain.

        Whenever a bulk action changes one of the fields listed here, you have to create
        a listing of the associated  records with ``preupdate_dependent`` before doing
        the bulk change. After the bulk change feed the listing back to ``update_dependent``
        with the `old` argument.

        With ``COMPUTEDFIELDS_ADMIN = True`` in `settings.py` this mapping can also be
        inspected as admin view. 
        """
        if not self._map_loaded:  # pragma: no cover
            raise ResolverException('resolver has no maps loaded yet')
        return self._fk_map

    def _sanity_check(self, field: Field, depends: IDepends) -> None:
        """
        Basic type check for computed field arguments `field` and `depends`.
        This only checks for proper type alignment (most crude source of errors) to give
        devs an early startup error for misconfigured computed fields.
        More subtle errors like non-existing paths or fields are caught
        by the resolver during graph reduction yielding somewhat crytic error messages.

        There is another class of misconfigured computed fields we currently cannot
        find by any safety measures - if `depends` provides valid paths and fields,
        but the function operates on different dependencies. Currently it is the devs'
        responsibility to perfectly align `depends` entries with dependencies
        used by the function to avoid faulty update behavior.
        """
        if not isinstance(field, Field):
                raise ResolverException('field argument is not a Field instance')
        for rule in depends:
            try:
                path, fieldnames = rule
            except ValueError:
                raise ResolverException(MALFORMED_DEPENDS)
            if not isinstance(path, str) or not all(isinstance(f, str) for f in fieldnames):
                raise ResolverException(MALFORMED_DEPENDS)

    def computedfield_factory(
        self,
        field: 'Field[_ST, _GT]',
        compute: Callable[..., _ST],
        depends: Optional[IDepends] = None,
        select_related: Optional[Sequence[str]] = None,
        prefetch_related: Optional[Sequence[Any]] = None,
        querysize: Optional[int] = None
    ) -> 'Field[_ST, _GT]':
        """
        Factory for computed fields.

        The method gets exposed as ``ComputedField`` to allow a more declarative
        code style with better separation of field declarations and function
        implementations. It is also used internally for the ``computed`` decorator.
        Similar to the decorator, the ``compute`` function expects a single argument
        as model instance of the model it got applied to.

        Usage example:

        .. code-block:: python

            from computedfields.models import ComputedField

            def calc_mul(inst):
                return inst.a * inst.b

            class MyModel(ComputedFieldsModel):
                a = models.IntegerField()
                b = models.IntegerField()
                sum = ComputedField(
                    models.IntegerField(),
                    depends=[('self', ['a', 'b'])],
                    compute=lambda inst: inst.a + inst.b
                )
                mul = ComputedField(
                    models.IntegerField(),
                    depends=[('self', ['a', 'b'])],
                    compute=calc_mul
                )
        """
        self._sanity_check(field, depends or [])
        cf = cast('IComputedField[_ST, _GT]', field)
        cf._computed = {
            'func': compute,
            'depends': depends or [],
            'select_related': select_related or [],
            'prefetch_related': prefetch_related or [],
            'querysize': querysize
        }
        cf.editable = False
        self.add_field(cf)
        return field

    def computed(
        self,
        field: 'Field[_ST, _GT]',
        depends: Optional[IDepends] = None,
        select_related: Optional[Sequence[str]] = None,
        prefetch_related: Optional[Sequence[Any]] = None,
        querysize: Optional[int] = None
    ) -> Callable[[Callable[..., _ST]], 'Field[_ST, _GT]']:
        """
        Decorator to create computed fields.

        `field` should be a model concrete field instance suitable to hold the result
        of the decorated method. The decorator expects a keyword argument `depends`
        to indicate dependencies to model fields (local or related).
        Listed dependencies will automatically update the computed field.

        Examples:

            - create a char field with no further dependencies (not very useful)

            .. code-block:: python

                @computed(models.CharField(max_length=32))
                def ...

            - create a char field with a dependency to the field ``name`` on a
              foreign key relation ``fk``

            .. code-block:: python

                @computed(models.CharField(max_length=32), depends=[('fk', ['name'])])
                def ...

        Dependencies should be listed as ``['relation_name', concrete_fieldnames]``.
        The relation can span serveral models, simply name the relation
        in python style with a dot (e.g. ``'a.b.c'``). A relation can be any of
        foreign key, m2m, o2o and their back relations. The fieldnames must point to
        concrete fields on the foreign model.

        .. NOTE::

            Dependencies to model local fields should be list with ``'self'`` as relation name.

        With `select_related` and `prefetch_related` you can instruct the dependency resolver
        to apply certain optimizations on the update queryset.

        .. NOTE::

            `select_related` and `prefetch_related` are stacked over computed fields
            of the same model during updates, that are marked for update.
            If your optimizations contain custom attributes (as with `to_attr` of a
            `Prefetch` object), these attributes will only be available on instances
            during updates from the resolver, never on newly constructed instances or
            model instances pulled by other means, unless you applied the same lookups manually.

            To keep the computed field methods working under any circumstances,
            it is a good idea not to rely on lookups with custom attributes,
            or to test explicitly for them in the method with an appropriate plan B.

        .. CAUTION::

            With the dependency resolver you can easily create recursive dependencies
            by accident. Imagine the following:

            .. code-block:: python

                class A(ComputedFieldsModel):
                    @computed(models.CharField(max_length=32), depends=[('b_set', ['comp'])])
                    def comp(self):
                        return ''.join(b.comp for b in self.b_set.all())

                class B(ComputedFieldsModel):
                    a = models.ForeignKey(A)

                    @computed(models.CharField(max_length=32), depends=[('a', ['comp'])])
                    def comp(self):
                        return a.comp

            Neither an object of `A` or `B` can be saved, since the ``comp`` fields depend on
            each other. While it is quite easy to spot for this simple case it might get tricky
            for more complicated dependencies. Therefore the dependency resolver tries
            to detect cyclic dependencies and might raise a ``CycleNodeException`` during
            startup.

            If you experience this in your project try to get in-depth cycle
            information, either by using the ``rendergraph`` management command or
            by directly accessing the graph objects:

            - intermodel dependency graph: ``active_resolver._graph``
            - mode local dependency graphs: ``active_resolver._graph.modelgraphs[your_model]``
            - union graph: ``active_resolver._graph.get_uniongraph()``

            Note that there is not graph object, when running with ``COMPUTEDFIELDS_MAP = True``.
            In that case either comment out that line `settings.py` and restart the server
            or build the graph at runtime with:

                >>> from computedfields.graph import ComputedModelsGraph
                >>> from computedfields.resolver import active_resolver
                >>> graph = ComputedModelsGraph(active_resolver.computed_models)

            Also see the graph documentation :ref:`here<graph>`.
        """
        def wrap(func: Callable[..., _ST]) -> 'Field[_ST, _GT]':
            return self.computedfield_factory(
                field,
                compute=func,
                depends=depends,
                select_related=select_related,
                prefetch_related=prefetch_related,
                querysize=querysize
            )
        return wrap

    @overload
    def precomputed(self, f: F) -> F:
        ...
    @overload
    def precomputed(self, skip_after: bool) -> Callable[[F], F]:
        ...
    def precomputed(self, *dargs, **dkwargs) -> Union[F, Callable[[F], F]]:
        """
        Decorator for custom ``save`` methods, that expect local computed fields
        to contain already updated values on enter.

        By default local computed field values are only calculated once by the
        ``ComputedFieldModel.save`` method after your own save method.

        By placing this decorator on your save method, the values will be updated
        before entering your method as well. Note that this comes for the price of
        doubled local computed field calculations (before and after your save method).
        
        To avoid a second recalculation, the decorator can be called with `skip_after=True`.
        Note that this might lead to desychronized computed field values, if you do late
        field changes in your save method without another resync afterwards.
        """
        skip: bool = False
        func: Optional[F] = None
        if dargs:
            if len(dargs) > 1 or not callable(dargs[0]) or dkwargs:
                raise ResolverException('error in @precomputed declaration')
            func = dargs[0]
        else:
            skip = dkwargs.get('skip_after', False)
        
        def wrap(func: F) -> F:
            def _save(instance, *args, **kwargs):
                new_fields = self.update_computedfields(instance, kwargs.get('update_fields'))
                if new_fields:
                    kwargs['update_fields'] = new_fields
                kwargs['skip_computedfields'] = skip
                return func(instance, *args, **kwargs)
            return cast(F, _save)
        
        return wrap(func) if func else wrap

    def update_computedfields(
        self,
        instance: Model,
        update_fields: Optional[Iterable[str]] = None
        ) -> Optional[Iterable[str]]:
        """
        Update values of local computed fields of `instance`.

        Other than calling ``compute`` on an instance, this call overwrites
        computed field values on the instance (destructive).

        Returns ``None`` or an updated set of field names for `update_fields`.
        The returned fields might contained additional computed fields, that also
        changed based on the input fields, thus should extend `update_fields`
        on a save call.
        """
        model = type(instance)
        if not self.has_computedfields(model):
            return update_fields
        cf_mro = self.get_local_mro(model, update_fields)
        if update_fields:
            update_fields = set(update_fields)
            update_fields.update(set(cf_mro))
        for fieldname in cf_mro:
            setattr(instance, fieldname, self._compute(instance, model, fieldname))
        if update_fields:
            return update_fields
        return None

    def has_computedfields(self, model: Type[Model]) -> bool:
        """
        Indicate whether `model` has computed fields.
        """
        return model in self._computed_models

    def get_computedfields(self, model: Type[Model]) -> Iterable[str]:
        """
        Get all computed fields on `model`.
        """
        return self._computed_models.get(model, {}).keys()

    def is_computedfield(self, model: Type[Model], fieldname: str) -> bool:
        """
        Indicate whether `fieldname` on `model` is a computed field.
        """
        return fieldname in self.get_computedfields(model)

    def get_graphs(self) -> Tuple[Graph, Dict[Type[Model], ModelGraph], Graph]:
        """
        Return a tuple of all graphs as
        ``(intermodel_graph, {model: modelgraph, ...}, union_graph)``.
        """
        graph = self._graph
        if not graph:
            graph = ComputedModelsGraph(active_resolver.computed_models)
            graph.get_edgepaths()
            graph.get_uniongraph()
        return (graph, graph.modelgraphs, graph.get_uniongraph())


# active_resolver is currently treated as global singleton (used in imports)
#: Currently active resolver.
active_resolver = Resolver()

# BOOT_RESOLVER: resolver that holds all startup declarations and resolve maps
# gets deactivated after startup, thus it is currently not possible to define
# new computed fields and add their resolve rules at runtime
# TODO: investigate on custom resolvers at runtime to be bootstrapped from BOOT_RESOLVER
#: Resolver used during django bootstrapping.
#: This is currently the same as `active_resolver` (treated as global singleton).
BOOT_RESOLVER = active_resolver


# placeholder class to test for correct model inheritance
# during initial field resolving
class _ComputedFieldsModelBase:
    pass
