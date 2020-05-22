"""
Module containing the graph logic for the dependency resolver.

Upon application initialization a dependency graph of all project wide
computed fields is created. The graph does a basic cycle check and
removes redundant dependencies. Finally the dependencies are translated
to the resolver map to be used later by ``update_dependent`` and in
the signal handlers.
"""
from collections import OrderedDict
from django.core.exceptions import FieldDoesNotExist
from django.db.models import ForeignKey
from computedfields.helper import pairwise, is_sublist, modelname, is_computedfield

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
        return self.data if isinstance(self.data, str) else '.'.join(self.data)

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
        self.cleaned_data = self._clean_data(self.resolved['global'])
        self._insert_data(self.cleaned_data)
        self._fk_map = self._generate_fk_map()
        self.modelgraphs = {}
        self.union = None

    # FIXME: remove once transition to new depends format is done
    def _is_old_depends(self, depends):
        if depends is None:
            return True
        return any(isinstance(el, str) for el in depends)

    # FIXME: remove once transition to new depends format is done
    def _get_local_non_cf_fields(self, model):
        # get all local fields of a model that are:
        # - concrete
        # - not a relation
        # - not primary key
        # - not a computed field
        cfields = getattr(model, '_computed_fields', {}).keys()
        return {f.name
            for f in model._meta.get_fields()
                if f.concrete
                and not f.auto_created
                and not f.is_relation
                and not f.primary_key
                and not f.name in cfields
        }

    # FIXME: remove once transition to new depends format is done
    def _resolve_relational_fields(self, model, path):
        cls = model
        for symbol in path.split('.'):
            try:
                rel = cls._meta.get_field(symbol)
            except FieldDoesNotExist:
                rel = getattr(cls, symbol).rel
                symbol = (rel.related_name
                          or rel.related_query_name
                          or rel.related_model._meta.model_name)
            cls = rel.related_model
        return self._get_local_non_cf_fields(cls)

    # FIXME: remove once transition to new depends format is done
    def _convert_depends(self, local_fields, depends, model):
        # convert old style depends string into new style
        result = []

        if depends:
            path_data = {'self': set(local_fields)} if local_fields else {}
            for dep in depends:
                try:
                    path, field = dep.split('#')
                    fields = (field,)
                except ValueError:
                    path = dep
                    fields = self._resolve_relational_fields(model, path)
                path_data.setdefault(path, set()).update(fields)
            for path, fields in path_data.items():
                result.append((path, fields))
        else:
            # always append local fields
            result.append(('self', set(local_fields)))
        return result

    def _check_concrete_field(self, model, fieldname):
        if not model._meta.get_field(fieldname).concrete:
            raise ComputedFieldsException("%s has no concrete field named '%s'" % (model, fieldname))

    def resolve_dependencies(self, computed_models):
        """
        Converts field dependencies into lookups and checks the fields' existance.
        Also expands the old depends notation into the new format:

        - ``'relA.relB'`` --> ``['relA.relB', local_fieldnames_on_B]``
        - ``'relA#xy'`` --> ``['relA', ['xy']]``
        - plus model local non computed fields, e.g. ``['self', ['fieldA', 'fieldB']]``

        .. warning::
            Dont use the old `depends` notation anymore, as it is underdetermined leading to ambiguity and
            will be removed by a later version.
        """
        global_deps = OrderedDict()
        local_deps = {}
        for model, fields in computed_models.items():
            local_fields = None
            local_deps.setdefault(model, {}) # always add to local to get a result from mro later on
            for field, depends in fields.items():
                fieldentry = global_deps.setdefault(model, {}).setdefault(field, {})
                local_deps.setdefault(model, {}).setdefault(field, set())

                if self._is_old_depends(depends):
                    # print a warning about old depends string
                    # FIXME: to be removed with future version
                    # silence test cases
                    if not model._meta.model_name in ('olddependsparent', 'olddependschild'):
                        print('WARNING: "%s" on %s contains old depends string format.'
                            % (field, model))
                    # translate old depends listing into new format
                    # note that this pulls all model local fields of underdetemined depends
                    # declarations:   depends=['relA'] => (('relA', local_fields_on_A),)
                    if not local_fields:
                        local_fields = self._get_local_non_cf_fields(model)
                    depends = self._convert_depends(local_fields, depends, model)

                for path, fieldnames in depends:
                    if path == 'self':
                        # skip selfdeps in global graph handling
                        # we handle it instead on model graph level
                        # do at least an existance check here to provide an early error
                        for fieldname in fieldnames:
                            self._check_concrete_field(model, fieldname)
                        local_deps.setdefault(model, {}).setdefault(field, set()).update(fieldnames)
                        continue
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
                        # add path segment to self deps if we have an fk field on a CFM
                        # this is needed to correctly propagate direct fk changes in local cf mro later on
                        if isinstance(rel, ForeignKey) and cls in computed_models:
                            self._check_concrete_field(cls, symbol)
                            local_deps.setdefault(cls, {}).setdefault(field, set()).add(symbol)
                        if path_segments:
                            # add segment to intermodel graph deps
                            # replaces the old '#' all rule with real source -> target deps
                            fieldentry.setdefault(cls, []).append({'path': '__'.join(path_segments), 'depends': symbol})
                        path_segments.append(symbol)
                        cls = rel.related_model
                    for target_field in fieldnames:
                        self._check_concrete_field(cls, target_field)
                        fieldentry.setdefault(cls, []).append({'path': '__'.join(path_segments), 'depends': target_field})
        return {'global': global_deps, 'local': local_deps}

    def _clean_data(self, data):
        """
        Converts the global dependency data into an adjacency list tree
        to be used with the underlying graph.
        """
        cleaned = OrderedDict()
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

    def _insert_data(self, data):
        """
        Adds edges in ``data`` to the graph.
        Data must be an adjacency mapping like
        ``{left: set(right neighbours)}``.
        """
        for left, value in data.items():
            for right in value:
                edge = Edge(Node(left), Node(right))
                self.add_edge(edge)

    def _get_fk_fields(self, model, paths):
        """
        Reduce field name dependencies in paths to reverse real local fk fields.
        """
        candidates = set(el.split('__')[-1] for el in paths)
        result = set()
        for f in filter(lambda f: isinstance(f, ForeignKey), model._meta.get_fields()):
            if f.related_query_name() in candidates:
                result.add(f.name)
        return result

    def _generate_fk_map(self):
        """
        Generate a map of local dependent fk field.
        This must be done before any graph path reduction to avoid loosing track
        of fk fields, that are removed by the reduction.
        The fk map is later on needed to do cf updates of old relations
        after relation changes, that would otherwise turn dirty.
        Note: An update of old relations must always trigger the '#' action on the model instances.
        """
        # build full node information from edges
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
                 .extend(self.resolved['global'][rmodel][rfield][lmodel])

        # extract all field paths for model dependencies
        path_map = {}
        for lmodel, data in table.items():
            path_map[lmodel] = set()
            for lfield, ldata in data.items():
                for rmodel, rdata in ldata.items():
                    for rfield, deps in rdata.items():
                        for dep in deps:
                            path_map[lmodel].add(dep['path'])

        # translate paths to model local fields and filter for fk fields
        final = {}
        for model, paths in path_map.items():
            v = self._get_fk_fields(model, paths)
            if v:
                final[model] = v
        return final

    def _resolve(self, data):
        """
        Helper to merge querystring paths for lookup map.
        """
        fields = set()
        strings = set()
        for field, dependencies in data.items():
            fields.add(field)
            for dep in dependencies:
                strings.add(dep['path'])
        return fields, strings

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
        a field that was changed. The right side contains the dependencies
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
                 .extend(self.resolved['global'][rmodel][rfield][lmodel])

        # finally build map for the signal handler
        lookup_map = {}
        for lmodel, data in table.items():
            for lfield, ldata in data.items():
                for rmodel, rdata in ldata.items():
                    lookup_map.setdefault(lmodel, {})\
                              .setdefault(lfield, {})[rmodel] = self._resolve(rdata)
        return lookup_map

    def prepare_modelgraphs(self):
        """
        Helper to initialize model local subgraphs.
        """
        if self.modelgraphs:
            return
        data = self.resolved['local']
        for model, local_deps in data.items():
            self.modelgraphs[model] = ModelGraph(model, local_deps)
            # modelgraph always must be cyclefree, thus we can always do the reduction here
            self.modelgraphs[model].transitive_reduction()

    def generate_local_mro_map(self):
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
            Note that the actual values in `fields` are bitarrays to index positions of `base`, which allows
            quick field update merges at runtime by doing binary OR on the bitarrays.
        """
        self.prepare_modelgraphs()
        return dict((model, g.generate_local_mapping(g.generate_field_paths(g.get_topological_paths())))
                        for model, g in self.modelgraphs.items())

    def get_uniongraph(self):
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
            for model, g in self.modelgraphs.items():
                name = modelname(model)
                for edge in g.edges:
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
    def __init__(self, model, local_dependencies):
        super(ModelGraph, self).__init__()
        self.model = model

        # add all edges from extracted local deps
        for right, deps in local_dependencies.items():
            for left in deps:
                self.add_edge(Edge(Node(left), Node(right)))

        # add ## node as update_fields=None placeholder with edges to all computed fields
        # --> None explicitly updates all computed fields
        # Note: this has to be on all cfs to not skip a non local dependent one by accident
        left = Node('##')
        for cf in self.model._computed_fields.keys():
            self.add_edge(Edge(left, Node(cf)))

    def transitive_reduction(self):
        """
        Remove redundant single edges. Also checks for cycles.
        *Note:* Other than intermodel dependencies a model local dependencies always must be cyclefree.
        """
        paths = self.get_edgepaths()
        remove = set()
        for p1 in paths:
            # we only cut single edge paths
            if len(p1) > 1:
                continue
            left = p1[0].left
            right = p1[-1].right
            for p2 in paths:
                if p2 == p1:
                    continue
                if right == p2[-1].right and left == p2[0].left:
                    remove.add(p1[0])
        for edge in remove:
            self.remove_edge(edge)

    def _tsort(self, graph, start, paths, path):
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

    def get_topological_paths(self):
        """
        Creates a map of all possible entry nodes and their topological update path (computed fields mro).
        """
        # create simplified parent-child relation graph
        graph = {}
        for edge in self.edges:
            graph.setdefault(edge.left, []).append(edge.right)
        topological_paths = {}

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

    def generate_field_paths(self, tpaths):
        """
        Convert topological path node mapping into a mapping containing the fieldnames.
        """
        field_paths = {}
        for node, path in tpaths.items():
            field_paths[node.data] = [el.data for el in path]
        return field_paths

    def generate_local_mapping(self, field_paths):
        """
        Generates the final model local update table to be used during ``ComputedFieldsModel.save``.
        Output is a mapping of local fields, that also update local computed fields, to a bitarray
        containing the computed fields mro, and the base topologcial order for a full update.
        """
        # transfer final data to bitarray
        # bitarray: bit index is realisation of one valid full topsort order held in '##'
        # since this order was build from full graph it always reflects the correct mro even for a subset
        # of fields in update_fields later on
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
        binary = {}
        base = field_paths['##']
        for field, deps in field_paths.items():
            if field == '##':
                continue
            binary[field] = 0
            for pos, name in enumerate(base):
                binary[field] |= (1 if name in deps else 0) << pos
        return {'base': base, 'fields': binary}
