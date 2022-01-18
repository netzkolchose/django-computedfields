from django.test import TestCase
from ..models import DepBaseA, DepBaseB, DepSub1, DepSub2, DepSubFinal
from computedfields.models import update_dependent, preupdate_dependent


class TestUpdateDependency(TestCase):
    def setUp(self):
        self.ba1 = DepBaseA.objects.create()
        self.ba2 = DepBaseA.objects.create()
        self.bb1 = DepBaseB.objects.create()
        self.bb2 = DepBaseB.objects.create()

        self.s11 = DepSub1.objects.create(a=self.ba1, b=self.bb1)
        self.s12 = DepSub1.objects.create(a=self.ba2, b=self.bb2)

        self.s21 = DepSub2.objects.create(sub1=self.s11)
        self.s22 = DepSub2.objects.create(sub1=self.s12)

        self.sf1 = DepSubFinal.objects.create(sub2=self.s21, name='f1')
        self.sf2 = DepSubFinal.objects.create(sub2=self.s21, name='f2')
        self.sf3 = DepSubFinal.objects.create(sub2=self.s21, name='f3')
        self.sf4 = DepSubFinal.objects.create(sub2=self.s21, name='f4')
        self.sf5 = DepSubFinal.objects.create(sub2=self.s21, name='f5')

        self.sf6 = DepSubFinal.objects.create(sub2=self.s22, name='f6')
        self.sf7 = DepSubFinal.objects.create(sub2=self.s22, name='f7')
        self.sf8 = DepSubFinal.objects.create(sub2=self.s22, name='f8')
        self.sf9 = DepSubFinal.objects.create(sub2=self.s22, name='f9')
        self.sf0 = DepSubFinal.objects.create(sub2=self.s22, name='f0')

    def test_creation(self):
        self.ba1.refresh_from_db()
        self.ba2.refresh_from_db()
        self.bb1.refresh_from_db()
        self.bb2.refresh_from_db()
        self.assertEqual(self.ba1.final_proxy, 'f1f2f3f4f5')
        self.assertEqual(self.ba2.final_proxy, 'f6f7f8f9f0')
        self.assertEqual(self.bb1.final_proxy, 'f1f2f3f4f5')
        self.assertEqual(self.bb2.final_proxy, 'f6f7f8f9f0')
    
    def test_update_final(self):
        self.sf6.sub2 = self.s21
        self.sf6.save()

        self.ba1.refresh_from_db()
        self.ba2.refresh_from_db()
        self.bb1.refresh_from_db()
        self.bb2.refresh_from_db()
        self.assertEqual(self.ba1.final_proxy, 'f1f2f3f4f5f6')
        self.assertEqual(self.ba2.final_proxy, 'f7f8f9f0')
        self.assertEqual(self.bb1.final_proxy, 'f1f2f3f4f5f6')
        self.assertEqual(self.bb2.final_proxy, 'f7f8f9f0')
    
    def test_update_s2(self):
        self.s22.sub1 = self.s11
        self.s22.save()

        self.ba1.refresh_from_db()
        self.ba2.refresh_from_db()
        self.bb1.refresh_from_db()
        self.bb2.refresh_from_db()
        self.assertEqual(self.ba1.final_proxy, 'f1f2f3f4f5f6f7f8f9f0')
        self.assertEqual(self.ba2.final_proxy, '')
        self.assertEqual(self.bb1.final_proxy, 'f1f2f3f4f5f6f7f8f9f0')
        self.assertEqual(self.bb2.final_proxy, '')

    def test_update_s1(self):
        self.s12.b = self.bb1
        self.s12.save()

        self.ba1.refresh_from_db()
        self.ba2.refresh_from_db()
        self.bb1.refresh_from_db()
        self.bb2.refresh_from_db()
        self.assertEqual(self.ba1.final_proxy, 'f1f2f3f4f5')
        self.assertEqual(self.ba2.final_proxy, 'f6f7f8f9f0')
        self.assertEqual(self.bb1.final_proxy, 'f1f2f3f4f5f6f7f8f9f0')
        self.assertEqual(self.bb2.final_proxy, '')

    def test_update_bulk_final_name(self):
        # here old is not needed, since the QS is stable itself (only endpoint data changed),
        # thus all data changes correctly trigger updates
        DepSubFinal.objects.filter(sub2=self.s21).update(name='X')
        update_dependent(DepSubFinal.objects.filter(sub2=self.s21))

        self.ba1.refresh_from_db()
        self.ba2.refresh_from_db()
        self.bb1.refresh_from_db()
        self.bb2.refresh_from_db()
        self.assertEqual(self.ba1.final_proxy, 'XXXXX')
        self.assertEqual(self.ba2.final_proxy, 'f6f7f8f9f0')
        self.assertEqual(self.bb1.final_proxy, 'XXXXX')
        self.assertEqual(self.bb2.final_proxy, 'f6f7f8f9f0')
    
    def test_update_bulk_final_sub2(self):
        # this needs old handling - seems a good indicator for this is whether the QS changes itself
        # here: filter(sub2=self.s21) before vs. filter(sub2=self.s22) after the update
        old_relations = preupdate_dependent(DepSubFinal.objects.filter(sub2=self.s21))
        DepSubFinal.objects.filter(sub2=self.s21).update(sub2=self.s22)
        update_dependent(DepSubFinal.objects.filter(sub2=self.s22), old=old_relations)

        self.ba1.refresh_from_db()
        self.ba2.refresh_from_db()
        self.bb1.refresh_from_db()
        self.bb2.refresh_from_db()
        self.assertEqual(self.ba1.final_proxy, '')
        self.assertEqual(self.ba2.final_proxy, 'f1f2f3f4f5f6f7f8f9f0')
        self.assertEqual(self.bb1.final_proxy, '')
        self.assertEqual(self.bb2.final_proxy, 'f1f2f3f4f5f6f7f8f9f0')

    def test_update_bulk_s2(self):
        old_relations = preupdate_dependent(DepSub2.objects.filter(sub1=self.s12))
        DepSub2.objects.filter(sub1=self.s12).update(sub1=self.s11)
        update_dependent(DepSub2.objects.filter(sub1=self.s11), old=old_relations)

        self.ba1.refresh_from_db()
        self.ba2.refresh_from_db()
        self.bb1.refresh_from_db()
        self.bb2.refresh_from_db()
        self.assertEqual(self.ba1.final_proxy, 'f1f2f3f4f5f6f7f8f9f0')
        self.assertEqual(self.ba2.final_proxy, '')
        self.assertEqual(self.bb1.final_proxy, 'f1f2f3f4f5f6f7f8f9f0')
        self.assertEqual(self.bb2.final_proxy, '')

    def test_update_bulk_s1(self):
        old_relations = preupdate_dependent(DepSub1.objects.filter(b=self.bb2))
        DepSub1.objects.filter(b=self.bb2).update(b=self.bb1)
        update_dependent(DepSub1.objects.filter(b=self.bb1), old=old_relations)

        self.ba1.refresh_from_db()
        self.ba2.refresh_from_db()
        self.bb1.refresh_from_db()
        self.bb2.refresh_from_db()
        self.assertEqual(self.ba1.final_proxy, 'f1f2f3f4f5')
        self.assertEqual(self.ba2.final_proxy, 'f6f7f8f9f0')
        self.assertEqual(self.bb1.final_proxy, 'f1f2f3f4f5f6f7f8f9f0')
        self.assertEqual(self.bb2.final_proxy, '')
