"""
Module containing the graph logic for the dependency resolver.

Upon application initialization a dependency graph of all project wide
computed fields is created. The graph does a basic cycle check and
removes redundant dependencies. Finally the dependencies are translated
to the resolver map to be used later by ``update_dependent`` and in
the signal handlers.
"""
from collections import OrderedDict
from os import PathLike
from django.core.exceptions import FieldDoesNotExist
from django.db.models import ForeignKey
from computedfields.helper import pairwise, modelname, parent_to_inherited_path, skip_equal_segments

# typing imports
from typing import (Callable, Dict, FrozenSet, Generic, Hashable, Any, List, Optional, Sequence,
                    Set, Tuple, TypeVar, Type, Union)
from typing_extensions import TypedDict
from django.db.models import Model, Field


_ST = TypeVar("_ST", contravariant=True)
_GT = TypeVar("_GT", covariant=True)
F = TypeVar('F', bound=Callable[..., Any])


# depends interface
IDepends = Sequence[Tuple[str, Sequence[str]]]
IDependsAppend = List[Tuple[str, Sequence[str]]]

# _computed container
class IComputedData(TypedDict):
    depends: IDepends
    func: Callable[[Model], Any]
    select_related: Sequence[str]
    prefetch_related: Sequence[Any]
    querysize: Optional[int]


# django Field type extended by our _computed data attribute
class IComputedField(Field, Generic[_ST, _GT]):
    _computed: IComputedData
    creation_counter: int


class ICycleData(TypedDict):
    entries: Set['Edge']
    path: List['Edge']


class IDependsData(TypedDict):
    path: str
    depends: str


class ILocalMroData(TypedDict):
    base: List[str]
    fields: Dict[str, int]


# global deps: {cfModel: {cfname: {srcModel: {'path': lookup_path, 'depends': src_fieldname}}}}
IGlobalDeps = Dict[Type[Model], Dict[str, Dict[Type[Model], List[IDependsData]]]]
# local deps: {Model: {'cfname': {'depends', 'on', 'these', 'local', 'fieldnames'}}}
ILocalDeps = Dict[Type[Model], Dict[str, Set[str]]]
# cleaned: {(cfmodel, cfname): {(srcmodel, fname), ...}}
IGlobalDepsCleaned = Dict[Tuple[str, str], Set[Tuple[str, str]]]
IInterimTable = Dict[Type[Model], Dict[str, Dict[Type[Model], Dict[str, List[IDependsData]]]]]

# maps exported to resolver
# LookupMap: {srcModel: {srcfield: {cfModel, ({querystrings}, {cfields})}}}
ILookupMap = Dict[Type[Model], Dict[str, Dict[Type[Model], Tuple[Set[str], Set[str]]]]]
# fk map: {Model: {fkname, ...}}
IFkMap = Dict[Type[Model], Set[str]]
# local MRO: {Model: {'base': [mro of all fields], 'fields': {fname: bitarray into base}}}
ILocalMroMap = Dict[Type[Model], ILocalMroData]


class IResolvedDeps(TypedDict):
    globalDeps: IGlobalDeps
    localDeps: ILocalDeps


class ComputedFieldsException(Exception):
    """
    Base exception raised from computed fields.
    """


class CycleException(ComputedFieldsException):
    """
    Exception raised during path linearization, if a cycle was found.
    Contains the found cycle either as list of edges or nodes in
    ``args``.
    """


class CycleEdgeException(CycleException):
    """
    Exception raised during path linearization, if a cycle was found.
    Contains the found cycle as list of edges in ``args``.
    """


class CycleNodeException(CycleException):
    """
    Exception raised during path linearization, if a cycle was found.
    Contains the found cycle as list of nodes in ``args``.
    """


class Edge:
    """
    Class for representing an edge in ``Graph``.
    The instances are created as singletons,
    calling ``Edge('A', 'B')`` multiple times
    will always point to the same object.
    """
    instances: Dict[Hashable, 'Edge'] = {}

    def __new__(cls, *args):
        key: Tuple['Node', 'Node'] = (args[0], args[1])
        if key in cls.instances:
            return cls.instances[key]
        instance = super(Edge, cls).__new__(cls)
        cls.instances[key] = instance
        return instance

    def __init__(self, left: 'Node', right: 'Node', data: Optional[Any] = None):
        self.left = left
        self.right = right
        self.data = data

    def __str__(self) -> str:
        return f'Edge {self.left}-{self.right}'

    def __repr__(self) -> str:
        return str(self)

    def __eq__(self, other) -> bool:
        return self is other

    def __ne__(self, other) -> bool:
        return self is not other

    def __hash__(self) -> int:
        return id(self)


class Node:
    """
    Class for representing a node in ``Graph``.
    The instances are created as singletons,
    calling ``Node('A')`` multiple times will
    always point to the same object.
    """
    instances: Dict[Hashable, 'Node'] = {}

    def __new__(cls, *args):
        if args[0] in cls.instances:
            return cls.instances[args[0]]
        instance = super(Node, cls).__new__(cls)
        cls.instances[args[0]] = instance
        return instance

    def __init__(self, data: Any):
        self.data = data

    def __str__(self) -> str:
        return self.data if isinstance(self.data, str) else '.'.join(self.data)

    def __repr__(self) -> str:
        return str(self)

    def __eq__(self, other) -> bool:
        return self is other

    def __ne__(self, other) -> bool:
        return self is not other

    def __hash__(self) -> int:
        return id(self)


class Graph:
    """
    .. _graph:

    Simple directed graph implementation.
    """

    def __init__(self):
        self.nodes: Set[Node] = set()
        self.edges: Set[Edge] = set()
        self._removed: Set[Edge] = set()

    def add_node(self, node: Node) -> None:
        """Add a node to the graph."""
        self.nodes.add(node)

    def remove_node(self, node: Node) -> None:
        """
        Remove a node from the graph.

        .. WARNING::
            Removing edges containing the removed node
            is not implemented.
        """
        self.nodes.remove(node)

    def add_edge(self, edge: Edge) -> None:
        """
        Add an edge to the graph.
        Automatically inserts the associated nodes.
        """
        self.edges.add(edge)
        self.nodes.add(edge.left)
        self.nodes.add(edge.right)

    def remove_edge(self, edge: Edge) -> None:
        """
        Removes an edge from the graph.

        .. WARNING::
            Does not remove leftover contained nodes.
        """
        self.edges.remove(edge)

    def get_dot(
            self,
            format: str = 'pdf',
            mark_edges: Optional[Dict[Edge, Dict[str, Any]]] = None,
            mark_nodes: Optional[Dict[Node, Dict[str, Any]]] = None
    ):
        """
        Returns the graphviz object of the graph
        (needs the :mod:`graphviz` package).
        """
        from graphviz import Digraph
        if not mark_edges:
            mark_edges = {}
        if not mark_nodes:
            mark_nodes = {}
        dot = Digraph(format=format)
        for node in self.nodes:
            dot.node(str(node), str(node), **mark_nodes.get(node, {}))
        for edge in self.edges:
            dot.edge(str(edge.left), str(edge.right), **mark_edges.get(edge, {}))
        return dot

    def render(
            self,
            filename: Optional[Union[PathLike, str]] = None,
            format: str = 'pdf',
            mark_edges: Optional[Dict[Edge, Dict[str, Any]]] = None,
            mark_nodes: Optional[Dict[Node, Dict[str, Any]]] = None
    ) -> None:
        """
        Renders the graph to file (needs the :mod:`graphviz` package).
        """
        self.get_dot(format, mark_edges, mark_nodes).render(
            filename=filename, cleanup=True)

    def view(
            self,
            format: str = 'pdf',
            mark_edges: Optional[Dict[Edge, Dict[str, Any]]] = None,
            mark_nodes: Optional[Dict[Node, Dict[str, Any]]] = None
    ) -> None:
        """
        Directly opens the graph in the associated desktop viewer
        (needs the :mod:`graphviz` package).
        """
        self.get_dot(format, mark_edges, mark_nodes).view(cleanup=True)

    @staticmethod
    def edgepath_to_nodepath(path: Sequence[Edge]) -> List[Node]:
        """
        Converts a list of edges to a list of nodes.
        """
        return [edge.left for edge in path] + [path[-1].right]

    @staticmethod
    def nodepath_to_edgepath(path: Sequence[Node]) -> List[Edge]:
        """
        Converts a list of nodes to a list of edges.
        """
        return [Edge(*pair) for pair in pairwise(path)]

    def _get_edge_paths(
            self,
            edge: Edge,
            left_edges: Dict[Node, List[Edge]],
            paths: List[List[Edge]],
            seen: Optional[List[Edge]] = None
    ) -> None:
        """
        Walks the graph recursively to get all possible paths.
        Might raise a ``CycleEdgeException``.
        """
        if not seen:
            seen = []
        if edge in seen:
            raise CycleEdgeException(seen[seen.index(edge):])
        seen.append(edge)
        if edge.right in left_edges:
            for new_edge in left_edges[edge.right]:
                self._get_edge_paths(new_edge, left_edges, paths, seen[:])
        paths.append(seen)

    def get_edgepaths(self) -> List[List[Edge]]:
        """
        Returns a list of all edge paths.
        An edge path is represented as list of edges.

        Might raise a ``CycleEdgeException``. For in-depth cycle detection
        use ``edge_cycles``, `node_cycles`` or ``get_cycles()``.
        """
        left_edges: Dict[Node, List[Edge]] = OrderedDict()
        paths: List[List[Edge]] = []
        for edge in self.edges:
            left_edges.setdefault(edge.left, []).append(edge)
        for edge in self.edges:
            self._get_edge_paths(edge, left_edges, paths)
        return paths

    def get_nodepaths(self) -> List[List[Node]]:
        """
        Returns a list of all node paths.
        A node path is represented as list of nodes.

        Might raise a ``CycleNodeException``. For in-depth cycle detection
        use ``edge_cycles``, ``node_cycles`` or ``get_cycles()``.
        """
        try:
            paths: List[List[Edge]] = self.get_edgepaths()
        except CycleEdgeException as exc:
            raise CycleNodeException(self.edgepath_to_nodepath(exc.args[0]))
        node_paths: List[List[Node]] = []
        for path in paths:
            node_paths.append(self.edgepath_to_nodepath(path))
        return node_paths

    def _get_cycles(
            self,
            edge: Edge,
            left_edges: Dict[Node, List[Edge]],
            cycles: Dict[FrozenSet[Edge], ICycleData],
            seen: Optional[List[Edge]] = None
    ) -> None:
        """
        Walks the graph to collect all cycles.
        """
        if not seen:
            seen = []
        if edge in seen:
            cycle: FrozenSet[Edge] = frozenset(seen[seen.index(edge):])
            data: ICycleData = cycles.setdefault(cycle, {'entries': set(), 'path': []})
            if seen:
                data['entries'].add(seen[0])
            data['path'] = seen[seen.index(edge):]
            return
        seen.append(edge)
        if edge.right in left_edges:
            for new_edge in left_edges[edge.right]:
                self._get_cycles(new_edge, left_edges, cycles, seen[:])

    def get_cycles(self) -> Dict[FrozenSet[Edge], ICycleData]:
        """
        Gets all cycles in graph.

        This is not optimised by any means, it simply walks the whole graph
        recursively and aborts as soon a seen edge gets entered again.
        Therefore use this and all dependent properties
        (``edge_cycles`` and ``node_cycles``) for in-depth cycle inspection
        only.

        As a start node any node on the left side of an edge will be tested.

        Returns a mapping of

        .. code:: python

            {frozenset(<cycle edges>): {
                'entries': set(edges leading to the cycle),
                'path': list(cycle edges in last seen order)
            }}

        An edge in ``entries`` is not necessarily part of the cycle itself,
        but once entered it will lead to the cycle.
        """
        left_edges: Dict[Node, List[Edge]] = OrderedDict()
        cycles: Dict[FrozenSet[Edge], ICycleData] = {}
        for edge in self.edges:
            left_edges.setdefault(edge.left, []).append(edge)
        for edge in self.edges:
            self._get_cycles(edge, left_edges, cycles)
        return cycles

    @property
    def edge_cycles(self) -> List[List[Edge]]:
        """
        Returns all cycles as list of edge lists.
        Use this only for in-depth cycle inspection.
        """
        return [cycle['path'] for cycle in self.get_cycles().values()]

    @property
    def node_cycles(self) -> List[List[Node]]:
        """
        Returns all cycles as list of node lists.
        Use this only for in-depth cycle inspection.
        """
        return [self.edgepath_to_nodepath(cycle['path'])
                for cycle in self.get_cycles().values()]

    @property
    def is_cyclefree(self) -> bool:
        """
        True if the graph contains no cycles.

        For faster calculation this property relies on
        path linearization instead of the more expensive
        full cycle detection. For in-depth cycle inspection
        use ``edge_cycles`` or ``node_cycles`` instead.
        """
        try:
            self.get_edgepaths()
            return True
        except CycleEdgeException:
            return False


class ComputedModelsGraph(Graph):
    """
    Class to convert the computed fields dependency strings into
    a graph and generate the final resolver functions.

    Steps taken:

    - ``resolve_dependencies`` resolves the depends field strings
      to real model fields.
    - The dependencies are rearranged to adjacency lists for
      the underlying graph.
    - The graph does a cycle check and removes redundant edges
      to lower the database penalty.
    - In ``generate_lookup_map`` the path segments of remaining edges
      are collected into the final lookup map.
    """

    def __init__(self, computed_models: Dict[Type[Model], Dict[str, IComputedField]]):
        """
        ``computed_models`` is ``Resolver.computed_models``.
        """
        super(ComputedModelsGraph, self).__init__()
        self._computed_models: Dict[Type[Model], Dict[str, IComputedField]] = computed_models
        self.models: Dict[str, Type[Model]] = {}
        self.resolved: IResolvedDeps = self.resolve_dependencies(computed_models)
        self.cleaned_data: IGlobalDepsCleaned = self._clean_data(self.resolved['globalDeps'])
        self._insert_data(self.cleaned_data)
        self.modelgraphs: Dict[Type[Model], ModelGraph] = {}
        self.union: Optional[Graph] = None

    def _right_constrain(self, model: Type[Model], fieldname: str) -> None:
        """
        Sanity check for right side field types.

        On the right side of a `depends` rule only real database fields should occur,
        that are fieldnames that can safely be used with `update_fields` in ``save``.
        This includes any concrete fields (also computed fields itself), but not m2m fields.
        """
        f = model._meta.get_field(fieldname)
        if not f.concrete or f.many_to_many:
            raise ComputedFieldsException(f"{model} has no concrete field named '{fieldname}'")

    def resolve_dependencies(
        self,
        computed_models: Dict[Type[Model], Dict[str, IComputedField]]
    ) -> IResolvedDeps:
        """
        Converts `depends` rules into ORM lookups and checks the source fields' existance.

        Basic `depends` rules:
        - left side may contain any relation path accessible from an instance as ``'a.b.c'``
        - right side may contain real database source fields (never relations)

        Deeper nested relations get automatically added to the resolver map:

        - fk relations are added on the model holding the fk field
        - reverse fk relations are added on related model holding the fk field
        - m2m fields and backrelations are added on the model directly, but
          only used for inter-model resolving, never for field lookups during ``save``
        """
        global_deps: IGlobalDeps = OrderedDict()
        local_deps: ILocalDeps = {}
        for model, fields in computed_models.items():
            # skip proxy models for graph handling,
            # deps get patched at runtime from resolved real models
            if model._meta.proxy:
                continue
            local_deps.setdefault(model, {})  # always add to local to get a result for MRO
            for field, real_field in fields.items():
                fieldentry = global_deps.setdefault(model, {}).setdefault(field, {})
                local_deps.setdefault(model, {}).setdefault(field, set())

                depends: IDepends = real_field._computed['depends']

                # fields contributed from multi table model inheritance need patched depends rules,
                # so the relation paths match the changed model entrypoint
                if real_field.model != model and not real_field.model._meta.abstract:
                    # path from original model to current inherited
                    # these path segments have to be removed from depends
                    remove_segments = parent_to_inherited_path(real_field.model, model)
                    if not remove_segments:
                        raise ComputedFieldsException(f'field {real_field} cannot be mapped on model {model}')

                    # paths starting with these segments belong to other derived models
                    # and get skipped for the dep tree creation on the current model
                    # allows depending on fields of derived models in a computed field on the parent model
                    # ("up-pulling", make sure your method handles the attribute access correctly)
                    skip_paths: List[str] = []
                    for rel1 in real_field.model._meta.related_objects:
                        if rel1.name != remove_segments[0]:
                            skip_paths.append(rel1.name)

                    # do a full rewrite of depends entry
                    depends_overwrite: IDependsAppend = []
                    for path, fieldnames in depends:
                        ps = path.split('.')
                        if ps[0] in skip_paths:
                            continue
                        path = '.'.join(skip_equal_segments(ps, remove_segments)) or 'self'
                        depends_overwrite.append((path, fieldnames[:]))
                    depends = depends_overwrite

                for path, fieldnames in depends:
                    if path == 'self':
                        # skip selfdeps in global graph handling
                        # we handle it instead on model graph level
                        # do at least an existance check here to provide an early error
                        for fieldname in fieldnames:
                            self._right_constrain(model, fieldname)
                        local_deps.setdefault(model, {}).setdefault(field, set()).update(fieldnames)
                        continue
                    path_segments: List[str] = []
                    cls: Type[Model] = model
                    for symbol in path.split('.'):
                        try:
                            rel: Any = cls._meta.get_field(symbol)
                            if rel.many_to_many:
                                # add dependency to m2m relation fields
                                path_segments.append(symbol)
                                fieldentry.setdefault(rel.related_model, []).append(
                                    {'path': '__'.join(path_segments), 'depends': rel.remote_field.name})
                                path_segments.pop()
                        except FieldDoesNotExist:
                            # handle reverse relation (not a concrete field)
                            descriptor = getattr(cls, symbol)
                            rel = getattr(descriptor, 'rel', None) or getattr(descriptor, 'related')
                            symbol = rel.field.related_query_name()
                            # add dependency to reverse relation field as well
                            # this needs to be added in opposite direction on related model
                            path_segments.append(symbol)
                            fieldentry.setdefault(rel.related_model, []).append(
                                {'path': '__'.join(path_segments), 'depends': rel.field.name})
                            path_segments.pop()
                        # add path segment to self deps if we have an fk field on a CFM
                        # this is needed to correctly propagate direct fk changes
                        # in local cf mro later on
                        if isinstance(rel, ForeignKey) and cls in computed_models:
                            self._right_constrain(cls, symbol)
                            local_deps.setdefault(cls, {}).setdefault(field, set()).add(symbol)
                        if path_segments:
                            # add segment to intermodel graph deps
                            fieldentry.setdefault(cls, []).append(
                                {'path': '__'.join(path_segments), 'depends': symbol})
                        path_segments.append(symbol)
                        cls = rel.related_model
                    for target_field in fieldnames:
                        self._right_constrain(cls, target_field)
                        fieldentry.setdefault(cls, []).append(
                            {'path': '__'.join(path_segments), 'depends': target_field})
        return {'globalDeps': global_deps, 'localDeps': local_deps}

    def _clean_data(self, data: IGlobalDeps) -> IGlobalDepsCleaned:
        """
        Converts the global dependency data into an adjacency list tree
        to be used with the underlying graph.
        """
        cleaned: IGlobalDepsCleaned = OrderedDict()
        for model, fielddata in data.items():
            self.models[modelname(model)] = model
            for field, modeldata in fielddata.items():
                for depmodel, relations in modeldata.items():
                    self.models[modelname(depmodel)] = depmodel
                    for dep in relations:
                        key = (modelname(depmodel), dep['depends'])
                        value = (modelname(model), field)
                        cleaned.setdefault(key, set()).add(value)
        return cleaned

    def _insert_data(self, data: IGlobalDepsCleaned) -> None:
        """
        Adds edges in ``data`` to the graph.
        Data must be an adjacency mapping like
        ``{left: set(right neighbours)}``.
        """
        for left, value in data.items():
            for right in value:
                edge = Edge(Node(left), Node(right))
                self.add_edge(edge)

    def _get_fk_fields(self, model: Type[Model], paths: Set[str]) -> Set[str]:
        """
        Reduce field name dependencies in paths to reverse real local fk fields.
        """
        candidates = set(el.split('__')[-1] for el in paths)
        result: Set[str] = set()
        for field in model._meta.get_fields():
            if isinstance(field, ForeignKey) and field.related_query_name() in candidates:
                result.add(field.name)
        return result

    def _resolve(self, data: Dict[str, List[IDependsData]]) -> Tuple[Set[str], Set[str]]:
        """
        Helper to merge querystring paths for lookup map.
        """
        fields: Set[str] = set()
        strings: Set[str] = set()
        for field, dependencies in data.items():
            fields.add(field)
            for dep in dependencies:
                strings.add(dep['path'])
        return fields, strings

    def generate_maps(self) -> Tuple[ILookupMap, IFkMap]:
        """
        Generates the final lookup map and the fk map.

        Schematically the lookup map is a reversed adjacency list of every source model
        with its fields mapping to the target models with computed fields it would
        update through a certain filter string::

            src_model:[src_field, ...] --> target_model:[(cf_field, filter_string), ...]

        During runtime ``update_dependent`` will use the the information to create
        select querysets on the target_models (roughly):

        .. code:: python

            qs = target_model._base_manager.filter(filter_string=src_model.instance)
            qs |= target_model._base_manager.filter(filter_string2=src_model.instance)
            ...
            bulk_updater(qs, cf_fields)

        The fk map list all models with fk fieldnames, that contribute to computed fields.

        Returns a tuple of (lookup_map, fk_map).
        """
        # apply full node information to graph edges
        table: IInterimTable = {}
        for edge in self.edges:
            lmodel, lfield = edge.left.data
            lmodel = self.models[lmodel]
            rmodel, rfield = edge.right.data
            rmodel = self.models[rmodel]
            table.setdefault(lmodel, {}) \
                .setdefault(lfield, {}) \
                .setdefault(rmodel, {}) \
                .setdefault(rfield, []) \
                .extend(self.resolved['globalDeps'][rmodel][rfield][lmodel])

        # build lookup and path map
        lookup_map: ILookupMap = {}
        path_map: Dict[Type[Model], Set[str]] = {}
        for lmodel, data in table.items():
            for lfield, ldata in data.items():
                for rmodel, rdata in ldata.items():
                    fields, strings = self._resolve(rdata)
                    lookup_map.setdefault(lmodel, {}) \
                        .setdefault(lfield, {})[rmodel] = (fields, strings)
                    path_map.setdefault(lmodel, set()).update(strings)

        # translate paths to model local fields and filter for fk fields
        fk_map: IFkMap = {}
        for model, paths in path_map.items():
            value = self._get_fk_fields(model, paths)
            if value:
                fk_map[model] = value

        return lookup_map, fk_map

    def prepare_modelgraphs(self) -> None:
        """
        Helper to initialize model local subgraphs.
        """
        if self.modelgraphs:
            return
        data = self.resolved['localDeps']
        for model, local_deps in data.items():
            model_graph = ModelGraph(model, local_deps, self._computed_models[model])
            model_graph.transitive_reduction()  # modelgraph always must be cyclefree
            self.modelgraphs[model] = model_graph

    def generate_local_mro_map(self) -> ILocalMroMap:
        """
        Generate model local computed fields mro maps.
        Returns a mapping of models with local computed fields dependencies and their
        `mro`, example:

        .. code:: python

            {
                modelX: {
                    'base': ['c1', 'c2', 'c3'],
                    'fields': {
                        'name': ['c2', 'c3'],
                        'c2': ['c2', 'c3']
                    }
                }
            }

        In the example `modelX` would have 3 computed fields, where `c2` somehow depends on
        the field `name`. `c3` itself depends on changes to `c2`, thus a change to `name` should
        run `c2` and `c3` in that specific order.

        `base` lists all computed fields in topological execution order (mro).
        It is also used at runtime to cover a full update of an instance (``update_fields=None``).

        .. NOTE::
            Note that the actual values in `fields` are bitarrays to index positions of `base`,
            which allows quick field update merges at runtime by doing binary OR on the bitarrays.
        """
        self.prepare_modelgraphs()
        return dict(
            (model, g.generate_local_mapping(g.generate_field_paths(g.get_topological_paths())))
            for model, g in self.modelgraphs.items()
        )

    def get_uniongraph(self) -> Graph:
        """
        Build a union graph of intermodel dependencies and model local dependencies.
        This graph represents the final update cascades triggered by certain field updates.
        The union graph is needed to spot cycles introduced by model local dependencies,
        that otherwise might went unnoticed, example:

        - global dep graph (acyclic):  ``A.comp --> B.comp, B.comp2 --> A.comp``
        - modelgraph of B  (acyclic):  ``B.comp --> B.comp2``

        Here the resulting union graph is not a DAG anymore, since both subgraphs short-circuit
        to a cycle of ``A.comp --> B.comp --> B.comp2 --> A.comp``.
        """
        if not self.union:
            graph = Graph()
            # copy intermodel edges
            for edge in self.edges:
                graph.add_edge(edge)
            # copy modelgraph edges
            self.prepare_modelgraphs()
            for model, modelgraph in self.modelgraphs.items():
                name = modelname(model)
                for edge in modelgraph.edges:
                    graph.add_edge(Edge(
                        Node((name, edge.left.data)),
                        Node((name, edge.right.data))
                    ))
            self.union = graph
        return self.union


class ModelGraph(Graph):
    """
    Graph to resolve model local computed field dependencies in right calculation order.
    """

    def __init__(
            self,
            model: Type[Model],
            local_dependencies: Dict[str, Set[str]],
            computed_fields: Dict[str, IComputedField]
    ):
        super(ModelGraph, self).__init__()
        self.model = model

        # add all edges from extracted local deps
        for right, deps in local_dependencies.items():
            for left in deps:
                self.add_edge(Edge(Node(left), Node(right)))

        # add ## node as update_fields=None placeholder with edges to all computed fields
        # --> None explicitly updates all computed fields
        # Note: this has to be on all cfs to not skip a non local dependent one by accident
        left_all = Node('##')
        for computed in computed_fields:
            self.add_edge(Edge(left_all, Node(computed)))

    def transitive_reduction(self) -> None:
        """
        Remove redundant single edges. Also checks for cycles.
        *Note:* Other than intermodel dependencies local dependencies must always be cyclefree.
        """
        paths: List[List[Edge]] = self.get_edgepaths()
        remove: Set[Edge] = set()
        for path1 in paths:
            # we only cut single edge paths
            if len(path1) > 1:
                continue
            left: Node = path1[0].left
            right: Node = path1[-1].right
            for path2 in paths:
                if path2 == path1:
                    continue
                if right == path2[-1].right and left == path2[0].left:
                    remove.add(path1[0])
        for edge in remove:
            self.remove_edge(edge)

    def _tsort(
            self,
            graph: Dict[Node, List[Node]],
            start: Node,
            paths: Dict[Node, List[Node]],
            path: List[Node]
    ):
        """
        Recursive deep first search variant of topsort.
        Also accumulates any revealed subpaths.
        """
        for node in graph.get(start, []):
            if not node in paths:
                # accumulate revealed topological subpaths
                paths[node] = self._tsort(graph, node, paths, [])
            for snode in paths[node]:
                # append node if its not yet part of the path
                if not snode in path:
                    path += [snode]
        path += [start]
        return path

    def get_topological_paths(self) -> Dict[Node, List[Node]]:
        """
        Creates a map of all possible entry nodes and their topological update path
        (computed fields mro).
        """
        # create simplified parent-child relation graph
        graph: Dict[Node, List[Node]] = {}
        for edge in self.edges:
            graph.setdefault(edge.left, []).append(edge.right)
        topological_paths: Dict[Node, List[Node]] = {}

        # '##' has connections to all cfs thus creates the basic deps order map containing all cfs
        # it also creates all tpaths between cfs itself
        topological_paths[Node('##')] = self._tsort(graph, Node('##'), topological_paths, [])[:-1]

        # we still need to reveal concrete field deps
        # other than for cfs we also strip last entry (the field itself)
        for node in graph:
            if node in topological_paths:
                continue
            topological_paths[node] = self._tsort(graph, node, topological_paths, [])[:-1]

        # reverse all tpaths
        for entry, path in topological_paths.items():
            topological_paths[entry] = path[::-1]

        return topological_paths

    def generate_field_paths(self, tpaths: Dict[Node, List[Node]]) -> Dict[str, List[str]]:
        """
        Convert topological path node mapping into a mapping containing the fieldnames.
        """
        field_paths: Dict[str, List[str]] = {}
        for node, path in tpaths.items():
            field_paths[node.data] = [el.data for el in path]
        return field_paths

    def generate_local_mapping(self, field_paths: Dict[str, List[str]]) -> ILocalMroData:
        """
        Generates the final model local update table to be used during ``ComputedFieldsModel.save``.
        Output is a mapping of local fields, that also update local computed fields, to a bitarray
        containing the computed fields mro, and the base topologcial order for a full update.
        """
        # transfer final data to bitarray
        # bitarray: bit index is realisation of one valid full topsort order held in '##'
        # since this order was build from full graph it always reflects the correct mro
        # even for a subset of fields in update_fields later on
        # properties:
        #   - length is number of computed fields on model
        #   - True indicates execution of associated function at position in topological order
        #   - bitarray is int, field update rules can be added by bitwise OR at save time
        # example:
        #   - edges: [name, c_a], [c_a, c_b], [c_c, c_b], [z, c_c]
        #   - topological order of cfs: {1: c_a, 2: c_c, 4: c_b}
        #   - field deps:   name  : c_a, c_b    --> 0b101
        #                   c_a   : c_a, c_b    --> 0b101
        #                   c_c   : c_c, c_b    --> 0b110
        #                   z     : c_c, c_b    --> 0b110
        #   - update mro:   [name, z]   --> 0b101 | 0b110 --> [c_a, c_c, c_b]
        #                   [c_a, c_b]  --> 0b101 | 0b110 --> [c_a, c_c, c_b]
        binary: Dict[str, int] = {}
        base = field_paths['##']
        for field, deps in field_paths.items():
            if field == '##':
                continue
            binary[field] = 0
            for pos, name in enumerate(base):
                binary[field] |= (1 if name in deps else 0) << pos
        return {'base': base, 'fields': binary}
