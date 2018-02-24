from collections import OrderedDict
from django.core.exceptions import FieldDoesNotExist
from itertools import tee, izip


def pairwise(iterable):
    a, b = tee(iterable)
    next(b, None)
    return izip(a, b)


def is_computed_field(model, field):
    if hasattr(model, '_computed_fields') and field in model._computed_fields:
        return True
    return False


def modelname(model):
    return '%s.%s' % (model._meta.app_label, model._meta.verbose_name)


def is_sublist(needle, haystack):
    if not needle:
        return True
    if not haystack:
        return False
    max_k = len(needle) - 1
    k = 0
    for elem in haystack:
        if elem != needle[k]:
            k = 0
            continue
        if k == max_k:
            return True
        k += 1
    return False


class CycleException(Exception):
    pass


class Edge(object):
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
        return self.left == other.left and self.right == other.right

    def __ne__(self, other):
        return not self.__eq__(other)


class Node(object):
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
        return self.data == other.data

    def __ne__(self, other):
        return not self.__eq__(other)


class Graph(object):
    def __init__(self):
        self.nodes = set()
        self.edges = set()

    def add_node(self, node):
        self.nodes.add(node)

    def remove_node(self, node):
        self.nodes.remove(node)

    def add_edge(self, edge):
        self.edges.add(edge)
        self.nodes.add(edge.left)
        self.nodes.add(edge.right)

    def remove_edge(self, edge):
        self.edges.remove(edge)

    def render(self):
        from graphviz import Digraph
        dot = Digraph()
        for node in self.nodes:
            dot.node(str(node), str(node))
        for edge in self.edges:
            dot.edge(str(edge.left), str(edge.right))
        dot.view()

    def _get_edge_paths(self, edge, left_edges, paths, seen=None):
        if not seen:
            seen = []
        if edge in seen:
            raise CycleException(seen[seen.index(edge):] + [edge])
        seen.append(edge)
        if edge.right in left_edges:
            for new_edge in left_edges[edge.right]:
                self._get_edge_paths(new_edge, left_edges, paths, seen[:])
        paths.append(seen)

    def get_edgepaths(self):
        left_edges = {}
        paths = []
        for edge in self.edges:
            left_edges.setdefault(edge.left, []).append(edge)
        for edge in self.edges:
            self._get_edge_paths(edge, left_edges, paths)
        return paths

    def get_nodepaths(self):
        paths = self.get_edgepaths()
        node_paths = []
        for path in paths:
            node_paths.append([edge.left for edge in path] + [path[-1].right])
        return node_paths

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
        return removed


class ComputedModelsGraph(Graph):
    def __init__(self, computed_models):
        super(ComputedModelsGraph, self).__init__()
        self.computed_models = computed_models
        self.cleaned = self.resolve_dependencies(self.computed_models)
        self.insert_data(self.cleaned)

    def resolve_dependencies(self, computed_models):
        store = OrderedDict()
        for model, fields in computed_models.iteritems():
            modelentry = store.setdefault(model, {})
            for field, depends in fields.iteritems():
                fieldentry = modelentry.setdefault(field, {})
                count = 0
                for value in depends:
                    path, target_field = value.split('#')
                    cls = model
                    agg_path = []
                    for symbol in path.split('.'):
                        agg_path.append(symbol)
                        try:
                            if fieldentry.get(cls):
                                fieldentry[cls][count]['depends'] = symbol
                        except IndexError:
                            pass
                        is_backrelation = False
                        try:
                            cls = cls._meta.get_field(symbol).related_model
                        except FieldDoesNotExist:
                            is_backrelation = True
                            cls = getattr(cls, symbol).field.rel.related_model
                        fieldentry.setdefault(cls, []).append({
                            'depends': '', 'backrel': is_backrelation, 'path': tuple(agg_path[:])})
                    fieldentry[cls][-1]['depends'] = target_field
                    count += 1

        # reorder data for better graph handling
        final = {}
        for model, fielddata in store.iteritems():
            for field, modeldata in fielddata.iteritems():
                for depmodel, data in modeldata.iteritems():
                    for comb in ((modelname(depmodel), dep['depends']
                    if is_computed_field(depmodel, dep['depends']) else '#') for dep in data):
                        final.setdefault(comb, set()).add((modelname(model), field))

        # fix tree: move all sub updates of field dependencies under '#'
        # leads possibly to double paths (removed later if redundant)
        for key, value in final.iteritems():
            model, field = key
            if field == '#':
                for skey, svalue in final.iteritems():
                    smodel, sfield = skey
                    if model == smodel and field != sfield:
                        value.update(svalue)
        return final

    def insert_data(self, data):
        for node, value in data.iteritems():
            self.add_node(Node(node))
            for node in value:
                self.add_node(Node(node))
        for left, value in data.iteritems():
            for right in value:
                edge = Edge(Node(left), Node(right))
                self.add_edge(edge)