# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from base import GenericModelTestBase, MODELS


class ForeignKeyBackDependencies(GenericModelTestBase):
    """
    Test cases for foreign key back relations.
    """
    def setUp(self):
        self.setDeps({
            # deps only to itself
            'G': {'func': lambda self: self.name},
            # one fk back step deps to comp field
            'F': {'depends': ['fg_f#comp'],
                  'func': lambda self: self.name + ''.join(self.fg_f.all().values_list('comp', flat=True))},
            'E': {'depends': ['ef_f#comp'],
                  'func': lambda self: self.name + ''.join(self.ef_f.all().values_list('comp', flat=True))},
            # multi fk back steps deps to non comp field
            'C': {'depends': ['cd_f.de_f#name'],
                  'func': lambda self: self.name + ''.join(
                      MODELS['E'].objects.filter(f_ed__f_dc=self).values_list('name', flat=True))},
            # multi fk back steps deps to comp field
            'D': {'depends': ['de_f.ef_f.fg_f#comp'],
                  'func': lambda self: self.name + ''.join(
                      MODELS['G'].objects.filter(f_gf__f_fe__f_ed=self).values_list('comp', flat=True))},
        })
        self.a = self.models.A(name='a')
        self.a.save()
        self.b = self.models.B(name='b', f_ba=self.a)
        self.b.save()
        self.c = self.models.C(name='c', f_cb=self.b)
        self.c.save()
        self.d = self.models.D(name='d', f_dc=self.c)
        self.d.save()
        self.e = self.models.E(name='e', f_ed=self.d)
        self.e.save()
        self.f = self.models.F(name='f', f_fe=self.e)
        self.f.save()
        self.g = self.models.G(name='g', f_gf=self.f)
        self.g.save()

    def tearDown(self):
        self.resetDeps()

    def test_insert(self):
        self.f.refresh_from_db()
        self.e.refresh_from_db()
        self.assertEqual(self.g.comp, 'g')
        self.assertEqual(self.f.comp, 'fg')
        self.assertEqual(self.e.comp, 'efg')

    def test_bubbling_updates(self):
        self.g.name = 'G'
        self.g.save()
        # need to reload data from db
        self.f.refresh_from_db()
        self.e.refresh_from_db()
        self.assertEqual(self.g.comp, 'G')
        self.assertEqual(self.f.comp, 'fG')
        self.assertEqual(self.e.comp, 'efG')

    def test_bubbling_update_without_refresh_on_save(self):
        # bubbling update without refresh should work on save
        self.g.name = 'G'
        self.g.save()
        self.f.name = 'F'
        self.f.save()
        self.e.name = 'E'
        self.e.save()
        self.assertEqual(self.g.comp, 'G')
        self.assertEqual(self.f.comp, 'FG')
        self.assertEqual(self.e.comp, 'EFG')

    def test_fkback_over_multiple_models_insert(self):
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'ce')

    def test_fkback_over_multiple_models_update(self):
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'ce')
        new_e = self.models.E(name='E', f_ed=self.d)
        new_e.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'ceE')

    def test_multiple_fk_deps_insert(self):
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dg')

    def test_multiple_fk_deps_update(self):
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dg')
        new_g = self.models.G(name='G', f_gf=self.f)
        new_g.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dgG')
