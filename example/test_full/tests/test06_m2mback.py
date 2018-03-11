# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from .base import GenericModelTestBase


def h(f):
    def wrap(self):
        if not self.pk:
            return ''
        return f(self)
    return wrap


def A_comp(self):
    if not self.pk:
        return ''
    s = self.name
    if self.ab_m.first():
        if self.ab_m.first().bc_m.last():
            s += self.ab_m.first().bc_m.last().name
        else:
            s += '+'
    else:
        s += '-'
    return s


def B_comp(self):
    if not self.pk:
        return ''
    s = self.name
    if self.bc_m:
        s += ''.join(self.bc_m.all().values_list('name', flat=True))
    else:
        s += '-'
    return s


class M2MBackDependencies(GenericModelTestBase):
    def setUp(self):
        self.setDeps({
            'A': {'depends': ['ab_m.bc_m#name'],
                  'func': A_comp},
            'B': {'depends': ['bc_m#name'],
                  'func': B_comp},
            'C': {'func': lambda self: self.name}
        })
        self.a1 = self.models.A(name='a1')
        self.a1.save()
        self.a2 = self.models.A(name='a2')
        self.a2.save()
        self.a3 = self.models.A(name='a3')
        self.a3.save()
        self.b1 = self.models.B(name='b1')
        self.b1.save()
        self.b1.m_ba.add(self.a1, self.a2, self.a3)
        self.b2 = self.models.B(name='b2')
        self.b2.save()
        self.b2.m_ba.add(self.a1, self.a2, self.a3)
        self.b3 = self.models.B(name='b3')
        self.b3.save()
        self.b3.m_ba.add(self.a1, self.a2, self.a3)
        self.c1 = self.models.C(name='c1')
        self.c1.save()
        self.c1.m_cb.add(self.b1, self.b2, self.b3)
        self.c2 = self.models.C(name='c2')
        self.c2.save()
        self.c2.m_cb.add(self.b1, self.b2, self.b3)
        self.c3 = self.models.C(name='c3')
        self.c3.save()
        self.c3.m_cb.add(self.b1, self.b2, self.b3)

    def tearDown(self):
        self.resetDeps()

    def test_insert(self):
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1c1c2c3')
        self.assertEqual(self.b2.comp, 'b2c1c2c3')
        self.assertEqual(self.b3.comp, 'b3c1c2c3')
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.a3.refresh_from_db()
        self.assertEqual(self.a1.comp, 'a1c3')
        self.assertEqual(self.a2.comp, 'a2c3')
        self.assertEqual(self.a3.comp, 'a3c3')

    def test_create_reverse(self):
        # create new c in b1
        self.b1.bc_m.create(name='c4')
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1c1c2c3c4')
        self.assertEqual(self.b2.comp, 'b2c1c2c3')
        self.assertEqual(self.b3.comp, 'b3c1c2c3')
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.a3.refresh_from_db()
        self.assertEqual(self.a1.comp, 'a1c4')
        self.assertEqual(self.a2.comp, 'a2c4')
        self.assertEqual(self.a3.comp, 'a3c4')

    def test_set_reverse(self):
        # set new c4 c5 in b1
        new_c4 = self.models.C(name='c4')
        new_c4.save()
        new_c5 = self.models.C(name='c5')
        new_c5.save()
        self.b1.bc_m.set([new_c4, new_c5])
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1c4c5')
        self.assertEqual(self.b2.comp, 'b2c1c2c3')
        self.assertEqual(self.b3.comp, 'b3c1c2c3')
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.a3.refresh_from_db()
        self.assertEqual(self.a1.comp, 'a1c5')
        self.assertEqual(self.a2.comp, 'a2c5')
        self.assertEqual(self.a3.comp, 'a3c5')

    def test_set_normal(self):
        # set new bs from c3 - should remove c3 from a.comp
        new_b4 = self.models.B(name='b4')
        new_b4.save()
        new_b5 = self.models.B(name='b5')
        new_b5.save()
        self.c3.m_cb.set([new_b4, new_b5])
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.a3.refresh_from_db()
        self.assertEqual(self.a1.comp, 'a1c2')
        self.assertEqual(self.a2.comp, 'a2c2')
        self.assertEqual(self.a3.comp, 'a3c2')

    def test_update(self):
        self.c1.name = 'C1'
        self.c1.save()
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1C1c2c3')
        self.assertEqual(self.b2.comp, 'b2C1c2c3')
        self.assertEqual(self.b3.comp, 'b3C1c2c3')
        self.c3.name = 'C3'
        self.c3.save()
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.a3.refresh_from_db()
        self.assertEqual(self.a1.comp, 'a1C3')
        self.assertEqual(self.a2.comp, 'a2C3')
        self.assertEqual(self.a3.comp, 'a3C3')
        new_c = self.models.C(name='c4')
        new_c.save()
        self.b1.bc_m.add(new_c)
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.a3.refresh_from_db()
        self.assertEqual(self.a1.comp, 'a1c4')
        self.assertEqual(self.a2.comp, 'a2c4')
        self.assertEqual(self.a3.comp, 'a3c4')

    def test_deletes(self):
        # delete c1 - should remove c1 from bs
        self.c1.delete()
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1c2c3')
        self.assertEqual(self.b2.comp, 'b2c2c3')
        self.assertEqual(self.b3.comp, 'b3c2c3')
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.a3.refresh_from_db()
        self.assertEqual(self.a1.comp, 'a1c3')
        self.assertEqual(self.a2.comp, 'a2c3')
        self.assertEqual(self.a3.comp, 'a3c3')
        # delete c3 - should remove c3 from bs and change as to c2
        self.c3.delete()
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1c2')
        self.assertEqual(self.b2.comp, 'b2c2')
        self.assertEqual(self.b3.comp, 'b3c2')
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.a3.refresh_from_db()
        self.assertEqual(self.a1.comp, 'a1c2')
        self.assertEqual(self.a2.comp, 'a2c2')
        self.assertEqual(self.a3.comp, 'a3c2')

    def test_remove_reverse(self):
        # remove c2, c3 from b1
        self.b1.bc_m.remove(self.c2, self.c3)
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1c1')
        self.assertEqual(self.b2.comp, 'b2c1c2c3')
        self.assertEqual(self.b3.comp, 'b3c1c2c3')
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.a3.refresh_from_db()
        self.assertEqual(self.a1.comp, 'a1c1')
        self.assertEqual(self.a2.comp, 'a2c1')
        self.assertEqual(self.a3.comp, 'a3c1')

    def test_remove_normal(self):
        # remove a1 from all b1
        # remove b2 from c3
        self.b1.m_ba.remove(self.a1)
        self.c3.m_cb.remove(self.b2)
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.a3.refresh_from_db()
        self.assertEqual(self.a1.comp, 'a1c2')
        self.assertEqual(self.a2.comp, 'a2c3')
        self.assertEqual(self.a3.comp, 'a3c3')

    def test_clear_reverse(self):
        # clear cs in b1
        self.b1.bc_m.clear()
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1')
        self.assertEqual(self.b2.comp, 'b2c1c2c3')
        self.assertEqual(self.b3.comp, 'b3c1c2c3')
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.a3.refresh_from_db()
        self.assertEqual(self.a1.comp, 'a1+')
        self.assertEqual(self.a2.comp, 'a2+')
        self.assertEqual(self.a3.comp, 'a3+')

    def test_clear_normal(self):
        # clear bs in c3
        self.c3.m_cb.clear()
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1c1c2')
        self.assertEqual(self.b2.comp, 'b2c1c2')
        self.assertEqual(self.b3.comp, 'b3c1c2')
        self.a1.refresh_from_db()
        self.a2.refresh_from_db()
        self.a3.refresh_from_db()
        self.assertEqual(self.a1.comp, 'a1c2')
        self.assertEqual(self.a2.comp, 'a2c2')
        self.assertEqual(self.a3.comp, 'a3c2')
