from .base import GenericModelTestBase, MODELS
from ..models import Parent, Child, Subchild, XParent, XChild
from computedfields.models import update_dependent, preupdate_dependent


class ForeignKeyBackDependencies(GenericModelTestBase):
    """
    Test cases for foreign key back relations.
    """
    def setUp(self):
        self.setDeps({
            # deps only to itself
            'G': {'depends': [('self', ['name'])],
                  'func': lambda self: self.name},
            # one fk back step deps to comp field
            'F': {'depends': [('self', ['name']), ('fg_f', ['comp'])],
                  'func': lambda self: self.name + (''.join(self.fg_f.all().values_list('comp', flat=True).order_by('pk')) if self.pk else '')},
            'E': {'depends': [('self', ['name']), ('ef_f', ['comp'])],
                  'func': lambda self: self.name + (''.join(self.ef_f.all().values_list('comp', flat=True).order_by('pk')) if self.pk else '')},
            # multi fk back steps deps to non comp field
            'C': {'depends': [('self', ['name']), ('cd_f.de_f', ['name'])],
                  'func': lambda self: self.name + ''.join(
                      MODELS['E'].objects.filter(f_ed__f_dc=self).values_list('name', flat=True).order_by('pk'))
                      if self.pk
                      else ''},
            # multi fk back steps deps to comp field
            'D': {'depends': [('self', ['name']), ('de_f.ef_f.fg_f', ['comp'])],
                  'func': lambda self: self.name + ''.join(
                      MODELS['G'].objects.filter(f_gf__f_fe__f_ed=self).values_list('comp', flat=True).order_by('pk'))
                      if self.pk
                      else ''},
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

    def test_deletes(self):
        # deleting g should update f, d, e
        self.g.delete()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'd')  # no g
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'f')  # no g
        self.e.refresh_from_db()
        self.assertEqual(self.e.comp, 'ef')  # no g
        # deleting g should not update c
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'ce')

    def test_move_children(self):
        p1 = Parent.objects.create()
        p2 = Parent.objects.create()
        c1 = Child.objects.create(parent=p1)
        c2 = Child.objects.create(parent=p2)

        # One child per parent
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.children_count, 1)
        self.assertEqual(p2.children_count, 1)

        # Move the child to another parent
        c2.parent = p1
        c2.save()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.children_count, 2)  # Fine
        self.assertEqual(p2.children_count, 0)  # Assertion error : 1 != 0

    def test_move_bulk(self):
        p1 = Parent.objects.create()
        p2 = Parent.objects.create()
        for i in range(10):
            Child.objects.create(parent=p1)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.children_count, 10)
        self.assertEqual(p2.children_count, 0)

        old_relations = preupdate_dependent(Child.objects.all())
        Child.objects.all().update(parent=p2)
        update_dependent(Child.objects.all(), old=old_relations)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.children_count, 0)
        self.assertEqual(p2.children_count, 10)

    def test_move_subchildren(self):
        p1 = Parent.objects.create()
        p2 = Parent.objects.create()
        c1 = Child.objects.create(parent=p1)
        c2 = Child.objects.create(parent=p2)
        s11 = Subchild.objects.create(subparent=c1)
        s12 = Subchild.objects.create(subparent=c1)
        s21 = Subchild.objects.create(subparent=c2)
        s22 = Subchild.objects.create(subparent=c2)

        # One child per parent
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 2)
        self.assertEqual(p2.subchildren_count, 2)

        # Move the child to another parent
        c2.parent = p1
        c2.save()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 4)
        self.assertEqual(p2.subchildren_count, 0)

        # move child back
        c2.parent = p2
        c2.save()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 2)
        self.assertEqual(p2.subchildren_count, 2)

        # move one subchild
        s22.subparent = c1
        s22.save()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 3)
        self.assertEqual(p2.subchildren_count, 1)
        self.assertEqual(p1.subchildren_count_proxy, 3)
        self.assertEqual(p2.subchildren_count_proxy, 1)

    def test_move_bulk_subchildren(self):
        p1 = Parent.objects.create()
        p2 = Parent.objects.create()
        c1 = Child.objects.create(parent=p1)
        c2 = Child.objects.create(parent=p2)
        s11 = Subchild.objects.create(subparent=c1)
        s12 = Subchild.objects.create(subparent=c1)
        s21 = Subchild.objects.create(subparent=c2)
        s22 = Subchild.objects.create(subparent=c2)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 2)
        self.assertEqual(p2.subchildren_count, 2)

        old_relations = preupdate_dependent(Subchild.objects.all())
        Subchild.objects.all().update(subparent=c2)
        update_dependent(Subchild.objects.all(), old=old_relations)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 0)
        self.assertEqual(p2.subchildren_count, 4)
        self.assertEqual(p1.subchildren_count_proxy, 0)
        self.assertEqual(p2.subchildren_count_proxy, 4)

    def test_x_models(self):
        self.xp1 = XParent.objects.create()
        self.xp2 = XParent.objects.create()

        self.xc1 = XChild.objects.create(parent=self.xp1, value=1)
        self.xc10 = XChild.objects.create(parent=self.xp1, value=10)
        self.xc100 = XChild.objects.create(parent=self.xp2, value=100)
        self.xc1000 = XChild.objects.create(parent=self.xp2, value=1000)

        self.xp1.refresh_from_db()
        self.xp2.refresh_from_db()

        self.assertEqual(self.xp1.children_value, 11)
        self.assertEqual(self.xp2.children_value, 1100)

        self.xc100.parent = self.xp1
        self.xc100.save()
        self.xc1000.parent = self.xp1
        self.xc1000.save()

        self.xp1.refresh_from_db()
        self.xp2.refresh_from_db()

        self.assertEqual(self.xp1.children_value, 1111)
        self.assertEqual(self.xp2.children_value, 0)




from computedfields.models import not_computed
class ForeignKeyBackDependenciesNC(GenericModelTestBase):
    """
    Test cases for foreign key back relations.
    """
    def setUp(self):
        self.setDeps({
            # deps only to itself
            'G': {'depends': [('self', ['name'])],
                  'func': lambda self: self.name},
            # one fk back step deps to comp field
            'F': {'depends': [('self', ['name']), ('fg_f', ['comp'])],
                  'func': lambda self: self.name + (''.join(self.fg_f.all().values_list('comp', flat=True).order_by('pk')) if self.pk else '')},
            'E': {'depends': [('self', ['name']), ('ef_f', ['comp'])],
                  'func': lambda self: self.name + (''.join(self.ef_f.all().values_list('comp', flat=True).order_by('pk')) if self.pk else '')},
            # multi fk back steps deps to non comp field
            'C': {'depends': [('self', ['name']), ('cd_f.de_f', ['name'])],
                  'func': lambda self: self.name + ''.join(
                      MODELS['E'].objects.filter(f_ed__f_dc=self).values_list('name', flat=True).order_by('pk'))
                      if self.pk
                      else ''},
            # multi fk back steps deps to comp field
            'D': {'depends': [('self', ['name']), ('de_f.ef_f.fg_f', ['comp'])],
                  'func': lambda self: self.name + ''.join(
                      MODELS['G'].objects.filter(f_gf__f_fe__f_ed=self).values_list('comp', flat=True).order_by('pk'))
                      if self.pk
                      else ''},
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
            self.g = self.models.G(name='g', f_gf=self.f)
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

    def test_insert(self):
        self.f.refresh_from_db()
        self.e.refresh_from_db()
        self.assertEqual(self.g.comp, 'g')
        self.assertEqual(self.f.comp, 'fg')
        self.assertEqual(self.e.comp, 'efg')

    def test_bubbling_updates(self):
        with not_computed(recover=True):
            self.g.name = 'G'
            self.g.save()
        # need to reload data from db
        self.g.refresh_from_db()
        self.f.refresh_from_db()
        self.e.refresh_from_db()
        self.assertEqual(self.g.comp, 'G')
        self.assertEqual(self.f.comp, 'fG')
        self.assertEqual(self.e.comp, 'efG')

    def test_bubbling_update_without_refresh_on_save(self):
        # bubbling update without refresh should work on save
        with not_computed(recover=True):
            self.g.name = 'G'
            self.g.save()
            self.f.name = 'F'
            self.f.save()
            self.e.name = 'E'
            self.e.save()
        # for not_computed we always need to refresh, even for local CFs
        self.g.refresh_from_db()
        self.f.refresh_from_db()
        self.e.refresh_from_db()
        self.assertEqual(self.g.comp, 'G')
        self.assertEqual(self.f.comp, 'FG')
        self.assertEqual(self.e.comp, 'EFG')

    def test_fkback_over_multiple_models_insert(self):
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'ce')

    def test_fkback_over_multiple_models_update(self):
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'ce')
        with not_computed(recover=True):
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
        with not_computed(recover=True):
            new_g = self.models.G(name='G', f_gf=self.f)
            new_g.save()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'dgG')

    def test_deletes(self):
        # deleting g should update f, d, e
        with not_computed(recover=True):
            self.g.delete()
        self.d.refresh_from_db()
        self.assertEqual(self.d.comp, 'd')  # no g
        self.f.refresh_from_db()
        self.assertEqual(self.f.comp, 'f')  # no g
        self.e.refresh_from_db()
        self.assertEqual(self.e.comp, 'ef')  # no g
        # deleting g should not update c
        self.c.refresh_from_db()
        self.assertEqual(self.c.comp, 'ce')

    def test_move_children(self):
        with not_computed(recover=True):
            p1 = Parent.objects.create()
            p2 = Parent.objects.create()
            c1 = Child.objects.create(parent=p1)
            c2 = Child.objects.create(parent=p2)

        # One child per parent
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.children_count, 1)
        self.assertEqual(p2.children_count, 1)

        # Move the child to another parent
        with not_computed(recover=True):
            c2.parent = p1
            c2.save()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.children_count, 2)  # Fine
        self.assertEqual(p2.children_count, 0)  # Assertion error : 1 != 0

    def test_move_bulk(self):
        with not_computed(recover=True):
            p1 = Parent.objects.create()
            p2 = Parent.objects.create()
            for i in range(10):
                Child.objects.create(parent=p1)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.children_count, 10)
        self.assertEqual(p2.children_count, 0)

        with not_computed(recover=True):
            old_relations = preupdate_dependent(Child.objects.all())
            Child.objects.all().update(parent=p2)
            update_dependent(Child.objects.all(), old=old_relations)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.children_count, 0)
        self.assertEqual(p2.children_count, 10)

    def test_move_subchildren(self):
        with not_computed(recover=True):
            p1 = Parent.objects.create()
            p2 = Parent.objects.create()
            c1 = Child.objects.create(parent=p1)
            c2 = Child.objects.create(parent=p2)
            s11 = Subchild.objects.create(subparent=c1)
            s12 = Subchild.objects.create(subparent=c1)
            s21 = Subchild.objects.create(subparent=c2)
            s22 = Subchild.objects.create(subparent=c2)

        # One child per parent
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 2)
        self.assertEqual(p2.subchildren_count, 2)

        # Move the child to another parent
        with not_computed(recover=True):
            c2.parent = p1
            c2.save()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 4)
        self.assertEqual(p2.subchildren_count, 0)

        # move child back
        with not_computed(recover=True):
            c2.parent = p2
            c2.save()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 2)
        self.assertEqual(p2.subchildren_count, 2)

        # move one subchild
        with not_computed(recover=True):
            s22.subparent = c1
            s22.save()

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 3)
        self.assertEqual(p2.subchildren_count, 1)
        self.assertEqual(p1.subchildren_count_proxy, 3)
        self.assertEqual(p2.subchildren_count_proxy, 1)

    def test_move_bulk_subchildren(self):
        with not_computed(recover=True):
            p1 = Parent.objects.create()
            p2 = Parent.objects.create()
            c1 = Child.objects.create(parent=p1)
            c2 = Child.objects.create(parent=p2)
            s11 = Subchild.objects.create(subparent=c1)
            s12 = Subchild.objects.create(subparent=c1)
            s21 = Subchild.objects.create(subparent=c2)
            s22 = Subchild.objects.create(subparent=c2)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 2)
        self.assertEqual(p2.subchildren_count, 2)

        with not_computed(recover=True):
            old_relations = preupdate_dependent(Subchild.objects.all())
            Subchild.objects.all().update(subparent=c2)
            update_dependent(Subchild.objects.all(), old=old_relations)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.subchildren_count, 0)
        self.assertEqual(p2.subchildren_count, 4)
        self.assertEqual(p1.subchildren_count_proxy, 0)
        self.assertEqual(p2.subchildren_count_proxy, 4)

    def test_x_models(self):
        with not_computed(recover=True):
            self.xp1 = XParent.objects.create()
            self.xp2 = XParent.objects.create()

            self.xc1 = XChild.objects.create(parent=self.xp1, value=1)
            self.xc10 = XChild.objects.create(parent=self.xp1, value=10)
            self.xc100 = XChild.objects.create(parent=self.xp2, value=100)
            self.xc1000 = XChild.objects.create(parent=self.xp2, value=1000)

        self.xp1.refresh_from_db()
        self.xp2.refresh_from_db()

        self.assertEqual(self.xp1.children_value, 11)
        self.assertEqual(self.xp2.children_value, 1100)

        with not_computed(recover=True):
            self.xc100.parent = self.xp1
            self.xc100.save()
            self.xc1000.parent = self.xp1
            self.xc1000.save()

        self.xp1.refresh_from_db()
        self.xp2.refresh_from_db()

        self.assertEqual(self.xp1.children_value, 1111)
        self.assertEqual(self.xp2.children_value, 0)
