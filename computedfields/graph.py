"""
Module containing the graph logic for the dependency resolver.

Upon application initialization a dependency graph of all project wide
computed fields is created. The graph does a basic cycle check and
removes redundant dependencies. Finally the dependencies are translated
to resolver functions to be used later by ``update_dependent`` and in
the signal handlers.
"""
from collections import OrderedDict
from django.core.exceptions import FieldDoesNotExist
from computedfields.helper import pairwise, is_sublist, modelname, is_computedfield
import django
Django2 = False
if django.VERSION[0] >= 2:
    Django2 = True


class CycleException(Exception):
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
    pass


class CycleNodeException(CycleException):
    """
    Exception raised during path linearization, if a cycle was found.
    Contains the found cycle as list of nodes in ``args``.
    """
    pass


class Edge(object):
    """
    Class for representing an edge in ``Graph``.
    The instances are created as singletons,
    calling ``Edge('A', 'B')`` multiple times
    will always point to the same object.
    """
    instances = {}

    def __new__(cls, *args, **kwargs):
        key = (args[0], args[1])
        if key in cls.instances:
            return cls.instances[key]
        instance = super(Edge, cls).__new__(cls)
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

    def __hash__(self):
        return id(self)


class Node(object):
    """
    Class for representing a node in ``Graph``.
    The instances are created as singletons,
    calling ``Node('A')`` multiple times will
    always point to the same object.
    """
    instances = {}

    def __new__(cls, *args, **kwargs):
        if args[0] in cls.instances:
            return cls.instances[args[0]]
        instance = super(Node, cls).__new__(cls)
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

    def __hash__(self):
        return id(self)


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
        Automatically inserts the associated nodes.
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

    def render(self, filename=None, format='pdf', mark_edges=None, mark_nodes=None):
        """
        Renders the graph to file (needs the :mod:`graphviz` package).
        """
        self.get_dot(format, mark_edges, mark_nodes).render(
            filename=filename, cleanup=True)

    def view(self, format='pdf', mark_edges=None, mark_nodes=None):
        """
        Directly opens the graph in the associated desktop viewer
        (needs the :mod:`graphviz` package).
        """
        self.get_dot(format, mark_edges, mark_nodes).view(cleanup=True)

    def edgepath_to_nodepath(self, path):
        """
        Converts a list of edges to a list of nodes.
        """
        return [edge.left for edge in path] + [path[-1].right]

    def nodepath_to_edgepath(self, path):
        """
        Converts a list of nodes to a list of edges.
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
        An edge path is represented as list of edges.

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
        A node path is represented as list of nodes.

        Might raise a ``CycleNodeException``. For in-depth cycle detection
        use ``edge_cycles``, ``node_cycles`` or ``get_cycles()``.
        """
        try:
            paths = self.get_edgepaths()
        except CycleEdgeException as e:
            raise CycleNodeException(self.edgepath_to_nodepath(e.args[0]))
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
        Returns all cycles as list of edge lists.
        Use this only for in-depth cycle inspection.
        """
        return [cycle['path'] for cycle in self.get_cycles().values()]

    @property
    def node_cycles(self):
        """
        Returns all cycles as list of node lists.
        Use this only for in-depth cycle inspection.
        """
        return [self.edgepath_to_nodepath(cycle['path'])
                for cycle in self.get_cycles().values()]

    @property
    def is_cyclefree(self):
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

    def remove_redundant(self):
        """
        Find and remove redundant edges. An edge is redundant
        if there there are multiple possibilities to reach an end node
        from a start node. Since the longer path triggers more needed
        database updates the shorter path gets discarded.
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
    def __init__(self, computed_models):
        """
        ``computed_fields`` is the ``ComputedFieldsModelType._computed_models``
        created during model initialization.
        """
        super(ComputedModelsGraph, self).__init__()
        self.models = {}
        self.resolved = self.resolve_dependencies(computed_models)
        self.cleaned_data = self._clean_data(self.resolved)
        self._insert_data(self.cleaned_data)

    def resolve_dependencies(self, computed_models):
        """
        Converts all depend strings into real model field lookups.
        """
        resolved = OrderedDict()
        for model, fields in computed_models.items():
            for field, depends in fields.items():
                fieldentry = resolved.setdefault(model, {}).setdefault(field, {})
                for value in depends:
                    try:
                        # depends on another computed field
                        path, target_field = value.split('#')
                    except ValueError:
                        # simple dependency to other model
                        path = value
                        target_field = '#'
                    path_segments = []
                    cls = model
                    for symbol in path.split('.'):
                        try:
                            rel = cls._meta.get_field(symbol)
                        except FieldDoesNotExist:
                            rel = getattr(cls, symbol).rel
                            symbol = (rel.related_name
                                      or rel.related_query_name
                                      or rel.related_model._meta.model_name)
                        path_segments.append(symbol)
                        cls = rel.related_model
                        fieldentry.setdefault(cls, []).append({'path': '__'.join(path_segments)})
                    fieldentry[cls][-1]['depends'] = target_field
        return resolved

    def _clean_data(self, data):
        """
        Converts the dependency data into an adjacency list tree
        to be used with the underlying graph.
        """
        cleaned = OrderedDict()
        for model, fielddata in data.items():
            self.models[modelname(model)] = model
            for field, modeldata in fielddata.items():
                for depmodel, relations in modeldata.items():
                    self.models[modelname(depmodel)] = depmodel
                    for dep in relations:
                        if is_computedfield(depmodel, dep.get('depends')):
                            depends = dep['depends']
                        else:
                            depends = '#'
                        key = (modelname(depmodel), depends)
                        value = (modelname(model), field)
                        cleaned.setdefault(key, set()).add(value)
        return cleaned

    def _insert_data(self, data):
        """
        Adds nodes in ``data`` to the graph and creates edges.
        Data must be an adjacency mapping like
        ``{left: set(right neighbours)}``.
        """
        for node, value in data.items():
            self.add_node(Node(node))
            for node in value:
                self.add_node(Node(node))
        for left, value in data.items():
            for right in value:
                edge = Edge(Node(left), Node(right))
                self.add_edge(edge)

    def generate_lookup_map(self):
        """
        Generates the final lookup map for queryset generation.

        Structure of the map is:

        .. code:: python

            {model: {
                '#'      :  dependencies
                'fieldA' :  dependencies
                }
            }

        ``model`` denotes the source model of a given instance. ``'fieldA'`` points to
        a computed field that was saved. The right side contains the dependencies
        in the form

        .. code:: python

            {dependent_model: (fields, filter_strings)}

        In ``update_dependent`` the information will be used to create a queryset
        and save their elements (roughly):

        .. code:: python

            queryset = dependent_model.objects.filter(string1=instance)
            queryset |= dependent_model.objects.filter(string2=instance)
            for obj in queryset:
                obj.save(update_fields=fields)

        The ``'#'`` is a special placeholder to indicate, that a model object
        was saved normally. It contains the plain and non computed field dependencies.

        The separation of dependencies to computed fields and to other fields makes it
        possible to create complex computed field dependencies, even multiple times
        between the same objects without running into circular dependencies:

        .. CODE:: python

            class A(ComputedFieldsModel):
                @computed(..., depends=['b_set#comp_b'])
                def comp_a(self):
                     ...

            class B(ComputedFieldsModel):
                a = ForeignKey(B)
                @computed(..., depends=['a'])
                def comp_b(self):
                    ...

        Here ``A.comp_a`` depends on ``b.com_b`` which itself somehow depends on ``A``.
        If an instance of ``A`` gets saved, the corresponding objects in ``B``
        will be updated, which triggers a final update of ``comp_a`` fields
        on associated ``A`` objects.

        .. CAUTION::

            If there are only computed fields in ``update_fields`` always use
            those dependencies, never ``'#'``. This is important to ensure
            cycle free database updates. For computed fields the corresponding
            dependencies should always be used to get properly updated.

        .. NOTE::
            The created map is also used for the pickle file to circumvent
            the computationally expensive graph and map creation in production mode.
        """
        # apply full node information to graph edges
        table = {}
        for edge in self.edges:
            lmodel, lfield = edge.left.data
            lmodel = self.models[lmodel]
            rmodel, rfield = edge.right.data
            rmodel = self.models[rmodel]
            table.setdefault(lmodel, {})\
                 .setdefault(lfield, {})\
                 .setdefault(rmodel, {})\
                 .setdefault(rfield, [])\
                 .extend(self.resolved[rmodel][rfield][lmodel])

        # finally build functions table for the signal handler
        func_table = {}
        for lmodel, data in table.items():
            for lfield, ldata in data.items():
                for rmodel, rdata in ldata.items():
                    func_table.setdefault(lmodel, {})\
                              .setdefault(lfield, {})[rmodel] = self._resolve(rdata)
        return func_table

    def _resolve(self, data):
        fields = set()
        strings = set()
        for field, dependencies in data.items():
            fields.add(field)
            for dep in dependencies:
                strings.add(dep['path'])
        return fields, strings
