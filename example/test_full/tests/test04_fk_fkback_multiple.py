from .base import GenericModelTestBase, MODELS


class MultipleDependenciesOne(GenericModelTestBase):
    def setUp(self):
        self.setDeps({
            # fk + fk + fk_back + fk_back
            'C': {'depends': [('self', ['name']), ('f_cb.f_ba.ag_f.gd_f', ['name']), ('cd_f.de_f', ['name'])],
                  'func': lambda self: self.name + ''.join(
                      MODELS['D'].objects.filter(f_dg__in=MODELS['G'].objects.filter(
                          f_ga=self.f_cb.f_ba)).values_list('name', flat=True)) + ''.join(
                      MODELS['E'].objects.filter(f_ed__in=self.cd_f.all()).values_list('name', flat=True)
                  )},
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
        self.g = self.models.G(name='g', f_gf=self.f, f_ga=self.a)
        self.g.save()
        self.d.f_dg = self.g
        self.d.save()

    def tearDown(self):
        self.resetDeps()

    def test_C_insert(self):
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cde')

    def test_C_update(self):
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cde')
        # change D
        self.d.name = 'D'
        self.d.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cDe')
        # add new D
        new_d = self.models.D(name='d2', f_dg=self.g)
        new_d.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cDd2e')
        # change E
        self.e.name = 'E'
        self.e.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cDd2E')
        # add new E
        new_e = self.models.E(name="e2", f_ed=self.d)
        new_e.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cDd2Ee2')

    def test_C_update_deletes(self):
        # change D
        self.d.name = 'D'
        self.d.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cDe')
        # add new D
        new_d = self.models.D(name='d2', f_dg=self.g)
        new_d.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cDd2e')
        # change E
        self.e.name = 'E'
        self.e.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cDd2E')
        # add new E
        new_e = self.models.E(name="e2", f_ed=self.d)
        new_e.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cDd2Ee2')
        # delete new_d
        new_d.delete()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cDEe2')
        # delete d - should remove D, E and e2
        self.d.delete()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'c')


class MultipleDependenciesTwo(GenericModelTestBase):
    def setUp(self):
        self.setDeps({
            # fk_back + fk_back + fk_back + fk + fk + fk
            'D': {'depends': [['self', ['name']], ['de_f.ef_f.fg_f.f_ga.f_ac.f_cb', ['name']], ['f_dc.f_cb', ['name']]],
                  'func': lambda self: self.name + ''.join(filter(bool, MODELS['G'].objects.filter(
                      f_gf__in=MODELS['F'].objects.filter(
                          f_fe__in=self.de_f.all())).values_list(
                      'f_ga__f_ac__f_cb__name', flat=True))) + self.f_dc.f_cb.name}
        })
        self.a = self.models.A(name='a')
        self.a.save()
        self.b = self.models.B(name='b', f_ba=self.a)
        self.b.save()
        self.c = self.models.C(name='c', f_cb=self.b)
        self.c.save()
        self.a.f_ac = self.c
        self.a.save()
        self.d = self.models.D(name='d', f_dc=self.c)
        self.d.save()
        self.e = self.models.E(name='e', f_ed=self.d)
        self.e.save()
        self.f = self.models.F(name='f', f_fe=self.e)
        self.f.save()
        self.g = self.models.G(name='g', f_gf=self.f, f_ga=self.a)
        self.g.save()

    def tearDown(self):
        self.resetDeps()

    def test_D_insert(self):
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dbb')

    def test_D_update(self):
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dbb')
        # change B --> should change both deps
        self.b.name = 'B'
        self.b.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dBB')
        # add new A, B and C, change f_ga
        new_b = self.models.B(name='b2')
        new_b.save()
        new_c = self.models.C(name='c2', f_cb=new_b)
        new_c.save()
        new_a = self.models.A(name='A', f_ac=new_c)
        new_a.save()
        self.g.f_ga = new_a
        self.g.save()
        self.d.refresh_from_db()
        # this should only change the "first" B dep
        self.assertEqual(self.d.comp, 'db2B')

    def test_D_update_deletes(self):
        # change B --> should change both deps
        self.b.name = 'B'
        self.b.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dBB')
        # add new A, B and C, change f_ga
        new_b = self.models.B(name='b2')
        new_b.save()
        new_c = self.models.C(name='c2', f_cb=new_b)
        new_c.save()
        new_a = self.models.A(name='A', f_ac=new_c)
        new_a.save()
        self.g.f_ga = new_a
        self.g.save()
        self.d.refresh_from_db()
        # this should only change the "first" B dep
        self.assertEqual(self.d.comp, 'db2B')
        # delete new_b - should remove b2
        new_b.delete()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dB')
