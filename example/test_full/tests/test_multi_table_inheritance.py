from django.test import TestCase
from ..models import ChildModel, ChildModel2


class MultiTableInheritanceModel(TestCase):
    def test_depends_on_child_model(self):
        child1 = ChildModel.objects.create(username="Child")
        child1.refresh_from_db()
        self.assertEqual(child1.name, "Child")

        child1.username = "Kid"
        child1.save()

        child1.refresh_from_db()

        self.assertEqual(child1.name, "Kid")

        child2 = ChildModel2.objects.create(pseudo="Pseudo")
        child2.refresh_from_db()
        self.assertEqual(child2.name, "Pseudo")

        child2.pseudo = "Kid"
        child2.save()

        child2.refresh_from_db()

        self.assertEqual(child2.name, "Kid")

    def test_parent_depends_on_self(self):
        child = ChildModel.objects.create(username="Child", x=12, y=67)
        child.refresh_from_db()
        self.assertEqual(child.name, "Child")
        self.assertEqual(child.z, 12+67)

        child.y = 8
        child.save()

        child.refresh_from_db()

        self.assertEqual(child.z, 20)

    def test_child_depends_on_self(self):
        child = ChildModel.objects.create(username="Child", a=12, b=67)
        child.refresh_from_db()
        self.assertEqual(child.name, "Child")
        self.assertEqual(child.c, 12+67)

        child.b = 8
        child.save()

        child.refresh_from_db()

        self.assertEqual(child.c, 20)

    def test_child_depends_on_self_and_parent(self):
        child = ChildModel2.objects.create(pseudo="Child", x=12, y=67)
        child.refresh_from_db()
        self.assertEqual(child.name, "Child")
        self.assertEqual(child.z, 12+67)
        self.assertEqual(child.other_name, "12Child79")

        child.x = 10
        child.save()

        child.refresh_from_db()

        self.assertEqual(child.z, 77)
        self.assertEqual(child.other_name, "10Child77")
