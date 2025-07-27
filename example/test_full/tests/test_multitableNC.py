from django.test import TestCase
from ..models import MtDerived, MtRelated, MtDerived2, MtSubDerived, MultiBase, MultiA, MultiB, MultiC
from ..models import ChildModel, ChildModel2, ParentModel, DependsOnParent, DependsOnParentComputed
from ..models import MtPtrBase, MtPtrDerived
from computedfields.models import update_dependent
from computedfields.models import not_computed


class TestMultiTableNC(TestCase):
    def setUp(self):
        with not_computed(recover=True):
            self.r1 = MtRelated.objects.create(name='r1')
            self.r2 = MtRelated.objects.create(name='r2')
            self.d = MtDerived.objects.create(name='b', dname='d', rel_on_base=self.r1, rel_on_derived=self.r2)
            self.d_2 = MtDerived2.objects.create(name='b', z='z', rel_on_base=self.r1)
            self.s = MtSubDerived.objects.create(name='b', z='z', rel_on_base=self.r1, sub='I am sub!')
        self.r1.refresh_from_db()
        self.r2.refresh_from_db()
        self.d.refresh_from_db()
        self.d_2.refresh_from_db()
        self.s.refresh_from_db()

    def test_init(self):
        self.d.refresh_from_db()
        self.assertEqual(self.d.upper, 'B')
        self.assertEqual(self.d.upper_combined, 'B/D#r1:r2')
        self.assertEqual(self.d.pulled, '###B/D#r1:r2')
        self.d_2.refresh_from_db()
        self.assertEqual(self.d_2.pulled, 'D2:z')
        self.s.refresh_from_db()
        self.assertEqual(self.s.pulled, 'SUB pulled:I am sub!')

    def test_rename_base(self):
        with not_computed(recover=True):
            self.d.name = 'bb'
            self.d.save(update_fields=['name'])
        self.d.refresh_from_db()
        self.assertEqual(self.d.upper_combined, 'BB/D#r1:r2')
        self.assertEqual(self.d.pulled, '###BB/D#r1:r2')

    def test_update_from_r1(self):
        with not_computed(recover=True):
            self.r1.name = 'rr1'
            self.r1.save(update_fields=['name'])
        self.d.refresh_from_db()
        self.assertEqual(self.d.upper_combined, 'B/D#rr1:r2')
        self.assertEqual(self.d.pulled, '###B/D#rr1:r2')

    def test_update_from_r2(self):
        with not_computed(recover=True):
            self.r2.name = 'rr2'
            self.r2.save(update_fields=['name'])
        self.d.refresh_from_db()
        self.assertEqual(self.d.upper_combined, 'B/D#r1:rr2')
        self.assertEqual(self.d.pulled, '###B/D#r1:rr2')

    def test_update_z_on_d2(self):
        with not_computed(recover=True):
            self.d_2.z = 'zzzzz'
            self.d_2.save(update_fields=['z'])
        self.d_2.refresh_from_db()
        self.assertEqual(self.d_2.pulled, 'D2:zzzzz')

    def test_change_sub(self):
        with not_computed(recover=True):
            self.s.sub = 'does it work?'
            self.s.save(update_fields=['sub'])
        self.s.refresh_from_db()
        self.assertEqual(self.s.pulled, 'SUB pulled:does it work?')


class MultiTableInheritanceModelNC(TestCase):
    def test_depends_on_child_model(self):
        with not_computed(recover=True):
            child1 = ChildModel.objects.create(username="Child")
        child1.refresh_from_db()
        self.assertEqual(child1.name, "Child")

        with not_computed(recover=True):
            child1.username = "Kid"
            child1.save()

        child1.refresh_from_db()
        self.assertEqual(child1.name, "Kid")

        with not_computed(recover=True):
            child2 = ChildModel2.objects.create(pseudo="Pseudo")
        child2.refresh_from_db()
        self.assertEqual(child2.name, "Pseudo")

        with not_computed(recover=True):
            child2.pseudo = "Kid"
            child2.save()

        child2.refresh_from_db()
        self.assertEqual(child2.name, "Kid")

    def test_parent_depends_on_self(self):
        with not_computed(recover=True):
            child = ChildModel.objects.create(username="Child", x=12, y=67)
        child.refresh_from_db()
        self.assertEqual(child.name, "Child")
        self.assertEqual(child.z, 12+67)

        with not_computed(recover=True):
            child.y = 8
            child.save()

        child.refresh_from_db()
        self.assertEqual(child.z, 20)

    def test_child_depends_on_self(self):
        with not_computed(recover=True):
            child = ChildModel.objects.create(username="Child", a=12, b=67)
        child.refresh_from_db()
        self.assertEqual(child.name, "Child")
        self.assertEqual(child.c, 12+67)

        with not_computed(recover=True):
            child.b = 8
            child.save()

        child.refresh_from_db()
        self.assertEqual(child.c, 20)

    def test_child_depends_on_self_and_parent(self):
        with not_computed(recover=True):
            child = ChildModel2.objects.create(pseudo="Child", x=12, y=67)
        child.refresh_from_db()
        self.assertEqual(child.name, "Child")
        self.assertEqual(child.z, 12+67)
        self.assertEqual(child.other_name, "12Child79")

        with not_computed(recover=True):
            child.x = 10
            child.save()

        child.refresh_from_db()
        self.assertEqual(child.z, 77)
        self.assertEqual(child.other_name, "10Child77")

    def test_other_class_depends_on_parent(self):
        with not_computed(recover=True):
            parent = ParentModel.objects.create(x=3, y=5)
        parent.refresh_from_db()
        self.assertEqual(parent.z, 8)
        self.assertIsNone(parent.name)

        with not_computed(recover=True):
            other = DependsOnParent.objects.create(parent=parent)
        other.refresh_from_db()
        self.assertEqual(other.x2, 6)

        with not_computed(recover=True):
            parent.x = 7
            parent.save()
        parent.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(parent.z, 12)
        self.assertEqual(other.x2, 14)

    def test_other_class_depends_on_parent_computed(self):
        with not_computed(recover=True):
            parent = ParentModel.objects.create(x=3, y=5)
        parent.refresh_from_db()
        self.assertEqual(parent.z, 8)
        self.assertIsNone(parent.name)

        with not_computed(recover=True):
            other = DependsOnParentComputed.objects.create(parent=parent)
        other.refresh_from_db()
        self.assertEqual(other.z2, 16)

        with not_computed(recover=True):
            parent.x = 7
            parent.save()
        parent.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(parent.z, 12)
        self.assertEqual(other.z2, 24)

    def test_other_class_depends_on_parent_child(self):
        with not_computed(recover=True):
            child = ChildModel.objects.create(username="Child", x=3, y=5)
        child.refresh_from_db()
        self.assertEqual(child.z, 8)
        self.assertEqual(child.name, "Child")

        with not_computed(recover=True):
            other = DependsOnParent.objects.create(parent=child)
        other.refresh_from_db()
        self.assertEqual(other.x2, 6)

        with not_computed(recover=True):
            child.x = 7
            child.save()
        child.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(child.z, 12)
        self.assertEqual(other.x2, 14)

    def test_other_class_depends_on_parent_computed_child(self):
        with not_computed(recover=True):
            child = ChildModel.objects.create(username="Child", x=3, y=5)
        child.refresh_from_db()
        self.assertEqual(child.z, 8)
        self.assertEqual(child.name, "Child")

        with not_computed(recover=True):
            other = DependsOnParentComputed.objects.create(parent=child)
        other.refresh_from_db()
        self.assertEqual(other.z2, 16)
        with not_computed(recover=True):
            child.x = 7
            child.save()
        child.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(child.z, 12)
        self.assertEqual(other.z2, 24)


class TestMultiTableWithPtrNC(TestCase):
    def test_init(self):
        with not_computed(recover=True):
            d = MtPtrDerived.objects.create(basename='hello')
        d.refresh_from_db()
        self.assertEqual(d.comp, d.basename)

    def test_base_change(self):
        with not_computed(recover=True):
            for i in range(10):
                MtPtrDerived.objects.create(basename='D{}'.format(i))
            # work around ever increasing pks on postgres and mysql
            b = MtPtrBase.objects.all().order_by('pk').first()
            if not b:
                raise MtPtrBase.DoesNotExist
            b.basename = 'changed'
            b.save(update_fields=['basename'])
        b.refresh_from_db()
        self.assertEqual(b.mtptrderived.comp, 'changed')

        with not_computed(recover=True):
            # create plain Basee object
            new_b = MtPtrBase.objects.create(basename='hello')
            # mass action
            MtPtrBase.objects.all().update(basename='new value')
            update_dependent(MtPtrBase.objects.all(), update_fields=['basename'])

        self.assertEqual(list(MtPtrDerived.objects.all().values_list('basename', flat=True)), ['new value'] * 10)


class TestMultiTableUpPullingExampleNC(TestCase):
    def setUp(self) -> None:
        with not_computed(recover=True):
            self.base = MultiBase.objects.create()
            self.a = MultiA.objects.create()
            self.b = MultiB.objects.create()
            self.c = MultiC.objects.create()
        self.base.refresh_from_db()
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.c.refresh_from_db()

    def test_init(self):
        self.base.refresh_from_db()
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.c.refresh_from_db()
        self.assertEqual(self.base.comp, '')
        self.assertEqual(self.a.comp, 'a')
        self.assertEqual(self.b.comp, 'b')
        self.assertEqual(self.c.comp, 'sub-c')

    def test_update(self):
        with not_computed(recover=True):
            self.a.f_on_a = 'A'
            self.a.save()
        self.a.refresh_from_db()
        self.assertEqual(self.a.comp, 'A')
        with not_computed(recover=True):
            self.b.f_on_b = 'B'
            self.b.save(update_fields=['f_on_b'])
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'B')
        with not_computed(recover=True):
            self.c.f_on_c = 'C'
            self.c.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'C')
        with not_computed(recover=True):
            self.c.f_on_c = 'CC'
            self.c.save(update_fields=['f_on_c'])
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'CC')
