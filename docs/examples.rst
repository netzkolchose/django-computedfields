Examples
========


Dependency Examples
-------------------

The following examples may give you a first idea on how to use the `depends` keyword of the
computed decorator for different scenarios.


No Dependencies
^^^^^^^^^^^^^^^

The most basic example is a computed field, that has no field dependencies at all.
It can be constructed by omitting the `depends` argument, e.g.:

.. code-block:: python

    class MyComputedModel(ComputedFieldsModel):

        @computed(Field(...))
        def comp(self):
            return some_value_pulled_from_elsewhere

Such a field will only be recalculated by calling ``save()`` or ``save(update_fields=[comp, ...])``
on a model instance. It never will be touched by the auto resolver, unless you force
the recalculation by directly calling ``update_dependent(MyComputedModel.objects.all())``, which
implies ``update_fields=None``, thus updates all model local fields, or again by explicitly listing
`comp` in `update_fields` like in ``update_dependent(MyComputedModel.objects.all(), update_fields=['comp'])``.


Local Fields
^^^^^^^^^^^^

A more useful computed field example would do some calculation based on some other model local fields:

.. code-block:: python

    class MyComputedModel(ComputedFieldsModel):
        fieldA = Field(...)
        fieldB = Field(...)

        @computed(Field(...), depends=[('self', ['fieldA', 'fieldB'])])
        def comp(self):
            return some_calc(self.fieldA, self.fieldB)

This can be achieve in a safe manner by placing a `self` rule in `depends`, listing local concrete fields
on the right side, as shown above.

.. admonition:: Background on `self` rule

    At a first glance it seems weird, that you should declare dependencies on other model local fields.
    Well, in previous versions it was not needed at all, but turned out as a major shortcoming of
    the old `depends` syntax leading to unresolvable ambiguity. The new syntax and the need to put
    local fields in a `self` rule enables :mod:`django-computedfields` to properly derive
    the execution order of local computed fields (MRO) and to correctly expand on `update_fields`
    given to a partial save call.


Local Computed Fields
^^^^^^^^^^^^^^^^^^^^^

To depend on another local computed field, simply list it in the `self` rule as another local concrete field:

.. code-block:: python

    class MyComputedModel(ComputedFieldsModel):
        fieldA = Field(...)
        fieldB = Field(...)
        fieldC = Field(...)

        @computed(Field(...), depends=[('self', ['fieldA', 'fieldB'])])
        def comp(self):
            return some_calc(self.fieldA, self.fieldB)
        
        @computed(Field(...), depends=[('self', ['fieldC', 'comp'])])
        def final(self):
            return some__other_calc(self.fieldC, self.comp)

The auto resolver will take care, that the computed fields are calculated in the correct order (`MRO`).
In the example above it will make sure, that `final` gets recalculated after `comp` only once, and never vice versa.
This also works with a partial save with ``save(update_fields=['fieldA'])``. Here the resolver will
expand `update_fields` to ``['fieldA', 'comp', 'final']``.

The ability to depend on other local computed fields may lead to update cycles:

.. code-block:: python

    class MyComputedModel(ComputedFieldsModel):
        fieldA = Field(...)
        fieldB = Field(...)
        fieldC = Field(...)

        @computed(Field(...), depends=[('self', ['fieldA', 'fieldB', 'final'])])
        def comp(self):
            return some_calc(self.fieldA, self.fieldB, self.final)
        
        @computed(Field(...), depends=[('self', ['fieldC', 'comp'])])
        def final(self):
            return some__other_calc(self.fieldC, self.comp)

There is no way to create or update such an instance, as `comp` relies on `final`,
which itself relies on `comp`. Here the the dependency resolver will throw a cycling exception
during startup.

.. NOTE::

    Dependencies to other local computed fields always must be cycle-free.


Related Model Fields
^^^^^^^^^^^^^^^^^^^^

Dependencies to fields on related models can be expressed with the relation name on the left side:

.. code-block:: python

    class Foo(models.Model):
        a = Field(...)
        x = Field(...)
    
    class Bar(models.Model):
        b = Field(...)
        baz = models.ForeignKey(Baz, related_name='bars', ...)

    class Baz(ComputedFieldsModel):
        c = Field(...)
        foo = models.ForeignKey(Foo, related_name='bazs', ...)

        @computed(Field(...), depends=[
            ('self', ['c']),
            ('foo', ['a']),   # fk forward relation to foo.a (accidentally forgetting foo.x)
            ('bars', ['b'])   # fk reverse relation to bar.b in self.bars
        ])
        def comp(self):
            for bar in self.bars.all():
                # do something with bar.b
            # do something with self.foo.a
            # wrong: self.foo.x somehow alters the result here
            return ...

Note that the method result should not rely on any other concrete field from the relations than those listed
in `depends`. If you accidentally forget to list some field (as shown for `foo.x` above),
the resolver will not update dependent instances for certain field updates (above: changes to `foo.x`
may not trigger an update on dependent `Foo.bazs.comp`).

:mod:`django-computedfields` has no measures to spot a forgotten source field, it fully relies on the correctness
of your `depends` declarations. If in doubt, whether you caught all relevant source fields,
you probably should test the computed field values against all of your critical business logic actions.

.. WARNING::

    Accidentally forgetting a source field in `depends` may lead to hard to track down desync issues.
    Make sure, that you listed in `depends` all source fields the method pulls data from.
    Note that this includes any concrete field, that alters the method result in a certain way.

The same rules apply for deeper nested relations, simply list the relation paths on the left side
with their corresponding source fields on the right side:

.. code-block:: python

    @computed(Field(...), depends=[
        ('related_set', ['a', 'b']),
        ('related_set.fk', ['xy'])
    ])
    def comp(self):
        result = 0
        for related in self.related_set.all():
            result -= related.a
            result += related.b
            result += related.fk.xy
        return result

For more advanced things like SQL aggregations or field annotations you should refer
to the true concrete source fields behind the annotation:

.. code-block:: python

    @computed(Field(...), depends=[
        ('related_set', ['value'])        # aggregation itself relies on field 'value'
    ])
    def with_aggregation(self):
        return self.related_set.aggregate(total=Sum('value'))['total'] or some_default

Here the aggregation is done over the field `value`, thus it should be listed in `depends`
to properly get updated on changes of related `value`. `totals` on the interim queryset
is only an annotated field with no persistent database representation, thus cannot be used
as source field in the dependency declaration. Same goes for even more complicated queryset
manipulations:

.. code-block:: python

    @computed(Field(...), depends=[
        ('related_set', ['a', 'b']),
        ('related_set.fk', ['c'])
    ])
    def with_complicated_aggregation(self):
        return (self.related_set
                .select_related('fk')
                .annotate(intermediate=F('a')+F('b')+F('fk__c'))
                .aggregate(total=Sum('intermediate'))['total']
            or some_default)

Here both fields `total` and `intermediate` are annotated and cannot be used in `depends`.
Instead resolve all annotated fields backwards and collect the concrete source fields,
which reveals `a` and `b` on `related_set` and `c` on `related_set.fk` as the real source fields
in the example above.

.. NOTE::

    The resolver expands dependencies on nested foreign key relations automatically:

    .. code-block:: python

        # shorthand notation of nested forward fk relations
        depends = [('a.b.c', ['fieldX'])]
        # expands internally to
        depends = [
          ('a.b.c', ['fieldX']),
          ('a.b', ['c']),
          ('a', ['b']),
          ('self', ['a'])
        ]

        # shorthand notation of nested reverse fk relations
        depends = [('a_set.b_set.c_set', ['fieldX'])]
        # expands internally to
        depends = [
          ('a_set.b_set.c_set', ['fieldX', 'fk_field_on_C_pointing_to_B']),
          ('a_set.b_set', ['fk_field_on_B_pointing_to_A']),
          ('a_set', ['fk_field_on_A_pointing_to_self'])
        ]

    This is needed to correctly spot and update computed fields on relation changes itself
    (e.g. moving children to a different parent).

    Note that because of this dependency expansion, it is not possible to omit foreign key
    relations on purpose, if they are part of a `depends` rule.

    Further note, that a similar expansion is done for m2m and reverse m2m fields.
    (Works similar to the fk expansion, but cannot be expressed in `depends`,
    as m2m fields dont map directly to a source column in database terms.)


Related Computed Fields
^^^^^^^^^^^^^^^^^^^^^^^

Depending on foreign computed fields works likewise as for other foreign source fields,
simply list them on the right side of the relation rule.

Again the auto resolver will throw a cycling exception by default, if you created a cycling
update. But other than for local computed field dependencies this can be supressed by setting
``COMPUTEDFIELDS_ALLOW_RECURSION`` to ``True`` in `settings.py`, which allows to use
computed fields on self-referencing models, e.g. tree-like structures.
Note that this currently disables intermodel dependency optimizations project-wide and might result
in high "update pressure". It also might lead to a `RuntimeError` later on, if you created
a real recursion on record level by accident.

.. TIP::

    Depending on additional computed fields is an easy way to lower the "update pressure" later on
    for complicated dependencies by isolating relatively static entities from fast turning ones.


Many-To-Many Fields
^^^^^^^^^^^^^^^^^^^

Django's `ManyToManyField` can be used in the dependency declaration on the left side as a relation:

.. code-block:: python

    class Person(ComputedFieldsModel):
        name = models.CharField(max_length=32)

        @computed(models.CharField(max_length=256), depends=[('groups', ['name'])])
        def groupnames(self):
            if not self.pk:
                return ''
            return ','.join(self.groups.all().values_list('name', flat=True))

    class Group(models.Model):
        name = models.CharField(max_length=32)
        members = models.ManyToManyField(Person, related_name='groups')

M2M relations are tested to work in both directions with their custom manager methods like
`add`, `set`, `remove` and `clear`. Also actions done to instances on boths ends should correctly update
computed fields through the m2m field. Still there are some specifics that need to be mentioned here.

In the method above there is a clause skipping the actual logic, if the instance has
no `pk` value yet. That clause is needed, since Django will not allow access to an m2m relation manager before
the instance was saved to the database. After the initial save the m2m relation can be accessed,
now correctly pulling field values across the m2m relation.

M2M fields allow to declare a custom `through` model for the join table. To use computed fields on the
`through` model or to pull fields from it to either side of the m2m relation, you cannot use the m2m field anymore.
Instead use the foreign key relations declared on the `through` model in `depends`.

Another important issue around m2m fields is the risk to cause a rather high update pressure later on.
Here it helps to remember, that the `n:m` relation in fact means, that every single instance
in `n` potentially updates `m` instances and vice versa. If you have multiple computed fields with dependency rules
spanning through an m2m field in either direction, the update penalty will explode creating a new bottleneck
in your project. Although there are some ways to further optimize computed fields updates, they are still quite
limited for m2m fields. Also see below under optimization examples. 

.. WARNING::

    M2M fields may create a high update pressure on computed fields and should be avoided in `depends`
    as much as possible.


Multi Table Inheritance
-----------------------

.. |br| raw:: html

   <br />


Multi table inheritance works with computed fields with some restrictions you have to be aware of.
The following requires basic knowledge about multi table inheritance in Django and its similarities
to o2o relations on accessor level (also see `official Django docs
<https://docs.djangoproject.com/en/3.2/topics/db/models/#multi-table-inheritance>`_).

Neighboring Models
^^^^^^^^^^^^^^^^^^

Let's illustrate dealing with updates from neighboring models with an example.
(Note: The example can also be found in `example.test_full` under `tests/test_multitable_example.py`)

.. code-block:: python

    from django.db import models
    from computedfields.models import ComputedFieldsModel, computed

    class User(ComputedFieldsModel):
        forname = models.CharField(max_length=32)
        surname = models.CharField(max_length=32)

        @computed(models.CharField(max_length=64), depends=[
            ('self', ['forname', 'surname'])
        ])
        def fullname(self):
            return '{}, {}'.format(self.surname, self.forname)

    class EmailUser(User):
        email = models.CharField(max_length=32)

        @computed(models.CharField(max_length=128), depends=[
            ('self', ['email', 'fullname']),
            ('user_ptr', ['fullname'])          # trigger updates from User type as well
        ])
        def email_contact(self):
            return '{} <{}>'.format(self.fullname, self.email)

    class Work(ComputedFieldsModel):
        subject = models.CharField(max_length=32)
        user = models.ForeignKey(User, on_delete=models.CASCADE)

        @computed(models.CharField(max_length=64), depends=[
            ('self', ['subject']),
            ('user', ['fullname']),
            ('user.emailuser', ['fullname'])    # trigger updates from EmailUser type as well
        ])
        def descriptive_assigment(self):
            return '"{}" is assigned to "{}"'.format(self.subject, self.user.fullname)

In the example there are two surprising `depends` rules:

    1. ``('user_ptr', ['fullname'])`` on ``EmailUser.email_contact``
    2. ``('user.emailuser', ['fullname'])`` on ``Work.descriptive_assigment``

Both are needed to expand the update rules in a way, that parent or derived models are also respected
for the field updates. While the first rule extends updates to the parent model `User`
(ascending in the model inheritance), the second one expands updates to a descendant.

*Why do I have to create those counter-intuitive rules?*

Currently the resolver does not expand on multi table inheritance automatically.
Furthermore it might not be wanted in all circumstances, that parent or derived models
trigger updates on other ends. Thus it has to be set explicitly (might change with future versions,
if highly demanded).

*When do I have to place those additional rules?*

In general the resolver updates computed fields only from model-field associations,
that were explicitly given in `depends` rules. Therefore it will not catch changes on
parent or derived models.

In the example above without the first rule any changes to an instance of `User` will not
trigger a recalculation of ``EmailUser.email_contact``. This is most likely unwanted behavior for this
particular example, as anyone would expect, that changing parts of the name should update the email contact
information here.

Without the second rule, ``Work.descriptive_assigment`` will not be updated from changes of an
`EmailUser` instance, which again is probably unwanted, as anyone would expect `EmailUser` to behave
like a `User` instance here.

*How to derive those rules?*

To understand, how to construct those additional rules, we have to look first at the rules,
they are derived from:

- first one is derived from ``('self', ['email', 'fullname'])``
- second one is derived from ``('user', ['fullname'])``

**Step 1 - check, whether the path ends on multi table model**

Looking at the relation paths (left side of the rules), both have something in common - they both end
on a model with multi table inheritance (`self` in 1. pointing to `EmailUser` model,
`user` in 2. pointing to `User` model). So whenever a relation ends on a multi table model,
there is a high chance, that you might want to apply additional rules for neighboring models.

**Step 2 - derive new relational path from model inheritance**

Next question is, whether you want to expand ascending or descending or both in the model inheritance:

- For ascending expansion append the o2o field name denoting the parent model.
- For descending expansion append reverse o2o relation name pointing to the derived model.

(Note: If a relation expands on `self` entries, `self` has to removed from the path.)

At this point it is important to know, how Django denotes multi table relations on model field level.
By default the o2o field is placed on the descendent model as `modelname_ptr`, while the reverse relation
gets the child modelname on the ancestor model as `modelname` (all lowercase).

In the example above ascending from `EmailUser` to `User` creates a relational path `user_ptr`,
while descending from `User` to `EmailUser` needs a relational path of `emailuser`.

**Step 3 - apply fieldnames on right side**

For descending rules you can just copy over the field names on the right side. For the descent from
`User` to `EmailUser` we finally get:

- ``('user.emailuser', ['fullname'])``

to be added to `depends` on ``Work.descriptive_assigment``.

For ascending rules you should be careful not to copy over field names on the right side, that are defined on
descendent models. After removing `email` from the field names we finally get for the ascent from `EmailUser`
to `User`:

- ``('user_ptr', ['fullname'])``

to be added to `depends` on ``EmailUser.email_contact``.

(Note: While not shown above, these steps can also be applied to neighboring tables in the middle of a relation path
to sidestep into a different path defined on a submodel. When doing this, keep in mind, that the JOINs in the DBMS
will grow a lot with heavy multi table inheritance eventually creating a select bottleneck just to figure out the
update candidates.)

Up-Pulling Fields
^^^^^^^^^^^^^^^^^

The resolver has a special rule for handling dependencies to fields on derived multi table models.
Therefore it is possible to create a computed field on the parent model, that conditionally
updates from different descendent model fields, example:

.. code-block:: python

    class MultiBase(ComputedFieldsModel):
        @computed(models.CharField(max_length=32), depends=[
            ('multia', ['f_on_a']),         # pull custom field from A descendant
            ('multib', ['f_on_b']),         # pull custom field from B descendant
            ('multib.multic', ['f_on_c'])   # pull custom field from C descendant
        ])
        def comp(self):
            # since we dont know the actual sub model,
            # we have to guard the attribute access
            # important: isinstance check will not work here!
            if hasattr(self, 'multia'):
                return self.multia.f_on_a
            if hasattr(self, 'multib'):
                if hasattr(self.multib, 'multic'):
                    return self.multib.multic.f_on_c
                return self.multib.f_on_b
            return ''

    class MultiA(MultiBase):
        f_on_a = models.CharField(max_length=32, default='a')
    class MultiB(MultiBase):
        f_on_b = models.CharField(max_length=32, default='b')
    class MultiC(MultiB):
        f_on_c = models.CharField(max_length=32, default='sub-c')

Note that you have to guard the attribute access yourself in the method as shown above.
Also you cannot rely on the type of `self` with `isinstance`, since the method
will run late on the model, where the field is defined (`MultiBase` above).

Sidenote: The up-pulling is currently not further optimized in the resolver,
which leads to a bad update cascade when used across deeper submodels. In the example above
saving a `MultiC` instance will cascade through updates on `MultiB` to `MultiBase`.


Forced Update of Computed Fields
--------------------------------

The simplest way to force a model to resync all its dependent computed fields is to re-save all model instances:

.. code-block:: python

    for inst in desynced_model.objects.all():
        inst.save()

While this is easy to comprehend, it has the major drawback of resyncing all dependencies as well
for every single save step touching related models over and over. Thus it will show a bad runtime for
complicated dependencies on big tables. A slightly better way is to call `update_dependent` instead:

.. code-block:: python

    from computedfields.models import update_dependent
    update_dependent(desynced_model.objects.all())

which will touch dependent models only once with an altered queryset containing all affected records.

If you have more knowledge about the action that caused a partial desync, you can customize
the queryset accordingly:

.. code-block:: python

    # given: some bulk action happened before like
    # desynced_model.objects.filter(fieldA='xy').update(fieldB='z')

    # either do
    for inst in desynced_model.objects.filter(fieldA='xy'):
        inst.save(update_fields=['fieldB'])
    # or
    update_dependent(desynced_model.objects.filter(fieldA='xy'), update_fields=['fieldB'])

Here both `save` or `update_dependent` will take care, that all dependent computed fields get updated.
Again using `update_dependent` has the advantage of further reducing the update pressure. Providing
`update_fields` will narrow the update path to computed fields, that actually rely on the listed
source fields.

A full resync of all computed fields project-wide can be triggered by calling the management command
`updatedata`. This comes handy if you cannot track down the cause of a desync or do not know which
models/fields are actually affected.

.. TIP::

    After bulk actions always call `update_dependent` with the changeset for any model to be on the
    safe side regarding sync status of computed fields. For models, that are not part of any
    dependency, `update_dependent` has a very small footprint in `O(1)` and will not hurt performance.

    Note that bulk actions altering relations itself might need a preparation step with
    `preupdate_dependent` (see API docs and optimization examples below).


Optimization Examples
---------------------

The way :mod:`django-computedfields` denormalizes data by precalculating fields at insert/update
time puts a major burden on these actions. Furthermore it synchronizes data between all database
relevant model instance actions from Python, which can cause high update load for computed fields
under certain circumstances. The following examples try to give some ideas on how to avoid major
update bottlenecks and to apply optimizations.


Prerequisites
^^^^^^^^^^^^^

Before trying to optimize things with computed fields it might be a good idea to check where
you start from. In terms of computed fields there are two major aspects, that might lead to poor
update performance:

- method code itself
    For the method code it is as simple as that - complicated code tends to do more things,
    tends to run longer. Try to keep methods slick, there is no need to wonder about DB query load,
    if the genuine method code itself eats >90% of the runtime (not counting needed ORM lookups).
    For big update queries you are already on the hours vs. days track, if not worse.
    If you cannot get the code any faster, maybe try to give up on the "realtime" approach
    computed fields offer by deferring the hard work.

    (Future versions might provide a `@computed_async` decorator to partially postpone
    hard work in a more straight forward fashion.)

- query load
    The following ideas/examples below mainly concentrate on query load issues with computed field updates
    and the question, how to gain back some update performance. For computed field updates the query load plays a
    rather important role, as any relation noted in dependencies is likely to turn into an `n`-case update.
    In theory this expands to `O(n^nested_relations)`, practically it cuts down earlier due to finite
    records in the database and aggressive model/field filtering done by the auto resolver. Still there is
    much room for further optimizations.

    Before applying some of the ideas below make sure to profile your project. Tools that might come
    handy for that:

        - ``django.test.utils.CaptureQueriesContext``
            Comes with Django itself, easy to use in tests or at the shell to get an idea,
            what is going on in SQL.
        - :mod:`django-debug-toolbar`
            Nice Django app with lots of profiling goodies like the SQL panel to inspect database
            interactions and timings.
        - :mod:`django-extensions`
            Another useful Django app with tons of goodies around Django needs. With the
            `ProfileServer` it is easy to find bottlenecks in your project.


Measuring with `updatedata`
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The revamped `updatedata` command since version 0.2.0 may help you to get a first impression,
which computed models perform really bad. The ``-p`` switch will give you a nice progressbar with
averaged `records/s` (needs :mod:`tqdm` to be installed).

*Note: The model definitions of the example below can be found in the exampleapp of the source repo.*

**Example** - 1M records in `exampleapp.baz` model, all in sync::

    $> ./manage.py updatedata exampleapp.baz -p
    Update mode: settings.py --> fast
    Default querysize: 10000
    Models:
    - exampleapp.baz
      Fields: foo_bar_baz
      Records: 1000000
      Querysize: 10000
      Progress: 100%|████████████████████████████| 1000000/1000000 [00:24<00:00, 41090.11 rec/s]

    Total update time: 0:00:24

Here we measured the select & eval time of `Baz.foo_bar_baz` (which happens to be the only computed
field on that model), for 1M records. Though we did not measure any update time yet, since the values
are already in sync (the update resolver skips updates of unchanged fields).

Now lets forcefully desync all 1M records (in the mangement shell)::

    >>> from exampleapp.models import Baz
    >>> Baz.objects.all().update(foo_bar_baz='')
    1000000

and double check things with `checkdata`::

    $> ./manage.py checkdata exampleapp.baz -p
    - exampleapp.baz
      Fields: foo_bar_baz
      Records: 1000000
      Check: 100%|███████████████████████████████| 1000000/1000000 [00:21<00:00, 47082.86 rec/s]
      Desync: 1000000 records (100.0%)
      Tainted dependants:
        └─ exampleapp.foo: bazzes (~1000 records)

    Total check time: 0:00:21

100% desync - ok we are good to go and can test the the full select & eval & update costs::

    $> ./manage.py updatedata exampleapp.baz -p
    Update mode: settings.py --> fast
    Default querysize: 10000
    Models:
    - exampleapp.baz
      Fields: foo_bar_baz
      Records: 1000000
      Querysize: 10000
      Progress: 100%|████████████████████████████| 1000000/1000000 [00:37<00:00, 26634.51 rec/s]

    Total update time: 0:00:37

As expected this runs a lot slower, almost at only half the speed (yes, updates in relational databases
are very expensive). But there is also a catch here - `Baz.foo_bar_baz` is actually a source field
for another computed field `Foo.bazzes`, as indicated by the `checkdata` output. Thus we added
more work than only updates on `Baz.foo_bar_baz`, also adding select & eval on `Foo.bazzes`.
(And since `Foo.bazzes` did not really change from the initial sync state, the resolver would see
them unchanged and not update anything).

The update speed is still quite high, which is possible due to using the `fast` update mode.
With `bulk` it already drops to 4600 rec/s (3:30 min), with `loop` we are at 240 rec/s (1h 10 min).
Therefore it might be a good idea to activate ``COMPUTEDFIELDS_FASTUPDATE`` in `settings.py` for
update intensive projects.

The example already contains another optimization discussed below - a `select_related` entry for
`Baz.foo_bar_baz`. Without it, the record throughput drops to 1500 - 2000 rec/s for `fast` or `bulk`.


Using `update_fields`
^^^^^^^^^^^^^^^^^^^^^

Django's ORM supports partial model instance updates by providing `update_fields` to ``save``.
This is a great way to lower the update penalty by limiting the DB writes to fields that actually changed.
To keep computed fields in sync with partial writes, the resolver will expand `update_fields` by computed fields,
that have dependency intersections, example:

.. code-block:: python

    class MyModel(ComputedFieldsModel):
        name = models.CharField(max_length=256)

        @computed(models.CharField(max_length=256), depends=[('self', ['name'])])
        def uppername(self):
            return self.name.upper()

    my_model.name = 'abc'
    my_model.save(update_fields=['name'])   # expanded to ['name', 'uppername']

This deviation from Django's default behavior favours data integrity over strict field listing.

.. NOTE::

    The `update_fields` expansion currently works only in the normal field --> computed fields direction,
    not the opposite way. This means, that you can craft a desync value by accident, if you placed
    the computed field's name manually in `update_fields`, but forgot to list the original source field.
    For the example above calling ``my_model.save(update_fields=['uppername'])`` after a change to
    `my_model.name` will create such a desync value. You can easily avoid that by never placing any
    computed field names into `update_fields` yourself (just let the resolver do its job).


Using `select_related`
^^^^^^^^^^^^^^^^^^^^^^

With the `select_related` argument of the `@computed` decorator you can pass along field lookups
to be joined into the select for update queryset used by the update resolver:

.. code-block:: python

    class MyComputedModel(ComputedFieldsModel):
        ...
        a = models.ForeignKey(OtherModel, ...)

        @computed(Field(...),
            depends=[
                ('a', ['field_on_a']),
                ('a.b.c', ['field_on_c'])
            ],
            select_related = ['a', 'a__b__c']
        )
        def compA(self):
            a_field = self.a.field_on_a         # normally creates a query into fk model
            c_field = self.a.b.c.field_on_c     # normally creates a query into c model
            return some_calc(a_field, c_field)

        @computed(Field(...),
            depends=[
                ('a.b', ['field_on_b'])
            ],
            select_related = ['a__b']
        )
        def compB(self):
            b_field = self.a.field_on_b         # normally creates a query into b model
            return some_calc(b_field)


This is a good way to keep the query load low for (nested) fk relations used in computed fields.
In the example above a full update without using `select_related` normally would create 3
additional subqueries per instance. With using `select_related` there are no additional subqueries
to perform at all, since the initial select for update queryset already has those fields loaded.

`When to apply this optimization?`

You can try to use it for fk forward relations in dependencies. Imagine in the example above,
that any `OtherModel` instance links to ~100 `MyComputedModel` instances. Now when an `OtherModel`
instance changes, the update resolver has to walk the dependency in reverse order, thus doing a `1:n` update.
With n=100 we already have to do 300 subqueries just to pull all the needed data,
plus one initial query to select instances for update plus one final save query.
Makes 302 queries in total. By using `select_related` we can drop that to just 2 queries.

Of course this does not come for free - multiple n:1 relations put into `select_related` will grow
the temporary JOIN table rather quick, possibly leading to memory / performance issues on the DBMS.
This is also the reason, why it is not enabled by default.

.. TIP::

    The resolver batches computed field update queries itself with `bulk_update` and a default batch size
    of 100. This can be further tweaked project-wide in `settings.py` with ``COMPUTEDFIELDS_BATCHSIZE``.


Using `prefetch_related`
^^^^^^^^^^^^^^^^^^^^^^^^

The `@computed` decorator also allows to pass along `prefetch_related` field lookups to be used with
the select for update queryset.

Other than for `select_related` above, basic rules when and how to use `prefetch_related` are much harder to find,
as it depends alot on the circumstances, from model / DB schematics down to plain record count. `prefetch_related`
is where the real ORM-Fu starts, where some knowledge about relational algebra will save you from performance hell.

`Any basics to still get started with it for computed fields?`

Well yes, as a rule of thumb - as soon as you have a reverse fk relation in some dependency chain, there is a high
chance to benefit from a `prefetch_related` lookup. This is also true for m2m relations, as they are `reverse_fk.fk`
relation on DB level. But more on m2m relations in the next section.

Lets try to tackle prefetch with a simple example:

.. code-block:: python

    class Foo(models.Model):
        fieldX = SomeConcreteField(...)
        b = models.ForeignKey('Bar', related_name='foos')

    class Bar(ComputedFieldsModel):
        @computed(Field(...),
            depends=[
                ('foos', ['fieldX'])
            ],
            prefetch_related=['foos']   # is that any helpful here?
        )
        def comp(self):
            result = 0
            for foo in self.foos.all():
                # do something with foo.fieldX
                result += foo.fieldX
            return result

This is the most basic example with a reverse fk relation. `comp` does some aggregation of `fieldX` on all linked `foos`.
To decide, whether the prefetch lookup shows any benefit, depends on how your application is going to update `Foo` instances
later on:

- 1-case: always done as single instance saves (including `instance.save()` loops)
- `n`-cases: likely to be done in batches / bulk actions

For 1-case updates the prefetch rule will behave worse, it will create another rather expensive query to be merged on
the update queryset in Python for just one `Bar` instance, while the relational manager access in the method
(touching `self.foos`) would get the linked `Foo` items much cheaper with a prefiltered subquery.

But the picture changes dramatically for `n`-cases update. Without the prefetch rule the related manager access
would have to query `n` times for the related `Foo` items with possible intersections, which creates a lot of
nonsense database load. With the prefetch rule in place you basically replaced those additional subqueries by just
one additional prefetch lookup, saving alot of DB lookups and ORM object mangeling.

Of course there is a downside - the prefetched lookup has to be held in memory and gets merged on Python side,
which might show negative impact for very large prefetchs. Still for most scenarios prefetching will show a much better
performance. (Also consult Django docs about `prefetch_related`).

Let's go one step further and extend the example by another fk relation behind the reverse one:

.. code-block:: python

    class Foo(models.Model):
        fieldX = SomeConcreteField(...)
        b = models.ForeignKey('Bar', related_name='foos')
        c = models.ForeignKey('Baz', related_name='foos')

    class Bar(ComputedFieldsModel):
        @computed(Field(...),
            depends=[
                ('foos.c', ['some_baz_field'])
            ],
            prefetch_related=['foos__c']        # extended to contain Baz values
        )
        def comp(self):
            result = 0
            for foo in self.foos.all():
                # do something with foo.c.some_baz_field
                result += foo.c.some_baz_field
            return result

With this you changed the chances, that multiple instances of `Foo` might be seen as changed at once by
the update resolver, as a single change of a `Baz` instance might link to multiple `foos`. Here the
resolver would have to do an n-cases update for the computed field `comp`, which qualifies for
a prefetch lookup.

Furthermore we extended the prefetch rule to also contain values from `Baz`, which lifts the need for
additional subqueries from the `some_baz_field` access in the code. This also could have been achieved
by a nested `select_related` lookup on a custom queryset definition with a `Prefetch` object, resulting
in slightly different queries and runtime needs.

`What? There are several ways to get the same update behavior, but with different query needs?`

Yes. We are now at the point, where ideal shaping of prefetch lookups gets really tricky, as it depends on
shifting soft criteria of your project needs (e.g. likelihood of doing 1-case vs. n-case changes for certain models,
number of total records, number of related records). Whether your application really can gain anything
from a particular prefetch lookup, should be profiled against typical actions of your business logic,
maybe in conjunction with some relational algebra analysis. It is this point, where a certain prefetch rule might
give you a really nice performance boost in one spot, while performance suffers badly in others.
If you end up at that level, you probably should resort things to your very own solution without using
:mod:`django-computedfields` for that particular task.

.. TIP::

    Try to avoid deep nested or complicated dependencies, they will lead to toxic "update pressure".
    For nested dependencies, that cannot be simplified further, try to apply prefetch lookups to
    restore some of the performance.


M2M relations
^^^^^^^^^^^^^

M2M relations are the logical continuation of the section above - they always fall under the category
of "complicated dependencies". On relational level m2m fields are in fact `n:1:m` relations, where the `1`
is an entry in the join table linking with foreign keys to the `n` and `m` ends.

For computed fields, whose dependencies span over m2m relations, this means, that you almost always
should apply a prefetch lookup. Let's look at the m2m example we used above, but slightly changed:

.. code-block:: python

    class Person(ComputedFieldsModel):
        name = models.CharField(max_length=32)

        @computed(models.CharField(max_length=256),
            depends=[('groups', ['name'])],
            prefetch_related=['groups']
        )
        def groupnames(self):
            if not self.pk:
                return ''
            names = []
            for group in self.groups.all():
                names.append(group.name)
            return ','.join(names)

    class Group(models.Model):
        name = models.CharField(max_length=32)
        members = models.ManyToManyField(Person, related_name='groups')

Here the `groups` access gets optimized by prefetching the items, which again helps, if we do an n-cases
update to `Person`. Since m2m relations are meant as set operations, we have a rather high chance to trigger
multiple updates on `Person` at once. Thus using prefetch is a good idea here.

With the `through` model Django offers a way, to customize the join table of m2m relations. As noted above,
it is also possible to place computed fields on the `through` model, or to pull data from it to either side
of the m2m relations via the fk relations. In terms of optimized computed field updates there is a catch
though:

.. code-block:: python

    class Person(ComputedFieldsModel):
        name = models.CharField(max_length=32)

        @computed(models.CharField(max_length=256),
            depends=[
                ('memberships', ['joined_at']),
                ('memberships.group', ['name'])         # replaces groups.name dep
            ],
            prefetch_related=['memberships__group']
        )
        def groupjoins(self):
            if not self.pk:
                return ''
            names = []
            for membership in self.memberships.all():   # not using groups anymore
                names.append('{}: joined at {}'.format(
                    membership.group.name, membership.joined_at))
            return ','.join(names)

    class Group(models.Model):
        name = models.CharField(max_length=32)
        members = models.ManyToManyField(Person, related_name='groups', through='Membership')

    class Membership(models.Model):
        person = models.ForeignKey(Person, related_name='memberships')
        group = models.ForeignKey(Group, related_name='memberships')
        joined_at = SomeDateField(...)

You should avoid listing the m2m relation and the `through` relations at the same time in `depends`,
as it will double certain update tasks. Instead rework your m2m dependencies to use the `through` relation,
and place appropriate prefetch lookups for them.

Another catch with m2m relations and their manager set methods is a high update pressure in general.
This comes from the fact that a set method may alter dependent computed fields on both m2m ends,
therefore the resolver has to trigger a full update into both directions. Currently this cannot be avoided,
since the `m2m_changed` signal does not provide enough details about the affected relation. This is also
the reason, why the resolver cannot autoexpand dependencies into the `through` model itself. Thus regarding
performance you should be careful with multiple m2m relations on a model or computed fields with dependencies
crossing m2m relations forth and back.

.. TIP::

    Performance tip regarding m2m relations - don't use them with computed fields.

    Avoid depending a computed field on another computed field, that lives behind an m2m relation.
    It surely will scale bad with any reasonable record count later on leading to expensive
    repeated update roundtrips with "coffee break" quality for your business logic.


"One batch to bind 'em all ..."
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

As anyone working with Django knows, inserting/updating big batches of data can get you into serious
runtime troubles with the default model instance approach. In conjunction with computed fields
you will hit that ground much earlier, as even the simplest computed field with just one foreign key relation
at least doubles the query load, plus the time to run the associated field method, example:

.. code-block:: python

    class SimpleComputed(ComputedFieldsModel):
        fk = models.ForeignKey(OtherModel, ...)

        @computed(Field(...), depends=[('fk', ['some_field'])])
        def comp(self):
            return self.fk.some_field

    ...
    # naive batch import with single model instance creation
    for d in data:
        obj = SimpleComputed(**d)
        obj.save()

Here ``obj.save()`` will do an additional lookup in ``OtherModel`` to get `comp` calculated,
before it can save the instance. This will get worse the more computed fields with dependencies the instance has.

To overcome these bottlenecks of the instance model approach, the ORM offers a bunch of bulk actions,
that regain performance by operating more close to the DB/SQL level.

.. WARNING::

    Using bulk actions does not update dependent computed fields automatically anymore. You have to trigger
    the updates yourself by calling `update_dependent`.

`update_dependent` is in fact the "main gateway" of the update resolver, it is also used internally for updates
triggered by instance signals. So lets have a look on how that function can be used and its catches.

Given that you want to update `some_field` on several instances of `OtherModel` of the example above.
The single instance approach would look like this:

.. code-block:: python

    new_value = ...
    for item in OtherModel.objects.filter(some_condition):
        item.some_field = new_value
        item.save()                     # correctly updates related SimpleComputed.comp

which correctly deals with computed field updates though the instance signals. But in the background
in fact this happens:

.. code-block:: python

    new_value = ...
    for item in OtherModel.objects.filter(some_condition):
        item.some_field = new_value
        save()
        # post_save signal:
            update_dependent(item, old)         # full refesh on dependents

Yes, we actually called `updated_dependent` over and over. For the single instance signal hooks there is
no other way to guarantee data integrity in between, thus we have to do the full roundtrip for each call
(the roundtrip itself is rather cheap in this example, but might be much more expensive with more
complicated dependencies).

With a bulk action this can be rewritten much shorter:

.. code-block:: python

    new_value = ...
    OtherModel.objects.filter(some_condition).update(some_field=new_value)
    # caution: here computed fields are not in sync
    ...
    # explicitly resync them
    update_dependent(OtherModel.objects.filter(some_condition), update_fields=['some_field'])

which reduces the workload by far. But note that it also reveals the desync state of the database to Python,
therefore it might be a good idea not to do any business critical actions between the bulk action and the resync.
This can be ensured by placing everything under a transaction:

.. code-block:: python

    new_value = ...
    with transaction.atomic():
        OtherModel.objects.filter(some_condition).update(some_field=new_value)
        update_dependent(OtherModel.objects.filter(some_condition), update_fields=['some_field'])

Of course there is a catch in using `update_dependent` directly - bulk actions altering fk relations
need another preparation step, if they are part of a computed field dependency as reverse relation:

.. code-block:: python

    class Parent(ComputedFieldsModel):
        @computed(models.IntegerField(), depends=[('children', ['parent'])])
        def number_of_children(self):
            return self.children.all().count()

    class Child(models.Model):
        parent = models.ForeignKey(Parent, related_name='children', on_delete=models.CASCADE)

    ...
    # moving children to new parent by some bulk action
    with transaction.atomic():
        old = preupdate_dependent(Child.objects.filter(some_condition))
        Child.objects.filter(some_condition).update(parent=new_parent)
        update_dependent(Child.objects.filter(some_condition), old=old)

Here `preupdate_dependent` will collect `Parent` instances before the the bulk change. We can feed the old
relations back to `update_dependent` with the `old` keyword, so parents, that just lost some children,
will be updated as well.

But looking at the example code it is not quite obvious, when you have to do this, as the fact is hidden
behind the related name in `depends` of some computed field elsewhere. Therefore
:mod:`django-computedfields` exposes a map containing contributing fk relations:

.. code-block:: python

    from computedfields.models import get_contributing_fks
    fk_map = get_contributing_fks()
    fk_map[Child]   # outputs {'parent'}

    # or programatically (done similar in pre_save signal hook for instance.save)
    old = None
    if model in fk_map:
        old = preupdate_dependent(model.objects...)
    model.objects.your_bulk_action()
    update_dependent(model.objects..., old=old)

.. NOTE::

    When using bulk actions and `update_dependent` yourself, always make sure, that
    the given querysets correctly reflect the changeset made by the bulk action.
    If in doubt, expand the queryset to a superset to not miss records by accident. Special care
    is needed for bulk actions, that alter fk relations itself.

.. admonition:: A note on raw SQL updates...

    Technically it is also possible to resync computed fields with the help of `update_dependent`
    after updates done by raw SQL queries. For that feed a model queryset reflecting the table,
    optionally filtered by the altered pks, back to `update_dependent`. To further narrow down
    the triggered updates, set `update_fields` to altered field names (watch out to correctly
    translate `db_column` back to the ORM field name).


Complicated & Deep nested
^^^^^^^^^^^^^^^^^^^^^^^^^

or `"How to stall the DMBS for sure"`

So you really want to declare computed fields with dependencies like:

.. code-block:: python

    class X(ComputedFieldsModel):
        a = models.ForeignKey(OtherModel, ...)

        @computed(Field(..),
            depends=[
                ('a', ['a1', 'a2', ...]),
                ('a.b_reverse', ['b1', 'b2', ...]),
                ('a.b_reverse.c', ['c1', 'c2', ...]),
                ('a.b_reverse.c.d_reverse', ['d1', 'd2', ...]),
                ('...very_deep' , [...])
            ],
            prefetch_related=[]     # HELP, what to put here?
        )
        def busy_is_better(self):
            # 1000+ lines of code following here
            ...

To make it short - yes that is possible as long as things are cycle-free. Should you do that - probably not.

:mod:`django-computedfields` might look like a hammer, but it should not turn all your database needs
into a nail. Maybe look for some better suited tools crafted for reporting needs.


.. _memory-issues:

Avoiding memory issues
----------------------

Once your tables reach a reasonable size, the memory needs of the update resolver might get out of hand
without further precautions. The high memory usage mainly comes from the fact, that the ORM will try to
cache model instances, when evaluated directly. For computed fields there are several factors,
that make high memory usage more likely:

- big record count addressed by a single `update_dependent` call
- expensive `select_related` and `prefetch_related` rules on computed fields
- deep nested dependencies or recursions

While the first two simply take more space for having more instances to process or to preload,
the last point might multiply those needs during DFS tree update (higher levels in the tree have to be held in memory).
For recursions this will grow exponentially based on recursion depth and branching factor.

With version 0.2.0 :mod:`django-computedfields` introduced a new global setting ``COMPUTEDFIELDS_QUERYSIZE``
and a new argument `querysize` on the ``computed`` decorator to mitigate those memory issues globally or
at individual field level.

Note that the memory usage is hard to estimate upfront. If you operate under strict memory conditions with big tables,
you probably should try to measure memory peaking of your business actions in a development system beforehand,
while adjusting the querysize parameters.

Some basic rules regarding querysize:

- If your logic only operates on single model instances, you are good to go by ignoring the querysize settings.
  (There are some exceptions like deep nested recursive dependencies spanning their own big trees, see below.)
- Huge bulk operations, like calling the `updatedata` command, will suffer first. This can be used to get an idea
  of the current memory situation for your declared computed fields. Furthermore `updatedata` and `checkdata`
  support an explicit querysize parameter, which might come handy to find a more appropriate setting for
  ``COMPUTEDFIELDS_QUERYSIZE`` in your project.
- If you have almost equally expensive computed fields in terms of memory usage, adjust the global value
  ``COMPUTEDFIELDS_QUERYSIZE`` to your needs.
- If there are a few naughty computed fields pulling tons of dependencies, their querysize can be lowered
  individually on the computed field:

  .. code-block:: python

      # field selects overly much data for the update,
      # so limit from COMPUTEDFIELDS_QUERYSIZE is still too high
      # --> limit it further individually
      @computed(..., depends=[...], querysize=100)
      def naughty_deps(self):
          ...

- Recursive dependencies are the worst and their memory needs will grow exponentially from the recursion depth
  and branching factor. They typically qualify for very low individual querysize, where you have to pay
  limited memory with a much higher runtime. Once you reached `querysize=1`, you have tamed the memory beast
  into linear growing from recursion depth, but might want to take a day off, before the update returns.
  (Seriously, get more RAM or rework your fields to be less "explosive". While the runtime-for-space-deal
  works in both directions, more space is typically the cheaper and better scaling one in long term.)

.. NOTE::

    The resolver determines the real querysize for a certain `ComputedFieldsModel` by pulling the lowest
    querysize of all to be updated computed fields. Thus it is technically possible to increase the querysize
    for a model above ``COMPUTEDFIELDS_QUERYSIZE`` by applying higher `querysize` values to all its computed fields.
    Such a sophisticated fine-tuning might help, if you have identified a big bulk update on one model as the
    main bottleneck in your business actions, while keeping other uncritical updates at lower throughput and memory.
