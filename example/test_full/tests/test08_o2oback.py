from .base import GenericModelTestBase, MODELS

# copied and modified from test02_fkback


class ForeignKeyBackDependencies(GenericModelTestBase):
    """
    Test cases for foreign key back relations.
    """
    def setUp(self):
        self.setDeps({
            # deps only to itself
            'G': {'depends':[['self', ['name']]],
                  'func': lambda self: self.name},
            # one o2o back step deps to comp field
            'F': {'depends': [['self', ['name']], ['fg_o', ['comp']]],
                  'func': lambda self: self.name + getattr(getattr(self, 'fg_o', None), 'comp', '-')},
            'E': {'depends': [['self', ['name']], ['ef_o', ['comp']]],
                  'func': lambda self: self.name + getattr(getattr(self, 'ef_o', None), 'comp', '-')},
            # multi o2o back steps deps to non comp field
            'C': {'depends': [['self', ['name']], ['cd_o.de_o', ['name']]],
                  'func': lambda self: self.name + ''.join(
                      MODELS['E'].objects.filter(o_ed__o_dc=self).values_list('name', flat=True))},
            # multi o2o back steps deps to comp field
            'D': {'depends': [['self', ['name']], ['de_o.ef_o.fg_o', ['comp']]],
                  'func': lambda self: self.name + ''.join(
                      MODELS['G'].objects.filter(o_gf__o_fe__o_ed=self).values_list('comp', flat=True))},
        })
        self.a = self.models.A(name='a')
        self.a.save()
        self.b = self.models.B(name='b', o_ba=self.a)
        self.b.save()
        self.c = self.models.C(name='c', o_cb=self.b)
        self.c.save()
        self.d = self.models.D(name='d', o_dc=self.c)
        self.d.save()
        self.e = self.models.E(name='e', o_ed=self.d)
        self.e.save()
        self.f = self.models.F(name='f', o_fe=self.e)
        self.f.save()
        self.g = self.models.G(name='g', o_gf=self.f)
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
        # have to delete old one first
        self.d.de_o.delete()
        new_e = self.models.E(name='E', o_ed=self.d)
        new_e.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cE')

    def test_multiple_fk_deps_insert(self):
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dg')

    def test_multiple_fk_deps_update(self):
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dg')
        # have to delete old one first
        self.f.fg_o.delete()
        new_g = self.models.G(name='G', o_gf=self.f)
        new_g.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dG')

    def test_deletes(self):
        # deleting g should update f, d, e
        self.g.delete()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'd')  # no g
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'f-')  # no g
        self.e.refresh_from_db()
        self.assertEqual(self.e.comp, 'ef-')  # no g
        # deleting g should not update c
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'ce')
