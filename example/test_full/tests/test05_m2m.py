# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from base import GenericModelTestBase, MODELS


def h(f):
    def wrap(self):
        if not self.pk:
            return ''
        return f(self)
    return wrap


class M2MDependencies(GenericModelTestBase):
    def setUp(self):
        self.setDeps({
            'A': {'func': lambda self: self.name},
            'B': {'depends': ['m_ba#name'],
                  'func': h(lambda self: self.name + ''.join(
                      self.m_ba.all().values_list('name', flat=True)))},
            'C': {'depends': ['m_cb.m_ba#name'],
                  'func': h(lambda self: self.name + getattr(self.m_cb.first().m_ba.last(), 'name', '-'))}
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
        self.assertEqual(self.b1.comp, 'b1a1a2a3')
        self.assertEqual(self.b2.comp, 'b2a1a2a3')
        self.assertEqual(self.b3.comp, 'b3a1a2a3')
        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c3.refresh_from_db()
        self.assertEqual(self.c1.comp, 'c1a3')
        self.assertEqual(self.c2.comp, 'c2a3')
        self.assertEqual(self.c3.comp, 'c3a3')

    def test_insert_reverse(self):
        # insert new c to b1
        new_c = self.models.C(name='c4')
        new_c.save()
        self.b1.bc_m.add(new_c)
        new_c.refresh_from_db()
        self.assertEqual(new_c.comp, 'c4a3')

    def test_create(self):
        # create new a in b1
        self.b1.m_ba.create(name='a4')
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1a1a2a3a4')
        self.assertEqual(self.b2.comp, 'b2a1a2a3')
        self.assertEqual(self.b3.comp, 'b3a1a2a3')
        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c3.refresh_from_db()
        self.assertEqual(self.c1.comp, 'c1a4')
        self.assertEqual(self.c2.comp, 'c2a4')
        self.assertEqual(self.c3.comp, 'c3a4')

    def test_create_reverse(self):
        # create new c in b1
        self.b1.bc_m.create(name='c4')
        self.assertEqual(self.b1.bc_m.last().comp, 'c4a3')

    def test_set(self):
        # set new a4 a5 in b1
        new_a4 = self.models.A(name='a4')
        new_a4.save()
        new_a5 = self.models.A(name='a5')
        new_a5.save()
        self.b1.m_ba.set([new_a4, new_a5])
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1a4a5')
        self.assertEqual(self.b2.comp, 'b2a1a2a3')
        self.assertEqual(self.b3.comp, 'b3a1a2a3')
        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c3.refresh_from_db()
        self.assertEqual(self.c1.comp, 'c1a5')
        self.assertEqual(self.c2.comp, 'c2a5')
        self.assertEqual(self.c3.comp, 'c3a5')

    def test_set_reverse(self):
        # set new b in a3
        new_b = self.models.B(name='B')
        new_b.save()
        self.a3.ab_m.set([new_b])
        new_b.refresh_from_db()
        self.assertEqual(new_b.comp, 'Ba3')
        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c3.refresh_from_db()
        self.assertEqual(self.c1.comp, 'c1a2')
        self.assertEqual(self.c2.comp, 'c2a2')
        self.assertEqual(self.c3.comp, 'c3a2')

    def test_update(self):
        self.a1.name = 'A1'
        self.a1.save()
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1A1a2a3')
        self.assertEqual(self.b2.comp, 'b2A1a2a3')
        self.assertEqual(self.b3.comp, 'b3A1a2a3')
        self.a3.name = 'A3'
        self.a3.save()
        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c3.refresh_from_db()
        self.assertEqual(self.c1.comp, 'c1A3')
        self.assertEqual(self.c2.comp, 'c2A3')
        self.assertEqual(self.c3.comp, 'c3A3')
        new_a = self.models.A(name='a4')
        new_a.save()
        self.b1.m_ba.add(new_a)
        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c3.refresh_from_db()
        self.assertEqual(self.c1.comp, 'c1a4')
        self.assertEqual(self.c2.comp, 'c2a4')
        self.assertEqual(self.c3.comp, 'c3a4')

    def test_deletes(self):
        # delete a1 - should remove a1 from bs
        self.a1.delete()
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1a2a3')
        self.assertEqual(self.b2.comp, 'b2a2a3')
        self.assertEqual(self.b3.comp, 'b3a2a3')
        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c3.refresh_from_db()
        self.assertEqual(self.c1.comp, 'c1a3')
        self.assertEqual(self.c2.comp, 'c2a3')
        self.assertEqual(self.c3.comp, 'c3a3')
        # delete a3 - should remove a3 from bs and change cs to a2
        self.a3.delete()
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1a2')
        self.assertEqual(self.b2.comp, 'b2a2')
        self.assertEqual(self.b3.comp, 'b3a2')
        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c3.refresh_from_db()
        self.assertEqual(self.c1.comp, 'c1a2')
        self.assertEqual(self.c2.comp, 'c2a2')
        self.assertEqual(self.c3.comp, 'c3a2')

    def test_remove(self):
        # remove a2, a3 from b1
        self.b1.m_ba.remove(self.a2, self.a3)
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1a1')
        self.assertEqual(self.b2.comp, 'b2a1a2a3')
        self.assertEqual(self.b3.comp, 'b3a1a2a3')
        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c3.refresh_from_db()
        self.assertEqual(self.c1.comp, 'c1a1')
        self.assertEqual(self.c2.comp, 'c2a1')
        self.assertEqual(self.c3.comp, 'c3a1')

    def test_remove_reverse(self):
        # remove b1 from a3 - a2 should be last cs
        self.a3.ab_m.remove(self.b1)
        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c3.refresh_from_db()
        self.assertEqual(self.c1.comp, 'c1a2')
        self.assertEqual(self.c2.comp, 'c2a2')
        self.assertEqual(self.c3.comp, 'c3a2')

    def test_clear(self):
        # clear as in b1
        self.b1.m_ba.clear()
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1')
        self.assertEqual(self.b2.comp, 'b2a1a2a3')
        self.assertEqual(self.b3.comp, 'b3a1a2a3')
        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c3.refresh_from_db()
        self.assertEqual(self.c1.comp, 'c1-')
        self.assertEqual(self.c2.comp, 'c2-')
        self.assertEqual(self.c3.comp, 'c3-')

    def test_clear_reverse(self):
        # clear bs in a3
        self.a3.ab_m.clear()
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertEqual(self.b1.comp, 'b1a1a2')
        self.assertEqual(self.b2.comp, 'b2a1a2')
        self.assertEqual(self.b3.comp, 'b3a1a2')
        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c3.refresh_from_db()
        self.assertEqual(self.c1.comp, 'c1a2')
        self.assertEqual(self.c2.comp, 'c2a2')
        self.assertEqual(self.c3.comp, 'c3a2')