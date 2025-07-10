from django.test import TestCase
from ..models import DefaultParent, DefaultChild, DefaultToy
from computedfields.signals import resolver_start, resolver_exit, resolver_update


RECORDED = []


def record_start(sender, **kwargs):
    RECORDED.append(['start'])

def record_exit(sender, **kwargs):
    RECORDED.append(['exit'])

def record_update(sender, model, fields, pks, **kwargs):
    RECORDED.append(['update', model, fields, pks])


class Signals(TestCase):
    def setUp(self) -> None:
        self.p1 = DefaultParent.objects.create(name='p1')
        self.p2 = DefaultParent.objects.create(name='p2')
        self.c1 = DefaultChild.objects.create(name='c1', parent=self.p1)
        self.c2 = DefaultChild.objects.create(name='c2', parent=self.p1)
        self.t1 = DefaultToy.objects.create(name='t1')
        self.t2 = DefaultToy.objects.create(name='t2')
        self.c1.toys.add(self.t1)

        resolver_start.connect(record_start)
        resolver_exit.connect(record_exit)
        resolver_update.connect(record_update)
        return super().setUp()
    
    def tearDown(self) -> None:
        resolver_start.disconnect(record_start)
        resolver_exit.disconnect(record_exit)
        resolver_update.disconnect(record_update)
        return super().tearDown()

    def test_create_parent(self):
        RECORDED.clear()
        # creating a parent should not trigger send any signal, as nothing depends on it
        DefaultParent.objects.create(name='some_p')
        p = DefaultParent(name='some_p')
        p.save()
        self.assertEqual(RECORDED, [])

    def test_create_child(self):
        RECORDED.clear()
        # create child must update DefaultParent.children_names
        DefaultChild.objects.create(name='some_c', parent=self.p1)
        self.assertEqual(RECORDED, [
            ['start'],
            ['update', DefaultParent, {'children_names'}, [self.p1.pk]],
            ['exit']
        ])
        RECORDED.clear()
        c = DefaultChild(name='some_c', parent=self.p1)
        c.save()
        self.assertEqual(RECORDED, [
            ['start'],
            ['update', DefaultParent, {'children_names'}, [self.p1.pk]],
            ['exit']
        ])
        RECORDED.clear()

    def test_create_toy(self):
        RECORDED.clear()
        # create toy updates DefaultChild.toy_names
        # but since it is not linked to a child, resolver exits empty
        DefaultToy.objects.create(name='some_t')
        t = DefaultToy(name='some_t')
        t.save()
        self.assertEqual(RECORDED, [['start'], ['exit'], ['start'], ['exit']])
        RECORDED.clear()

    def test_delete_parent(self):
        RECORDED.clear()
        # delete parent w'o child does nothing
        self.p2.delete()
        self.assertEqual(RECORDED, [])

        # delete parent with child updates:
        # - first cascade delete p1 --> c1,c2
        # - delete c1,c2 updates DefaultParent.children_name and DefaultToy.children_names
        # - delete p1
        self.p1.delete()
        self.assertEqual(RECORDED, [
            ['start'],
            ['update', DefaultParent, {'children_names'}, [1]],
            ['exit'],
            ['start'],  # FIXME: why second run here?
            ['update', DefaultToy, {'children_names'}, [1]],
            ['exit'],
        ])
        RECORDED.clear()

    def test_delete_child(self):
        RECORDED.clear()
        # delete child updates DefaultParent.children_names
        self.c2.delete()
        self.assertEqual(RECORDED, [
            ['start'],
            ['update', DefaultParent, {'children_names'}, [self.p1.pk]],
            ['exit']
        ])
        RECORDED.clear()

        # delete child with toys updates DefaultParent.children_name and DefaultToy.children_names
        self.c1.delete()
        try:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultToy, {'children_names'}, [1]], # updates may flip positions
                ['update', DefaultParent, {'children_names'}, [self.p1.pk]],
                ['exit'],
            ])
        except AssertionError:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultParent, {'children_names'}, [self.p1.pk]],
                ['update', DefaultToy, {'children_names'}, [1]],
                ['exit'],
            ])
        RECORDED.clear()

    def test_delete_toy(self):
        RECORDED.clear()
        # empty, if not linked to child
        self.t2.delete()
        self.assertEqual(RECORDED, [])

        # linked to child updates DefaultChild.toy_names
        self.t1.delete()
        self.assertEqual(RECORDED, [
            ['start'],
            ['update', DefaultChild, {'toy_names'}, [self.c1.pk]],
            ['exit']
        ])
        RECORDED.clear()

    def test_save_details(self):
        RECORDED.clear()
        # a full save trigger start/end, if something depends on a field
        self.c1.save()
        self.assertEqual(RECORDED, [['start'], ['exit']])
        RECORDED.clear()

        # partial save of non-depends fields does not trigger any signal
        self.c1.save(update_fields=['toy_names'])
        self.assertEqual(RECORDED, [])

        RECORDED.clear()

    def test_move_child_parent(self):
        RECORDED.clear()
        # move c1 --> p1 (no change) is an empty update
        self.c1.parent = self.p1
        self.c1.save()
        self.assertEqual(RECORDED, [['start'], ['exit']])
        RECORDED.clear()

        # move c2 --> p2 updates DefaultParent.children_names on p2 & p1
        self.c2.parent = self.p2
        self.c2.save()
        self.assertEqual(RECORDED, [
            ['start'],
            ['update', DefaultParent, {'children_names'}, [self.p2.pk]],
            ['update', DefaultParent, {'children_names'}, [self.p1.pk]],
            ['exit']
        ])
        RECORDED.clear()

    def test_m2m_child_toy(self):
        RECORDED.clear()
        # add t2 to c2 updates DefaultChild.toy_names & DefaultToy.children_names
        self.c2.toys.add(self.t2)
        try:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultChild, {'toy_names'}, [self.c2.pk]],  # updates may flip positions
                ['update', DefaultToy, {'children_names'}, [self.t2.pk]],
                ['exit']
            ])
        except AssertionError:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultToy, {'children_names'}, [self.t2.pk]],
                ['update', DefaultChild, {'toy_names'}, [self.c2.pk]],
                ['exit']
            ])
        RECORDED.clear()

        # remove t2 from c2 updates DefaultChild.toy_names & DefaultToy.children_names
        self.c2.toys.remove(self.t2)
        try:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultChild, {'toy_names'}, [self.c2.pk]],  # updates may flip positions
                ['update', DefaultToy, {'children_names'}, [self.t2.pk]],
                ['exit']
            ])
        except AssertionError:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultToy, {'children_names'}, [self.t2.pk]],
                ['update', DefaultChild, {'toy_names'}, [self.c2.pk]],
                ['exit']
            ])
        RECORDED.clear()

        # empty clear trigger nothing
        self.c2.toys.clear()
        self.assertEqual(RECORDED, [])

        # non-empty clear updates DefaultChild.toy_names & DefaultToy.children_names
        self.c1.toys.clear()
        try:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultChild, {'toy_names'}, [self.c1.pk]],  # updates may flip positions
                ['update', DefaultToy, {'children_names'}, [self.t1.pk]],
                ['exit']
            ])
        except AssertionError:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultToy, {'children_names'}, [self.t1.pk]],
                ['update', DefaultChild, {'toy_names'}, [self.c1.pk]],
                ['exit']
            ])
        RECORDED.clear()

        # set to empty updates DefaultChild.toy_names & DefaultToy.children_names
        self.c1.toys.set([self.t1, self.t2])
        try:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultChild, {'toy_names'}, [self.c1.pk]],  # updates may flip positions
                ['update', DefaultToy, {'children_names'}, [self.t1.pk, self.t2.pk]],
                ['exit']
            ])
        except AssertionError:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultToy, {'children_names'}, [self.t1.pk, self.t2.pk]],
                ['update', DefaultChild, {'toy_names'}, [self.c1.pk]],
                ['exit']
            ])
        RECORDED.clear()

        # set to non-empty updates DefaultChild.toy_names & DefaultToy.children_names on all 4 ends
        self.c2.toys.set([self.t1, self.t2])
        try:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultChild, {'toy_names'}, [self.c2.pk]],  # updates may flip positions
                ['update', DefaultToy, {'children_names'}, [self.t1.pk, self.t2.pk]],
                ['exit']
            ])
        except AssertionError:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultToy, {'children_names'}, [self.t1.pk, self.t2.pk]],
                ['update', DefaultChild, {'toy_names'}, [self.c2.pk]],
                ['exit']
            ])
        RECORDED.clear()

    def test_m2m_child_toy_reverse(self):
        RECORDED.clear()
        # add t2 to c2 updates DefaultChild.toy_names & DefaultToy.children_names
        self.t2.children.add(self.c2)
        try:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultChild, {'toy_names'}, [self.c2.pk]],  # updates may flip positions
                ['update', DefaultToy, {'children_names'}, [self.t2.pk]],
                ['exit']
            ])
        except AssertionError:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultToy, {'children_names'}, [self.t2.pk]],
                ['update', DefaultChild, {'toy_names'}, [self.c2.pk]],
                ['exit']
            ])
        RECORDED.clear()

        # remove t2 from c2 updates DefaultChild.toy_names & DefaultToy.children_names
        self.t2.children.remove(self.c2)
        try:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultChild, {'toy_names'}, [self.c2.pk]],  # updates may flip positions
                ['update', DefaultToy, {'children_names'}, [self.t2.pk]],
                ['exit']
            ])
        except AssertionError:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultToy, {'children_names'}, [self.t2.pk]],
                ['update', DefaultChild, {'toy_names'}, [self.c2.pk]],
                ['exit']
            ])
        RECORDED.clear()

        # empty clear trigger nothing
        self.t2.children.clear()
        self.assertEqual(RECORDED, [])

        # non-empty clear updates DefaultChild.toy_names & DefaultToy.children_names
        self.t1.children.clear()
        try:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultChild, {'toy_names'}, [self.c1.pk]],  # updates may flip positions
                ['update', DefaultToy, {'children_names'}, [self.t1.pk]],
                ['exit']
            ])
        except AssertionError:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultToy, {'children_names'}, [self.t1.pk]],
                ['update', DefaultChild, {'toy_names'}, [self.c1.pk]],
                ['exit']
            ])
        RECORDED.clear()

        # set to empty updates DefaultChild.toy_names & DefaultToy.children_names
        self.t1.children.set([self.c1, self.c2])
        try:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultChild, {'toy_names'}, [self.c1.pk, self.c2.pk]],  # updates may flip positions
                ['update', DefaultToy, {'children_names'}, [self.t1.pk]],
                ['exit']
            ])
        except AssertionError:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultToy, {'children_names'}, [self.t1.pk]],
                ['update', DefaultChild, {'toy_names'}, [self.c1.pk, self.c2.pk]],
                ['exit']
            ])
        RECORDED.clear()

        # set to non-empty updates DefaultChild.toy_names & DefaultToy.children_names on all 4 ends
        self.t2.children.set([self.c1, self.c2])
        try:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultChild, {'toy_names'}, [self.c1.pk, self.c2.pk]],  # updates may flip positions
                ['update', DefaultToy, {'children_names'}, [self.t2.pk]],
                ['exit']
            ])
        except AssertionError:
            self.assertEqual(RECORDED, [
                ['start'],
                ['update', DefaultToy, {'children_names'}, [self.t2.pk]],
                ['update', DefaultChild, {'toy_names'}, [self.c1.pk, self.c2.pk]],
                ['exit']
            ])
        RECORDED.clear()
