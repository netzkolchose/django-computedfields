from collections import OrderedDict
from django.core.exceptions import FieldDoesNotExist
from computedfields.pathresolver import PathResolver
from computedfields.helper import pairwise, is_sublist, reltype, modelname, is_computed_field


class CycleException(Exception):
    """
    Exception raised during path linearization, if a cycle was found.
    Contains the cycle either as edge path or node path in
    ``message``.
    """
    pass


class CycleEdgeException(CycleException):
    """
    Exception raised during path linearization, if a cycle was found.
    Contains the cycle as edge path in ``message``.
    """
    pass


class CycleNodeException(CycleException):
    """
    Exception raised during path linearization, if a cycle was found.
    Contains the cycle as node path in ``message``.
    """
    pass


class Edge(object):
    """
    Class for representing an edge in ``Graph``.
    The instances are created as singletons,
    calling ``Edge('A', 'B')`` multiple times
    will point to the same object.
    """
    instances = {}

    def __new__(cls, *args, **kwargs):
        key = (args[0], args[1])
        if key in cls.instances:
            return cls.instances[key]
        instance = super(Edge, cls).__new__(cls, *args, **kwargs)
        cls.instances[key] = instance
        return instance

    def __init__(self, left, right, data=None):
        self.left = left
        self.right = right
        self.data = data

    def __str__(self):
        return 'Edge %s-%s' % (self.left, self.right)

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return self is not other


class Node(object):
    """
    Class for representing a node in ``Graph``.
    The instances are created as singletons,
    calling ``Node('A')`` multiple times will
    point to the same object.
    """
    instances = {}

    def __new__(cls, *args, **kwargs):
        if args[0] in cls.instances:
            return cls.instances[args[0]]
        instance = super(Node, cls).__new__(cls, *args, **kwargs)
        cls.instances[args[0]] = instance
        return instance

    def __init__(self, data):
        self.data = data

    def __str__(self):
        return '.'.join(self.data)

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return self is not other


class Graph(object):
    """
    .. _graph:

    Simple directed graph implementation.
    """
    def __init__(self):
        self.nodes = set()
        self.edges = set()
        self._removed = set()

    def add_node(self, node):
        """Add a node to the graph."""
        self.nodes.add(node)

    def remove_node(self, node):
        """
        Remove a node from the graph.

        .. WARNING::
            Removing edges containing the removed node
            is not implemented.
        """
        self.nodes.remove(node)

    def add_edge(self, edge):
        """
        Add an edge to the graph.
        Automatically inserts the nodes.
        """
        self.edges.add(edge)
        self.nodes.add(edge.left)
        self.nodes.add(edge.right)

    def remove_edge(self, edge):
        """
        Removes an edge from the graph.

        .. WARNING::
            Does not remove leftover contained nodes.
        """
        self.edges.remove(edge)

    def get_dot(self, format='pdf', mark_edges=None, mark_nodes=None):
        """
        Returns the graphviz object of the graph.
        Needs the :mod:`graphviz` package to be installed.
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

    def render(self, filename=None, format='pdf', mark_edges=None, mark_nodes=None):
        """
        Renders the graph to file.
        Needs the :mod:`graphviz` package to be installed.
        """
        self.get_dot(format, mark_edges, mark_nodes).render(filename=filename, cleanup=True)

    def view(self, format='pdf', mark_edges=None, mark_nodes=None):
        """
        Directly opens the graph in the associated desktop viewer.
        Needs the :mod:`graphviz` package to be installed.
        """
        self.get_dot(format, mark_edges, mark_nodes).view(cleanup=True)

    def edgepath_to_nodepath(self, path):
        """
        Converts an edge path to a node path.
        """
        return [edge.left for edge in path] + [path[-1].right]

    def nodepath_to_edgepath(self, path):
        """
        Converts a node path to an edge path.
        """
        return [Edge(*pair) for pair in pairwise(path)]

    def _get_edge_paths(self, edge, left_edges, paths, seen=None):
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

    def get_edgepaths(self):
        """
        Returns a list of all edge paths.
        Might raise a ``CycleEdgeException``. For in-depth cycle detection
        use ``edge_cycles``, `node_cycles`` or ``get_cycles()``.
        """
        left_edges = OrderedDict()
        paths = []
        for edge in self.edges:
            left_edges.setdefault(edge.left, []).append(edge)
        for edge in self.edges:
            self._get_edge_paths(edge, left_edges, paths)
        return paths

    def get_nodepaths(self):
        """
        Returns a list of all node paths.
        Might raise a ``CycleNodeException``. For in-depth cycle detection
        use ``edge_cycles``, ``node_cycles`` or ``get_cycles()``.
        """
        try:
            paths = self.get_edgepaths()
        except CycleEdgeException as e:
            raise CycleNodeException(self.edgepath_to_nodepath(e.message))
        node_paths = []
        for path in paths:
            node_paths.append(self.edgepath_to_nodepath(path))
        return node_paths

    def _get_cycles(self, edge, left_edges, cycles, seen=None):
        """
        Walks the graph to collect all cycles.
        """
        if not seen:
            seen = []
        if edge in seen:
            cycle = frozenset(seen[seen.index(edge):])
            data = cycles.setdefault(cycle, {'entries': set(), 'path': []})
            if seen:
                data['entries'].add(seen[0])
            data['path'] = seen[seen.index(edge):]
            return
        seen.append(edge)
        if edge.right in left_edges:
            for new_edge in left_edges[edge.right]:
                self._get_cycles(new_edge, left_edges, cycles, seen[:])

    def get_cycles(self):
        """
        Get all cycles in graph. This is not optimised by any means,
        it simply walks the whole graph and collects all cycles. Therefore
        use this only for in-depth cycle inspection. This applies to all
        dependent properties as well (``edge_cycles`` and ``node_cycles``).
        As start nodes any node on the left side of an edge will be tested.
        Returns a mapping of

        .. code:: python

            {frozenset(<cycling edgepath>): {
                'entries': set(<edges leading to the cycle>),
                'path': <last seen edge path of the cycle in order>
            }}

        An edge in ``entries`` is not necessarily part of the cycle itself,
        but once entered the path will lead to the cycle.
        """
        left_edges = OrderedDict()
        cycles = {}
        for edge in self.edges:
            left_edges.setdefault(edge.left, []).append(edge)
        for edge in self.edges:
            self._get_cycles(edge, left_edges, cycles)
        return cycles

    @property
    def edge_cycles(self):
        """
        Returns all cycles as edge paths.
        Use this only for in-depth cycle inspection.
        """
        return [cycle['path'] for cycle in self.get_cycles().values()]

    @property
    def node_cycles(self):
        """
        Returns all cycles as node paths.
        Use this only for in-depth cycle inspection.
        """
        return [self.edgepath_to_nodepath(cycle['path'])
                for cycle in self.get_cycles().values()]

    @property
    def is_cyclefree(self):
        """
        True if the graph contains no cycles.
        To be faster this property relies on path linearization
        instead of the more expensive full cycle detection.
        For in-depth cycle inspection use ``edge_cycles``
        or ``node_cycles``.
        """
        try:
            self.get_edgepaths()
            return True
        except CycleEdgeException:
            return False

    def _can_replace_nodepath(self, needle, haystack):
        if not set(haystack).issuperset(needle):
            return False
        if is_sublist(needle, haystack):
            return False
        return True

    def _compare_startend_nodepaths(self, new_paths, base_paths):
        base_points = set((path[0], path[-1]) for path in base_paths)
        new_points = set((path[0], path[-1]) for path in new_paths)
        return base_points == new_points

    def remove_redundant_paths(self):
        """
        Find and remove redundant paths. A path is redundant if there there are multiple
        possibilities to reach a node from a start node. Since the longer path triggers
        more db updates the shorter gets discarded.
        Might raise a ``CycleNodeException``.
        Returns the removed edges.
        """
        paths = self.get_nodepaths()
        possible_replaces = []
        for p in paths:
            for q in paths:
                if self._can_replace_nodepath(q, p):
                    possible_replaces.append((q, p))
        removed = set()
        for candidate, replacement in possible_replaces:
            edges = [Edge(*nodes) for nodes in pairwise(candidate)]
            for edge in edges:
                if edge in removed:
                    continue
                self.remove_edge(edge)
                removed.add(edge)
                # make sure all startpoints will still update all endpoints
                if not self._compare_startend_nodepaths(self.get_nodepaths(), paths):
                    self.add_edge(edge)
                    removed.remove(edge)
        self._removed.update(removed)
        return removed


# TODO: simplify the deps handling in resolve_dependencies and generate_lookup_map
class ComputedModelsGraph(Graph):
    """
    Class to resolve and convert initial computed fields model dependencies into
    a graph and generate the final resolver functions.
    In ``resolve_dependencies`` the depends field strings are resolved to real models.
    The dependencies are rearranged to adjacency lists for the underlying graph.
    The graph does a cycle check and removes redundant edges to lower the database penalty.
    In the last step the path segments of remaining edges are resolver functions and
    gathered into a lookup map in ``generate_lookup_map``.
    """
    def __init__(self, computed_models):
        """
        ``computed_fields`` is the ``ComputedFieldsModelType._computed_models``
        created during model initialization.
        """
        super(ComputedModelsGraph, self).__init__()
        self.computed_models = computed_models
        self.lookup_map = {}
        self.data, self.cleaned, self.model_mapping = self.resolve_dependencies(self.computed_models)
        self._insert_data(self.cleaned)

    def resolve_dependencies(self, computed_models):
        """
        Converts all depends strings into real model and field dependencies.
        """
        # first resolve all stringified dependencies to real types
        # walks every depends string for all models
        store = OrderedDict()
        for model, fields in computed_models.items():
            modelentry = store.setdefault(model, {})
            for field, depends in fields.items():
                fieldentry = modelentry.setdefault(field, {})
                count = 0
                for value in depends:
                    path, target_field = value.split('#')
                    cls = model
                    agg_path = []
                    new_data = []
                    for symbol in path.split('.'):
                        nd = {}
                        agg_path.append(symbol)
                        try:
                            if fieldentry.get(cls):
                                fieldentry[cls][count]['depends'] = symbol
                        except IndexError:
                            pass
                        is_backrelation = False
                        try:
                            rel = cls._meta.get_field(symbol).rel
                            nd['model'] = cls
                            cls = cls._meta.get_field(symbol).related_model
                            nd['path'] = symbol
                        except (FieldDoesNotExist, AttributeError):  # FIXME: do a real reltype check instead
                            is_backrelation = True
                            field = getattr(cls, symbol).field
                            rel = field.rel
                            cls = rel.related_model
                            nd['path'] = field.name
                            nd['model'] = cls
                        nd['backrel'] = is_backrelation
                        nd['type'] = reltype(rel)
                        new_data.append(nd)
                        fieldentry.setdefault(cls, []).append({
                            'depends': '', 'backrel': is_backrelation,
                            'rel': reltype(rel), 'path': tuple(agg_path[:]), 'nd': new_data[:]})
                    fieldentry[cls][-1]['depends'] = target_field
                    count += 1

        # reorder to adjacency list tree for easier graph handling
        final = OrderedDict()
        model_mapping = OrderedDict()
        for model, fielddata in store.items():
            model_mapping[modelname(model)] = model
            for field, modeldata in fielddata.items():
                for depmodel, data in modeldata.items():
                    model_mapping[modelname(depmodel)] = depmodel
                    for comb in ((modelname(depmodel), dep['depends']
                      if is_computed_field(depmodel, dep['depends']) else '#') for dep in data):
                        final.setdefault(comb, set()).add((modelname(model), field))

        # fix tree: move all sub updates of field dependencies under '#'
        # leads possibly to double paths (removed later if redundant)
        for key, value in final.items():
            model, field = key
            if field == '#':
                for skey, svalue in final.items():
                    smodel, sfield = skey
                    if model == smodel and field != sfield:
                        value.update(svalue)

        return store, final, model_mapping

    def _insert_data(self, data):
        """
        Adds all needed nodes and edges to the graph as in ``data``.
        Data must be an adjacency mapping.
        """
        for node, value in data.items():
            self.add_node(Node(node))
            for node in value:
                self.add_node(Node(node))
        for left, value in data.items():
            for right in value:
                edge = Edge(Node(left), Node(right))
                self.add_edge(edge)

    def _cleaned_data_from_edges(self):
        """
        Returns an adjacency mapping of the graph
        as ``{left: set(right neighbours)}``.
        """
        map = {}
        for edge in self.edges:
            map.setdefault(edge.left.data, set()).add(edge.right.data)
        return map

    def generate_lookup_map(self):
        """
        Generates a function lookup map to be used to get dependent objects.
        Structure of the map is:

        .. code:: python

            {model: {
                '#'      :  [list of callbacks]
                'fieldA' :  [list of callbacks]
                }
            }

        ``model`` denotes the source model. The ``'#'`` callbacks are to be used
        if there are no ``update_fields`` set or if it conains unkown fields
        (ordinary non computed model fields).

        .. CAUTION::

            If there are only known fields in ``update_fields`` always use
            their specific callbacks, never the ``'#'`` callbacks. This is important
            to ensure cycle free database updates. Any known field must call
            it's corresponding callbacks to get properly updated.

        .. NOTE::
            The created map is also used for the map file to circumvent
            the computationally expensive graph and map creation in production mode.
        """
        # reorder full node information to
        # {changed_model: {needs_update_model: {computed_field: dep_data}}}
        final = OrderedDict()
        for model, fielddata in self.data.items():
            for field, modeldata in fielddata.items():
                for depmodel, data in modeldata.items():
                    final.setdefault(depmodel, {}).setdefault(model, {}).setdefault(field, data)

        # apply full node information to graph edges
        table = {}
        for left_node, right_nodes in self._cleaned_data_from_edges().items():
            lmodel, lfield = left_node
            lmodel = self.model_mapping[lmodel]
            rstore = table.setdefault(lmodel, {}).setdefault(lfield, {})
            for right_node in right_nodes:
                rmodel, rfield = right_node
                rmodel = self.model_mapping[rmodel]
                rstore.setdefault(rmodel, {}).setdefault(rfield, []).extend(
                    final[lmodel][rmodel][rfield])

        # finally build functions table for the signal handler
        func_table = {}
        for lmodel, data in table.items():
            for lfield, fielddata in data.items():
                store = func_table.setdefault(lmodel, {}).setdefault(lfield, {})
                for rmodel, rfielddata in fielddata.items():
                    store[rmodel] = PathResolver(rmodel, rfielddata).resolve()
        return func_table
