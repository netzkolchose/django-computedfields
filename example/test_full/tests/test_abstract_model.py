from django.test import TestCase
from ..models import Concrete, ParentOfAbstract, ConcreteChild, ConcreteSubchild, ConcreteWithForeignKey, ConcreteWithForeignKey2


class AbstractModel(TestCase):
    def test_computed_field_on_abstract_model(self):
        concrete = Concrete.objects.create(a=300, b=14)
        self.assertEqual(concrete.c, 314)

    def test_foreign_key_on_abstract_model(self):
        target = Concrete.objects.create()
        concrete_target = Concrete.objects.create()

        concrete_with_fk = ConcreteWithForeignKey.objects.create(target=target, concrete_target=concrete_target)

        target.a = 101
        target.b = 37
        target.d = 15
        target.save()
        concrete_target.a = 201
        concrete_target.b = 137
        concrete_target.d = 115
        concrete_target.save()

        concrete_with_fk.refresh_from_db()

        self.assertEqual(concrete_with_fk.target_d, 15)
        self.assertEqual(concrete_with_fk.target_c, 138)
        self.assertEqual(concrete_with_fk.target_c_proxy, 138)
        self.assertEqual(concrete_with_fk.d, 15)
        self.assertEqual(concrete_with_fk.c, 138)
        self.assertEqual(concrete_with_fk.c_proxy, 138)
        self.assertEqual(concrete_with_fk.concrete_d, 115)
        self.assertEqual(concrete_with_fk.concrete_c, 338)
        self.assertEqual(concrete_with_fk.concrete_c_proxy, 338)

    def test_inverse_relationship_on_abstract_model(self):
        parent = ParentOfAbstract.objects.create()

        self.assertEqual(parent.children_count, 0)
        self.assertEqual(parent.subchildren_count, 0)
        self.assertEqual(parent.subchildren_count_proxy, 0)

        child1 = ConcreteChild.objects.create(parent=parent)
        child2 = ConcreteChild.objects.create(parent=parent)

        self.assertEqual(child1.subchildren_count, 0)
        self.assertEqual(child2.subchildren_count, 0)

        ConcreteSubchild.objects.create(subparent=child1)
        ConcreteSubchild.objects.create(subparent=child2)
        ConcreteSubchild.objects.create(subparent=child2)

        child1.refresh_from_db()
        child2.refresh_from_db()
        parent.refresh_from_db()

        self.assertEqual(child1.subchildren_count, 1)
        self.assertEqual(child2.subchildren_count, 2)

        self.assertEqual(parent.children_count, 2)
        self.assertEqual(parent.subchildren_count, 3)
        self.assertEqual(parent.subchildren_count_proxy, 3)

    def test_multi_concrete_models_inheriting_same_abstract_model(self):
        target = Concrete.objects.create()
        concrete_target = Concrete.objects.create()

        concrete = ConcreteWithForeignKey.objects.create(target=target, concrete_target=concrete_target)
        concrete2 = ConcreteWithForeignKey2.objects.create(target=target)

        target.d = 1337
        target.save()

        concrete.refresh_from_db()
        concrete2.refresh_from_db()

        self.assertEqual(concrete.d, 1337)
        self.assertEqual(concrete2.d2, 1337)


from computedfields.models import not_computed
class AbstractModelNC(TestCase):
    def test_computed_field_on_abstract_model(self):
        with not_computed(recover=True):
            concrete = Concrete.objects.create(a=300, b=14)
        concrete.refresh_from_db()
        self.assertEqual(concrete.c, 314)

    def test_foreign_key_on_abstract_model(self):
        with not_computed(recover=True):
            target = Concrete.objects.create()
            concrete_target = Concrete.objects.create()

            concrete_with_fk = ConcreteWithForeignKey.objects.create(target=target, concrete_target=concrete_target)

            target.a = 101
            target.b = 37
            target.d = 15
            target.save()
            concrete_target.a = 201
            concrete_target.b = 137
            concrete_target.d = 115
            concrete_target.save()

        concrete_with_fk.refresh_from_db()

        self.assertEqual(concrete_with_fk.target_d, 15)
        self.assertEqual(concrete_with_fk.target_c, 138)
        self.assertEqual(concrete_with_fk.target_c_proxy, 138)
        self.assertEqual(concrete_with_fk.d, 15)
        self.assertEqual(concrete_with_fk.c, 138)
        self.assertEqual(concrete_with_fk.c_proxy, 138)
        self.assertEqual(concrete_with_fk.concrete_d, 115)
        self.assertEqual(concrete_with_fk.concrete_c, 338)
        self.assertEqual(concrete_with_fk.concrete_c_proxy, 338)

    def test_inverse_relationship_on_abstract_model(self):
        with not_computed(recover=True):
            parent = ParentOfAbstract.objects.create()
        parent.refresh_from_db()

        self.assertEqual(parent.children_count, 0)
        self.assertEqual(parent.subchildren_count, 0)
        self.assertEqual(parent.subchildren_count_proxy, 0)

        with not_computed(recover=True):
            child1 = ConcreteChild.objects.create(parent=parent)
            child2 = ConcreteChild.objects.create(parent=parent)
        child1.refresh_from_db()
        child2.refresh_from_db()

        self.assertEqual(child1.subchildren_count, 0)
        self.assertEqual(child2.subchildren_count, 0)

        with not_computed(recover=True):
            ConcreteSubchild.objects.create(subparent=child1)
            ConcreteSubchild.objects.create(subparent=child2)
            ConcreteSubchild.objects.create(subparent=child2)

        child1.refresh_from_db()
        child2.refresh_from_db()
        parent.refresh_from_db()

        self.assertEqual(child1.subchildren_count, 1)
        self.assertEqual(child2.subchildren_count, 2)

        self.assertEqual(parent.children_count, 2)
        self.assertEqual(parent.subchildren_count, 3)
        self.assertEqual(parent.subchildren_count_proxy, 3)

    def test_multi_concrete_models_inheriting_same_abstract_model(self):
        with not_computed(recover=True):
            target = Concrete.objects.create()
            concrete_target = Concrete.objects.create()

            concrete = ConcreteWithForeignKey.objects.create(target=target, concrete_target=concrete_target)
            concrete2 = ConcreteWithForeignKey2.objects.create(target=target)

            target.d = 1337
            target.save()

        concrete.refresh_from_db()
        concrete2.refresh_from_db()

        self.assertEqual(concrete.d, 1337)
        self.assertEqual(concrete2.d2, 1337)
