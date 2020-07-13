from django.test import TestCase
from ..models import ChildModel, ChildModel2


class MultiTableInheritanceModel(TestCase):
    def test_computed_field_on_multi_table_inheritance_model(self):
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
