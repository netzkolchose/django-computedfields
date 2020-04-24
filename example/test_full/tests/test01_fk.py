from .base import GenericModelTestBase


class ForeignKeyDependencies(GenericModelTestBase):
    """
    Test cases for foreign key relations.
    """
    def setUp(self):
        self.setDeps({
            # deps only to itself
            'B': {'func': lambda self: self.name},
            # one fk step deps to comp field
            'C': {'depends': ['f_cb#comp'],
                  'func': lambda self: self.name + self.f_cb.comp},
            'D': {'depends': ['f_dc#comp'],
                  'func': lambda self: self.name + (self.f_dc.comp if self.f_dc else '-')},
            # multi fk steps deps to non comp field
            'E': {'depends': ['f_ed.f_dc.f_cb.f_ba#name'],
                  'func': lambda self: self.name + (self.f_ed.f_dc.f_cb.f_ba.name if self.f_ed.f_dc else '-')},
            # multi fk steps deps to comp field
            'F': {'depends': ['f_fe.f_ed.f_dc.f_cb#name'],
                  'func': lambda self: self.name + (self.f_fe.f_ed.f_dc.f_cb.name if self.f_fe.f_ed.f_dc else '-')},
            # multiple mixed deps
            'G': {'depends': ['f_gf#comp', 'f_gf.f_fe.f_ed#name'],
                  'func': lambda self: self.name + self.f_gf.comp + self.f_gf.f_fe.f_ed.name}
        })
        # test data - fk chained objects
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
        self.assertEqual(self.b.comp, 'b')
        self.assertEqual(self.c.comp, 'cb')
        self.assertEqual(self.d.comp, 'dcb')

    def test_bubbling_updates(self):
        self.b.name = 'B'
        self.b.save()
        # need to reload data from db
        self.c.refresh_from_db()
        self.d.refresh_from_db()
        self.assertEqual(self.b.comp, 'B')
        self.assertEqual(self.c.comp, 'cB')
        self.assertEqual(self.d.comp, 'dcB')

    def test_bubbling_update_without_refresh_on_save(self):
        # bubbling update without refresh should work on save
        self.b.name = 'B'
        self.b.save()
        self.c.name = 'C'
        self.c.save()
        self.d.name = 'D'
        self.d.save()
        self.assertEqual(self.b.comp, 'B')
        self.assertEqual(self.c.comp, 'CB')
        self.assertEqual(self.d.comp, 'DCB')

    def test_fk_over_multiple_models_insert(self):
        self.assertEqual(self.e.comp, 'ea')
        self.assertEqual(self.f.comp, 'fb')

    def test_fk_over_multiple_models_update(self):
        self.assertEqual(self.e.comp, 'ea')
        new_a = self.models.A(name='A')
        new_a.save()
        self.b.f_ba = new_a
        self.b.name = 'B'
        self.b.save()
        self.e.refresh_from_db()
        self.f.refresh_from_db()
        self.assertEqual(self.e.comp, 'eA')
        self.assertEqual(self.f.comp, 'fB')

    def test_multiple_fk_deps_insert(self):
        self.assertEqual(self.g.comp, 'gfbd')

    def test_multiple_fk_deps_update(self):
        # removed: set([Edge test_full.e.#-test_full.g.comp, Edge test_full.d.#-test_full.g.comp])
        # G.comp depends: ['f_gf#comp', 'f_gf.f_fe.f_ed#name']
        self.assertEqual(self.g.comp, 'gfbd')
        self.f.name = 'F'
        self.f.save()
        self.g.refresh_from_db()
        self.assertEqual(self.g.comp, 'gFbd')
        self.d.name = 'D'
        self.d.save()
        self.g.refresh_from_db()
        self.assertEqual(self.g.comp, 'gFbD')

    def test_deletes(self):
        self.assertEqual(self.g.comp, 'gfbd')
        # deleting c should trigger updates for d, e, f, g
        self.c.delete()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'd-')
        self.e.refresh_from_db()
        self.assertEqual(self.e.comp, 'e-')
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'f-')
        self.g.refresh_from_db()
        self.assertEqual(self.g.comp, 'gf-d')
        # deleting g should not trigger any updates
        self.g.delete()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'd-')  # - instead of g
        self.e.refresh_from_db()
        self.assertEqual(self.e.comp, 'e-')  # - instead of g
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'f-')  # - instead of g
