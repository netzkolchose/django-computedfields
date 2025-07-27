from django.test import TestCase
from .. import models


class ComputedField(TestCase):
    def setUp(self):
        self.obj1 = models.FactorySimple.objects.create(a=10, b=20)
        self.obj2 = models.FactorySimple.objects.create(a=100, b=200)
      
    def test_create(self):
        self.assertEqual(self.obj1.c, 30)
        self.assertEqual(self.obj1.c, self.obj1.a + self.obj1.b)
        self.assertEqual(self.obj1.d, 200)
        self.assertEqual(self.obj1.d, self.obj1.a * self.obj1.b)
        self.obj2.refresh_from_db()
        self.assertEqual(self.obj2.c, 300)
        self.assertEqual(self.obj2.c, self.obj2.a + self.obj2.b)
        self.assertEqual(self.obj2.d, 20000)
        self.assertEqual(self.obj2.d, self.obj2.a * self.obj2.b)
    
    def test_alter(self):
        self.obj1.b = 30
        self.obj1.save()
        self.assertEqual(self.obj1.c, 40)
        self.assertEqual(self.obj1.c, self.obj1.a + self.obj1.b)
        self.assertEqual(self.obj1.d, 300)
        self.assertEqual(self.obj1.d, self.obj1.a * self.obj1.b)
        self.obj2.b = 300
        self.obj2.save()
        self.obj2.refresh_from_db()
        self.assertEqual(self.obj2.c, 400)
        self.assertEqual(self.obj2.c, self.obj2.a + self.obj2.b)
        self.assertEqual(self.obj2.d, 30000)
        self.assertEqual(self.obj2.d, self.obj2.a * self.obj2.b)


from computedfields.models import not_computed
class ComputedFieldNC(TestCase):
    def setUp(self):
        with not_computed(recover=True):
            self.obj1 = models.FactorySimple.objects.create(a=10, b=20)
            self.obj2 = models.FactorySimple.objects.create(a=100, b=200)
        self.obj1.refresh_from_db()
        self.obj2.refresh_from_db()

    def test_create(self):
        self.assertEqual(self.obj1.c, 30)
        self.assertEqual(self.obj1.c, self.obj1.a + self.obj1.b)
        self.assertEqual(self.obj1.d, 200)
        self.assertEqual(self.obj1.d, self.obj1.a * self.obj1.b)
        self.obj2.refresh_from_db()
        self.assertEqual(self.obj2.c, 300)
        self.assertEqual(self.obj2.c, self.obj2.a + self.obj2.b)
        self.assertEqual(self.obj2.d, 20000)
        self.assertEqual(self.obj2.d, self.obj2.a * self.obj2.b)
    
    def test_alter(self):
        with not_computed(recover=True):
            self.obj1.b = 30
            self.obj1.save()
        self.obj1.refresh_from_db()
        self.assertEqual(self.obj1.c, 40)
        self.assertEqual(self.obj1.c, self.obj1.a + self.obj1.b)
        self.assertEqual(self.obj1.d, 300)
        self.assertEqual(self.obj1.d, self.obj1.a * self.obj1.b)
        with not_computed(recover=True):
            self.obj2.b = 300
            self.obj2.save()
        self.obj2.refresh_from_db()
        self.assertEqual(self.obj2.c, 400)
        self.assertEqual(self.obj2.c, self.obj2.a + self.obj2.b)
        self.assertEqual(self.obj2.d, 30000)
        self.assertEqual(self.obj2.d, self.obj2.a * self.obj2.b)
