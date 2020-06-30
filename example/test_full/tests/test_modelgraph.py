from django.test import TestCase
from computedfields.graph import ModelGraph, Edge, Node
from computedfields.models import active_resolver
from ..models import SelfA, SelfB

class TestModelGraphInit(TestCase):
    def test_init(self):
        base_graph = active_resolver._graph
        depsA = base_graph.resolved['local'][SelfA]
        depsB = base_graph.resolved['local'][SelfB]
        ga = ModelGraph(SelfA, depsA)
        gb = ModelGraph(SelfB, depsB)

class TestModelGraph(TestCase):
    def setUp(self):
        base_graph = active_resolver._graph
        self.depsA = base_graph.resolved['local'][SelfA]
        self.depsB = base_graph.resolved['local'][SelfB]
        self.ga = ModelGraph(SelfA, self.depsA)
        self.gb = ModelGraph(SelfB, self.depsB)

    def test_contains_all_needed_edges(self):
        # depsX {key: [valueX]} contains all edges as Edge(valueX, key) ...
        # + '##' edge to all cfs
        edges = []
        for key, sources in self.depsA.items():
            right = Node(key)
            for src in sources:
                edges.append(Edge(Node(src), right))
            edges.append(Edge(Node('##'), right))
        self.assertEqual(set(edges), self.ga.edges)

        edges = []
        for key, sources in self.depsB.items():
            right = Node(key)
            for src in sources:
                edges.append(Edge(Node(src), right))
            edges.append(Edge(Node('##'), right))
        self.assertEqual(set(edges), self.gb.edges)

    def test_transitive_reduction(self):
        self.ga.transitive_reduction()
        # before '##' has edge to all cfs: c1, c2, c3, c4
        # after  '##' has only one edge to c1
        self.assertEqual([edge for edge in self.ga.edges if edge.left == Node('##')], [Edge(Node('##'), Node('c1'))])

    def test_topological_paths(self):
        paths = self.ga.get_topological_paths()
        # should contain all cfs as self dep
        for cf in self.ga.model._computed_fields.keys():
            self.assertEqual(Node(cf) in paths, True)
            self.assertEqual(Node(cf) in paths[Node(cf)], True)
        # non cfs should not contain itself
        for node in paths:
            if node.data not in self.ga.model._computed_fields.keys():
                self.assertEqual(node not in paths[node], True)
        # order must be c1-c2-c3-c4
        self.assertEqual(paths[Node('##')], [Node('c1'), Node('c2'), Node('c3'), Node('c4')])

    def test_binary_conversion(self):
        def mro_helper(base, value):
            return [field for pos, field in enumerate(base) if value & (1 << pos)]
        self.ga.transitive_reduction()
        paths = self.ga.get_topological_paths()
        fpaths = self.ga.generate_field_paths(paths)
        mapping = self.ga.generate_local_mapping(fpaths)
        base = mapping['base']
        fields = mapping['fields']
        for field, paths in fpaths.items():
            if field == '##':
                continue
            self.assertEqual(mro_helper(base, fields[field]), paths)
