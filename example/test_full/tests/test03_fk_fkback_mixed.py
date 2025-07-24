from .base import GenericModelTestBase, MODELS


class MixedForeignKeysAndBackDependenciesSimple(GenericModelTestBase):
    """
    Test cases for mixed simple foreign key and
    foreign key back relations (fk + fk_back, fk_back + fk).
    """
    def setUp(self):
        self.setDeps({
            # fk + fk_back
            'B': {'depends': [('self', ['name']), ('f_ba.ag_f', ['name'])],
                  'func': lambda self: self.name + ''.join(
                      MODELS['G'].objects.filter(f_ga=self.f_ba).values_list('name', flat=True).order_by('pk'))},
            # fk_back + fk
            'F': {'depends': [('self', ['name']), ('fg_f.f_ga', ['name'])],
                  'func': lambda self: self.name + (''.join(MODELS['A'].objects.filter(
                      pk__in=self.fg_f.all().values_list('f_ga', flat=True).order_by('pk').distinct()
                  ).values_list('name', flat=True).order_by('pk')) if self.pk else '')},
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

    def tearDown(self):
        self.resetDeps()

    def test_fk_fkback_insert(self):
        # since g got saved later we need to reload from db
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bg')

    def test_fk_fkback_update(self):
        # since g got saved later we need to reload from db
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bg')
        new_g = self.models.G(name='G', f_gf=self.f, f_ga=self.a)
        new_g.save()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bgG')

    def test_fkback_fk_insert(self):
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'fa')

    def test_fkback_fk_update(self):
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'fa')
        new_a = self.models.A(name='A')
        new_a.save()
        self.g.f_ga = new_a
        self.g.save()
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'fA')
        new_g = self.models.G(name='G', f_gf=self.f, f_ga=self.a)
        new_g.save()
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'faA')

    def test_deletes(self):
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bg')
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'fa')
        self.g.delete()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'b')
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'f')


class MixedForeignKeysAndBackDependenciesMultipleOne(GenericModelTestBase):
    """
    Test cases for more complex foreign key and foreign key back relations
    (fk + fk_back + fk + fk_back, fk_back + fk + fk_back + fk).
    """
    def setUp(self):
        self.setDeps({
            # fk + fk_back + fk + fk_back
            'B': {'depends': [('self', ['name']), ('f_ba.ag_f.f_gf.fd_f', ['name'])],
                  'func': lambda self: self.name + ''.join(MODELS['D'].objects.filter(
                      f_df__in=MODELS['G'].objects.filter(f_ga=self.f_ba).values_list('f_gf', flat=True)
                  ).values_list('name', flat=True))},
            # fk_back + fk + fk_back + fk
            'D': {'depends': [('self', ['name']), ('f_df.fg_f.f_ga.ab_f', ['name'])],
                  'func': lambda self: self.name + ''.join(MODELS['B'].objects.filter(
                      f_ba__in=MODELS['G'].objects.filter(f_gf=self.f_df).values_list('f_ga', flat=True)
                  ).values_list('name', flat=True))}
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
        self.d.f_df = self.f
        self.d.save()

    def tearDown(self):
        self.resetDeps()

    def test_B_insert(self):
        # since g got saved later we need to reload from db
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bd')

    def test_B_update(self):
        # dep is D -> (F) -> G -> A -> B
        # change D
        self.d.name = 'D'
        self.d.save()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bD')
        # new D
        new_d = self.models.D(name='d2', f_df=self.f)
        new_d.save()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bDd2')
        # change b to different a
        new_a = self.models.A(name='newA')
        new_a.save()
        self.b.f_ba = new_a
        self.b.save()
        self.assertEqual(self.b.comp, 'b')
        # insert g with points to new a and old f
        # should restore old value in comp
        new_g = self.models.G(name='g', f_gf=self.f, f_ga=new_a)
        new_g.save()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bDd2')

    def test_B_update_insert_delete(self):
        # change D
        self.d.name = 'D'
        self.d.save()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bD')
        # new D
        new_d = self.models.D(name='d2', f_df=self.f)
        new_d.save()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bDd2')
        # delete new_d
        new_d.delete()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bD')
        # delete d
        self.d.delete()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'b')

    def test_D_insert(self):
        self.assertEqual(self.d.comp, 'db')

    def test_D_update(self):
        self.assertEqual(self.d.comp, 'db')
        # change linked B
        self.b.name = 'B'
        self.b.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dB')
        # add new B
        new_b = self.models.B(name='b2', f_ba=self.a)
        new_b.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dBb2')

    def test_D_insert_update_delete(self):
        self.b.name = 'B'
        self.b.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dB')
        # add new B
        new_b = self.models.B(name='b2', f_ba=self.a)
        new_b.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dBb2')
        # delete new_b
        new_b.delete()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dB')
        # delete b
        self.b.delete()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'd')


class MixedForeignKeysAndBackDependenciesMultipleTwo(GenericModelTestBase):
    """
    Test cases for long path mixed foreign key and foreign key back relations
    (fk + fk + fk_back + fk_back).
    """
    def setUp(self):
        self.setDeps({
            # fk + fk + fk_back + fk_back
            'C': {'depends': [('self', ['name']), ('f_cb.f_ba.ag_f.gd_f', ['name'])],
                  'func': lambda self: self.name + ''.join(
                      MODELS['D'].objects.filter(f_dg__in=MODELS['G'].objects.filter(
                          f_ga=self.f_cb.f_ba)).values_list('name', flat=True))},
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
        self.assertEqual(self.c.comp, 'cd')

    def test_C_update(self):
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cd')
        # change D
        self.d.name = 'D'
        self.d.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cD')
        # add new D
        new_d = self.models.D(name='d2', f_dg=self.g)
        new_d.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cDd2')

    def test_C_update_delete(self):
        # change D
        self.d.name = 'D'
        self.d.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cD')
        # add new D
        new_d = self.models.D(name='d2', f_dg=self.g)
        new_d.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cDd2')
        # delete new_d
        new_d.delete()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cD')
        # delete d
        self.d.delete()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'c')


class MixedForeignKeysAndBackDependenciesMultipleExtendedFKBack(GenericModelTestBase):
    """
    There is a problem if multiple fkback are in front - this resulting
    queryset contains only pk values (from values_list).
    Extended test to make sure it works in different circumstances.
    Tests fk_back + fk_back + fk_back + fk + fk + fk
    """
    def setUp(self):
        self.setDeps({
            # fk_back + fk_back + fk_back + fk + fk + fk
            'D': {'depends': [('self', ['name']), ('de_f.ef_f.fg_f.f_ga.f_ac.f_cb', ['name'])],
                  'func': lambda self: self.name + (''.join(filter(bool, MODELS['G'].objects.filter(
                      f_gf__in=MODELS['F'].objects.filter(
                          f_fe__in=self.de_f.all())).values_list('f_ga__f_ac__f_cb__name', flat=True))) if self.pk else '')}
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
        self.assertEqual(self.d.comp, 'db')

    def test_D_update(self):
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'db')
        # change B
        self.b.name = 'B'
        self.b.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dB')
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
        self.assertEqual(self.d.comp, 'db2')

    def test_D_update_delete(self):
        # change B
        self.b.name = 'B'
        self.b.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dB')
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
        self.assertEqual(self.d.comp, 'db2')
        # delete new_a - should remove b from d
        new_a.delete()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'd')




from computedfields.models import not_computed
class MixedForeignKeysAndBackDependenciesSimpleNC(GenericModelTestBase):
    """
    Test cases for mixed simple foreign key and
    foreign key back relations (fk + fk_back, fk_back + fk).
    """
    def setUp(self):
        self.setDeps({
            # fk + fk_back
            'B': {'depends': [('self', ['name']), ('f_ba.ag_f', ['name'])],
                  'func': lambda self: self.name + ''.join(
                      MODELS['G'].objects.filter(f_ga=self.f_ba).values_list('name', flat=True).order_by('pk'))},
            # fk_back + fk
            'F': {'depends': [('self', ['name']), ('fg_f.f_ga', ['name'])],
                  'func': lambda self: self.name + (''.join(MODELS['A'].objects.filter(
                      pk__in=self.fg_f.all().values_list('f_ga', flat=True).order_by('pk').distinct()
                  ).values_list('name', flat=True).order_by('pk')) if self.pk else '')},
        })
        with not_computed(recover=True):
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
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.c.refresh_from_db()
        self.d.refresh_from_db()
        self.e.refresh_from_db()
        self.f.refresh_from_db()
        self.g.refresh_from_db()

    def tearDown(self):
        self.resetDeps()

    def test_fk_fkback_insert(self):
        # since g got saved later we need to reload from db
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bg')

    def test_fk_fkback_update(self):
        # since g got saved later we need to reload from db
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bg')
        with not_computed(recover=True):
            new_g = self.models.G(name='G', f_gf=self.f, f_ga=self.a)
            new_g.save()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bgG')

    def test_fkback_fk_insert(self):
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'fa')

    def test_fkback_fk_update(self):
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'fa')
        with not_computed(recover=True):
            new_a = self.models.A(name='A')
            new_a.save()
            self.g.f_ga = new_a
            self.g.save()
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'fA')
        with not_computed(recover=True):
            new_g = self.models.G(name='G', f_gf=self.f, f_ga=self.a)
            new_g.save()
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'faA')

    def test_deletes(self):
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bg')
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'fa')
        with not_computed(recover=True):
            self.g.delete()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'b')
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'f')


class MixedForeignKeysAndBackDependenciesMultipleOneNC(GenericModelTestBase):
    """
    Test cases for more complex foreign key and foreign key back relations
    (fk + fk_back + fk + fk_back, fk_back + fk + fk_back + fk).
    """
    def setUp(self):
        self.setDeps({
            # fk + fk_back + fk + fk_back
            'B': {'depends': [('self', ['name']), ('f_ba.ag_f.f_gf.fd_f', ['name'])],
                  'func': lambda self: self.name + ''.join(MODELS['D'].objects.filter(
                      f_df__in=MODELS['G'].objects.filter(f_ga=self.f_ba).values_list('f_gf', flat=True)
                  ).values_list('name', flat=True))},
            # fk_back + fk + fk_back + fk
            'D': {'depends': [('self', ['name']), ('f_df.fg_f.f_ga.ab_f', ['name'])],
                  'func': lambda self: self.name + ''.join(MODELS['B'].objects.filter(
                      f_ba__in=MODELS['G'].objects.filter(f_gf=self.f_df).values_list('f_ga', flat=True)
                  ).values_list('name', flat=True))}
        })
        with not_computed(recover=True):
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
            self.d.f_df = self.f
            self.d.save()
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.c.refresh_from_db()
        self.d.refresh_from_db()
        self.e.refresh_from_db()
        self.f.refresh_from_db()
        self.g.refresh_from_db()

    def tearDown(self):
        self.resetDeps()

    def test_B_insert(self):
        # since g got saved later we need to reload from db
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bd')

    def test_B_update(self):
        # dep is D -> (F) -> G -> A -> B
        # change D
        with not_computed(recover=True):
            self.d.name = 'D'
            self.d.save()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bD')
        # new D
        with not_computed(recover=True):
            new_d = self.models.D(name='d2', f_df=self.f)
            new_d.save()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bDd2')
        # change b to different a
        with not_computed(recover=True):
            new_a = self.models.A(name='newA')
            new_a.save()
            self.b.f_ba = new_a
            self.b.save()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'b')
        # insert g with points to new a and old f
        # should restore old value in comp
        with not_computed(recover=True):
            new_g = self.models.G(name='g', f_gf=self.f, f_ga=new_a)
            new_g.save()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bDd2')

    def test_B_update_insert_delete(self):
        # change D
        with not_computed(recover=True):
            self.d.name = 'D'
            self.d.save()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bD')
        # new D
        with not_computed(recover=True):
            new_d = self.models.D(name='d2', f_df=self.f)
            new_d.save()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bDd2')
        # delete new_d
        with not_computed(recover=True):
            new_d.delete()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'bD')
        # delete d
        with not_computed(recover=True):
            self.d.delete()
        self.b.refresh_from_db()
        self.assertEqual(self.b.comp, 'b')

    def test_D_insert(self):
        self.assertEqual(self.d.comp, 'db')

    def test_D_update(self):
        self.assertEqual(self.d.comp, 'db')
        # change linked B
        with not_computed(recover=True):
            self.b.name = 'B'
            self.b.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dB')
        # add new B
        with not_computed(recover=True):
            new_b = self.models.B(name='b2', f_ba=self.a)
            new_b.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dBb2')

    def test_D_insert_update_delete(self):
        with not_computed(recover=True):
            self.b.name = 'B'
            self.b.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dB')
        # add new B
        with not_computed(recover=True):
            new_b = self.models.B(name='b2', f_ba=self.a)
            new_b.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dBb2')
        # delete new_b
        with not_computed(recover=True):
            new_b.delete()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dB')
        # delete b
        with not_computed(recover=True):
            self.b.delete()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'd')


class MixedForeignKeysAndBackDependenciesMultipleTwoNC(GenericModelTestBase):
    """
    Test cases for long path mixed foreign key and foreign key back relations
    (fk + fk + fk_back + fk_back).
    """
    def setUp(self):
        self.setDeps({
            # fk + fk + fk_back + fk_back
            'C': {'depends': [('self', ['name']), ('f_cb.f_ba.ag_f.gd_f', ['name'])],
                  'func': lambda self: self.name + ''.join(
                      MODELS['D'].objects.filter(f_dg__in=MODELS['G'].objects.filter(
                          f_ga=self.f_cb.f_ba)).values_list('name', flat=True))},
        })
        with not_computed(recover=True):
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
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.c.refresh_from_db()
        self.d.refresh_from_db()
        self.e.refresh_from_db()
        self.f.refresh_from_db()
        self.g.refresh_from_db()

    def tearDown(self):
        self.resetDeps()

    def test_C_insert(self):
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cd')

    def test_C_update(self):
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cd')
        # change D
        with not_computed(recover=True):
            self.d.name = 'D'
            self.d.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cD')
        # add new D
        with not_computed(recover=True):
            new_d = self.models.D(name='d2', f_dg=self.g)
            new_d.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cDd2')

    def test_C_update_delete(self):
        # change D
        with not_computed(recover=True):
            self.d.name = 'D'
            self.d.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cD')
        # add new D
        with not_computed(recover=True):
            new_d = self.models.D(name='d2', f_dg=self.g)
            new_d.save()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cDd2')
        # delete new_d
        with not_computed(recover=True):
            new_d.delete()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'cD')
        # delete d
        with not_computed(recover=True):
            self.d.delete()
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'c')


class MixedForeignKeysAndBackDependenciesMultipleExtendedFKBackNC(GenericModelTestBase):
    """
    There is a problem if multiple fkback are in front - this resulting
    queryset contains only pk values (from values_list).
    Extended test to make sure it works in different circumstances.
    Tests fk_back + fk_back + fk_back + fk + fk + fk
    """
    def setUp(self):
        self.setDeps({
            # fk_back + fk_back + fk_back + fk + fk + fk
            'D': {'depends': [('self', ['name']), ('de_f.ef_f.fg_f.f_ga.f_ac.f_cb', ['name'])],
                  'func': lambda self: self.name + (''.join(filter(bool, MODELS['G'].objects.filter(
                      f_gf__in=MODELS['F'].objects.filter(
                          f_fe__in=self.de_f.all())).values_list('f_ga__f_ac__f_cb__name', flat=True))) if self.pk else '')}
        })
        with not_computed(recover=True):
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
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.c.refresh_from_db()
        self.d.refresh_from_db()
        self.e.refresh_from_db()
        self.f.refresh_from_db()
        self.g.refresh_from_db()

    def tearDown(self):
        self.resetDeps()

    def test_D_insert(self):
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'db')

    def test_D_update(self):
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'db')
        # change B
        with not_computed(recover=True):
            self.b.name = 'B'
            self.b.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dB')
        # add new A, B and C, change f_ga
        with not_computed(recover=True):
            new_b = self.models.B(name='b2')
            new_b.save()
            new_c = self.models.C(name='c2', f_cb=new_b)
            new_c.save()
            new_a = self.models.A(name='A', f_ac=new_c)
            new_a.save()
            self.g.f_ga = new_a
            self.g.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'db2')

    def test_D_update_delete(self):
        # change B
        with not_computed(recover=True):
            self.b.name = 'B'
            self.b.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dB')
        # add new A, B and C, change f_ga
        with not_computed(recover=True):
            new_b = self.models.B(name='b2')
            new_b.save()
            new_c = self.models.C(name='c2', f_cb=new_b)
            new_c.save()
            new_a = self.models.A(name='A', f_ac=new_c)
            new_a.save()
            self.g.f_ga = new_a
            self.g.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'db2')
        # delete new_a - should remove b from d
        with not_computed(recover=True):
            new_a.delete()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'd')
