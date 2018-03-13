# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.test import TestCase
from computedfields.graph import Node, Edge, Graph, CycleNodeException, CycleEdgeException
from computedfields.helper import pairwise


class GraphTests(TestCase):
    def test_node(self):
        n1 = Node('A')
        n2 = Node('A')
        self.assertIs(n1, n2)
        self.assertTrue(n1 == n2)
        self.assertEqual(str(n1), 'A')

    def test_edge(self):
        n1 = Node('A')
        n2 = Node('B')
        edge1 = Edge(n1, n2)
        edge2 = Edge(n1, n2)
        edge3 = Edge(n2, n1)
        self.assertIs(edge1, edge2)
        self.assertTrue(edge1 == edge2)
        self.assertTrue(edge1 != edge3)
        self.assertEqual(str(edge1), 'Edge A-B')
        self.assertEqual(str(edge1), repr(edge1))

    def test_graph_autoadd_nodes(self):
        n1 = Node('A')
        n2 = Node('B')
        edge = Edge(n1, n2)
        graph = Graph()
        graph.add_edge(edge)
        self.assertIn(edge, graph.edges)
        self.assertIn(n1, graph.nodes)
        self.assertIn(n2, graph.nodes)

    def test_graph_remove_edge(self):
        n1 = Node('A')
        n2 = Node('B')
        edge = Edge(n1, n2)
        graph = Graph()
        graph.add_edge(edge)
        graph.remove_edge(edge)
        self.assertNotIn(edge, graph.edges)
        self.assertIn(n1, graph.nodes)
        self.assertIn(n2, graph.nodes)
        # not implemented: a node should not be removable if still part of an edge
        graph.remove_node(n1)
        self.assertNotIn(n1, graph.nodes)

    def test_paths(self):
        nodes = [Node('A'), Node('B'), Node('C'), Node('D'), Node('E'), Node('F')]
        simple_edges = [Edge(a, b) for a, b in pairwise(nodes)]
        graph = Graph()
        for edge in simple_edges:
            graph.add_edge(edge)
        all_edge_paths = graph.get_edgepaths()
        all_node_paths = graph.get_nodepaths()
        self.assertEqual(len(all_node_paths), 15)  # should match 6 choose 2 (n!/((n-k)!*k!))
        self.assertEqual(all_edge_paths,
                         [graph.nodepath_to_edgepath(path) for path in all_node_paths])
        self.assertEqual(all_node_paths,
                         [graph.edgepath_to_nodepath(path) for path in all_edge_paths])

    def test_graph_cycle_detection(self):
        nodes = [Node('A'), Node('B'), Node('C'), Node('D'), Node('E'), Node('F')]
        simple_edges = [Edge(a, b) for a, b in pairwise(nodes)]
        graph = Graph()
        for edge in simple_edges:
            graph.add_edge(edge)
        self.assertTrue(graph.is_cyclefree)
        self.assertFalse(graph.edge_cycles)
        self.assertFalse(graph.node_cycles)
        # add one cycle
        graph.add_edge(Edge(nodes[1], nodes[0]))
        self.assertFalse(graph.is_cyclefree)
        self.assertEqual(len(graph.node_cycles), 1)
        # add second cycle
        graph.add_edge(Edge(nodes[2], nodes[0]))
        self.assertEqual(len(graph.node_cycles), 2)
        # add third cycle
        graph.add_edge(Edge(nodes[5], nodes[4]))
        self.assertEqual(len(graph.node_cycles), 3)
        # add tricky edge (adds multiple cycles at once)
        graph.add_edge(Edge(nodes[4], nodes[2]))
        self.assertGreater(len(graph.node_cycles), 4)
        self.assertGreater(len(graph.edge_cycles), 4)

    def test_raise_cycle_exceptions(self):
        nodes = [Node('A'), Node('B'), Node('C'), Node('D'), Node('E'), Node('F')]
        simple_edges = [Edge(a, b) for a, b in pairwise(nodes)]
        graph = Graph()
        for edge in simple_edges:
            graph.add_edge(edge)
        # should not raise CycleExceptions
        graph.get_nodepaths()
        graph.get_edgepaths()
        # add one cycle
        graph.add_edge(Edge(nodes[1], nodes[0]))
        # should raise suitable exceptions
        self.assertRaises(CycleNodeException, lambda: graph.get_nodepaths())
        self.assertRaises(CycleEdgeException, lambda: graph.get_edgepaths())
        # CycleNodeException message should contain
        # cycling nodes (order is undetermined)
        try:
            graph.get_nodepaths()
        except CycleNodeException as e:
            self.assertIn(e.args[0], [[nodes[0], nodes[1], nodes[0]],
                                      [nodes[1], nodes[0], nodes[1]]])
