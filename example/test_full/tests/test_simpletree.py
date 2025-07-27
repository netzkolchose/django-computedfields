from contextlib import contextmanager
from django.test import TestCase, override_settings
from computedfields.resolver import active_resolver
from computedfields.graph import CycleEdgeException

from ..models import Tree

@contextmanager
def patch_tree(with_recreation=True):
    """
    Patch models.Tree into self refencing path.
    We do this only temporary to not affect other test cases on global level.
    """
    depends = Tree._meta.get_field('path')._computed['depends']
    depends.clear()
    depends.append(('self', ['name']))
    depends.append(('parent', ['path']))
    if with_recreation:
        active_resolver.load_maps(_force_recreation=True)
    yield
    depends.clear()
    depends.append(('self', ['name']))
    if with_recreation:
        active_resolver.load_maps(_force_recreation=True)

class TestTree(TestCase):
    def test_patchsetup(self):
        with patch_tree(False):
            self.assertEqual(Tree._meta.get_field('path')._computed['depends'], [('self', ['name']), ('parent', ['path'])])
            with self.assertRaises(CycleEdgeException):
                active_resolver.load_maps(_force_recreation=True)
        self.assertEqual(Tree._meta.get_field('path')._computed['depends'], [('self', ['name'])])
        active_resolver.load_maps(_force_recreation=True)

    @override_settings(COMPUTEDFIELDS_ALLOW_RECURSION=True)
    def test_allow_recursion(self):
        with patch_tree():
            self.assertEqual(Tree._meta.get_field('path')._computed['depends'], [('self', ['name']), ('parent', ['path'])])
        self.assertEqual(Tree._meta.get_field('path')._computed['depends'], [('self', ['name'])])

    @override_settings(COMPUTEDFIELDS_ALLOW_RECURSION=True)
    def test_object_creation(self):
        with patch_tree():
            parent = Tree.objects.create(name='parent')
            child = Tree.objects.create(name='child', parent=parent)
            grandchild = Tree.objects.create(name='grandchild', parent=child)

            parent.refresh_from_db()
            child.refresh_from_db()
            grandchild.refresh_from_db()
            self.assertEqual(parent.path, '/parent')
            self.assertEqual(child.path, '/parent/child')
            self.assertEqual(grandchild.path, '/parent/child/grandchild')

    @override_settings(COMPUTEDFIELDS_ALLOW_RECURSION=True)
    def test_object_change(self):
        with patch_tree():
            parent = Tree.objects.create(name='parent')
            child = Tree.objects.create(name='child', parent=parent)
            grandchild = Tree.objects.create(name='grandchild', parent=child)

            parent.name = 'root'
            parent.save(update_fields=['name'])

            parent.refresh_from_db()
            child.refresh_from_db()
            grandchild.refresh_from_db()
            self.assertEqual(parent.path, '/root')
            self.assertEqual(child.path, '/root/child')
            self.assertEqual(grandchild.path, '/root/child/grandchild')

    @override_settings(COMPUTEDFIELDS_ALLOW_RECURSION=True)
    def test_object_move(self):
        with patch_tree():
            p1 = Tree.objects.create(name='P1')
            p2 = Tree.objects.create(name='P2')
            c1 = Tree.objects.create(name='C1', parent=p1)
            c2 = Tree.objects.create(name='C2', parent=p1)
            g1 = Tree.objects.create(name='G1', parent=c1)

            p1.refresh_from_db()
            p2.refresh_from_db()
            c1.refresh_from_db()
            c2.refresh_from_db()
            g1.refresh_from_db()
            self.assertEqual(p1.path, '/P1')
            self.assertEqual(p2.path, '/P2')
            self.assertEqual(c1.path, '/P1/C1')
            self.assertEqual(c2.path, '/P1/C2')
            self.assertEqual(g1.path, '/P1/C1/G1')
            
            c1.parent = p2
            c1.save(update_fields=['parent'])

            p1.refresh_from_db()
            p2.refresh_from_db()
            c1.refresh_from_db()
            c2.refresh_from_db()
            g1.refresh_from_db()
            self.assertEqual(p1.path, '/P1')
            self.assertEqual(p2.path, '/P2')
            self.assertEqual(c1.path, '/P2/C1')
            self.assertEqual(c2.path, '/P1/C2')
            self.assertEqual(g1.path, '/P2/C1/G1')

            c2.parent = p2
            c2.save(update_fields=['parent'])
            g1.parent = c2
            g1.save(update_fields=['parent'])
            c2.refresh_from_db()
            g1.refresh_from_db()
            self.assertEqual(c2.path, '/P2/C2')
            self.assertEqual(g1.path, '/P2/C2/G1')

            g1.parent = None
            g1.save(update_fields=['parent'])
            g1.refresh_from_db()
            self.assertEqual(g1.path, '/G1')


from computedfields.models import not_computed
class TestTreeNC(TestCase):

    @override_settings(COMPUTEDFIELDS_ALLOW_RECURSION=True)
    def test_object_creation(self):
        with patch_tree():
            with not_computed(recover=True):
                parent = Tree.objects.create(name='parent')
                child = Tree.objects.create(name='child', parent=parent)
                grandchild = Tree.objects.create(name='grandchild', parent=child)

            parent.refresh_from_db()
            child.refresh_from_db()
            grandchild.refresh_from_db()
            self.assertEqual(parent.path, '/parent')
            self.assertEqual(child.path, '/parent/child')
            self.assertEqual(grandchild.path, '/parent/child/grandchild')

    @override_settings(COMPUTEDFIELDS_ALLOW_RECURSION=True)
    def test_object_change(self):
        with patch_tree():
            with not_computed(recover=True):
                parent = Tree.objects.create(name='parent')
                child = Tree.objects.create(name='child', parent=parent)
                grandchild = Tree.objects.create(name='grandchild', parent=child)

                parent.name = 'root'
                parent.save(update_fields=['name'])

            parent.refresh_from_db()
            child.refresh_from_db()
            grandchild.refresh_from_db()
            self.assertEqual(parent.path, '/root')
            self.assertEqual(child.path, '/root/child')
            self.assertEqual(grandchild.path, '/root/child/grandchild')

    @override_settings(COMPUTEDFIELDS_ALLOW_RECURSION=True)
    def test_object_move(self):
        with patch_tree():
            with not_computed(recover=True):
                p1 = Tree.objects.create(name='P1')
                p2 = Tree.objects.create(name='P2')
                c1 = Tree.objects.create(name='C1', parent=p1)
                c2 = Tree.objects.create(name='C2', parent=p1)
                g1 = Tree.objects.create(name='G1', parent=c1)

            p1.refresh_from_db()
            p2.refresh_from_db()
            c1.refresh_from_db()
            c2.refresh_from_db()
            g1.refresh_from_db()
            self.assertEqual(p1.path, '/P1')
            self.assertEqual(p2.path, '/P2')
            self.assertEqual(c1.path, '/P1/C1')
            self.assertEqual(c2.path, '/P1/C2')
            self.assertEqual(g1.path, '/P1/C1/G1')

            with not_computed(recover=True):
                c1.parent = p2
                c1.save(update_fields=['parent'])

            p1.refresh_from_db()
            p2.refresh_from_db()
            c1.refresh_from_db()
            c2.refresh_from_db()
            g1.refresh_from_db()
            self.assertEqual(p1.path, '/P1')
            self.assertEqual(p2.path, '/P2')
            self.assertEqual(c1.path, '/P2/C1')
            self.assertEqual(c2.path, '/P1/C2')
            self.assertEqual(g1.path, '/P2/C1/G1')

            with not_computed(recover=True):
                c2.parent = p2
                c2.save(update_fields=['parent'])
                g1.parent = c2
                g1.save(update_fields=['parent'])
            c2.refresh_from_db()
            g1.refresh_from_db()
            self.assertEqual(c2.path, '/P2/C2')
            self.assertEqual(g1.path, '/P2/C2/G1')

            with not_computed(recover=True):
                g1.parent = None
                g1.save(update_fields=['parent'])
            g1.refresh_from_db()
            self.assertEqual(g1.path, '/G1')
