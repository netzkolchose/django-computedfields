User Guide
==========

:mod:`django-computedfields` provides autoupdated database fields for
model methods.


Installation
------------

Install the package with pip:

.. code:: bash

    $ pip install django-computedfields

and add ``computedfields`` to your ``INSTALLED_APPS``.

To render the update dependency graph during development, also install :mod:`graphviz`:

.. code:: bash

    $ pip install graphviz


Settings
--------

The module respects optional settings in `settings.py`:

- ``COMPUTEDFIELDS_ADMIN``
    Set this to ``True`` to get a listing of ``ComputedFieldsModel`` models with their field
    dependencies in admin. Useful during development.

- ``COMPUTEDFIELDS_ALLOW_RECURSION``
    Normally cycling updates to the same model field indicate an error in database design.
    Therefore the dependency resolver raises a ``CycleNodeException`` if a cycle was
    encountered. For more complicated setups (like tree structures) you can disable the
    recursion check. This comes with the drawback, that the underlying graph cannot
    linearize and optimize the update paths anymore.

- ``COMPUTEDFIELDS_BATCHSIZE_BULK`` and ``COMPUTEDFIELDS_BATCHSIZE_FAST``
    Set the batch size used for computed field updates by the auto resolver.
    Internally the resolver updates computed fields either by `bulk_update` or `fast_update`,
    which might penalize update performance for very big updates due high memory usage or
    expensive SQL evaluation, if done in a single update statement. Here batch size will split
    the update into smaller batches of the given size. For `bulk_update` reasonable batch sizes
    are typically between 100 to 1000 (going much higher will degrade performance a lot with
    `bulk_update`), for `fast_update` higher values in 10k to 100k are still reasonable,
    if RAM usage is no concern. If not explicitly set in `settings.py` the default value will be
    set to 100 for `bulk_update` and 10k for `fast_update`.
    The batch size might be further restricted by certain database adapters.

- ``COMPUTEDFIELDS_FASTUPDATE`` (Beta)
    Set this to ``True`` to use `fast_update` from  :mod:`django-fast-update` instead of
    `bulk_update`. This is recommended if you face serious update pressure from computed fields,
    and will speed up writing to the database by multitudes. While :mod:`django-computedfields`
    depends on the package by default (gets installed automatically), it does not enable it yet.
    This is likely to change once :mod:`django-fast-update` has seen more in-the-wild testing and fixes.
    Note that `fast_update` relies on recent database versions (see `package description
    <https://github.com/netzkolchose/django-fast-update>`_).

- ``COMPUTEDFIELDS_QUERYSIZE``
    Limits the query size used by the resolver to slices of the given value (global default is 10k).
    This setting is mainly to avoid excessive memory usage from big querysets, where a direct
    evaluation would try to cache everything into RAM. The global setting acts as a "damper" on all
    reading querysets invoked by the resolver.

    The querysize can be further adjusted for individual computed fields as optional argument `querysize`
    on the ``@computed`` decorator. This is especially useful, if a field has overly complicated
    dependencies pulling much more into memory than other fields. Also see :ref:`memory-issues` in examples.


Basic usage
-----------

Simply derive your model from ``ComputedFieldsModel`` and place
the ``@computed`` decorator on a method:

.. code-block:: python

    from django.db import models
    from computedfields.models import ComputedFieldsModel, computed, compute

    class Person(ComputedFieldsModel):
        forename = models.CharField(max_length=32)
        surname = models.CharField(max_length=32)

        @computed(models.CharField(max_length=32), depends=[('self', ['surname', 'forename'])])
        def combined(self):
            return f'{self.surname}, {self.forename}'

``combined`` will be turned into a real database field and can be accessed
and searched like any other database field. During saving the associated method gets called
and its result written to the database. With ``compute(instance, 'fieldname')`` you can
inspect the value that will be written, which is useful if you have pending
changes:

    >>> person = Person(forename='Leeroy', surname='Jenkins')
    >>> person.combined             # empty since not saved yet
    >>> compute(person, 'combined') # outputs 'Jenkins, Leeroy'
    >>> person.save()
    >>> person.combined             # outputs 'Jenkins, Leeroy'
    >>> Person.objects.filter(combined__<some condition>)  # used in a queryset

The ``@computed`` decorator expects a model field instance as first argument to hold the
result of the decorated method.


Alternative Syntax
------------------

For a more declarative code style you can use the ``ComputedField`` factory method instead
(since version 2.4.0):

.. code-block:: python

    from django.db import models
    from computedfields.models import ComputedFieldsModel, ComputedField

    class Person(ComputedFieldsModel):
        forename = models.CharField(max_length=32)
        surname = models.CharField(max_length=32)
        combined = ComputedField(
            models.CharField(max_length=32),
            depends=[('self', ['surname', 'forename'])],
            compute=lambda inst: f'{inst.surname}, {inst.forename}'
        )

which yields the same behavior as the decorator. ``ComputedField`` expects
the same arguments as the decorator, plus the compute function as ``compute``.
The compute function should expect a model instance as single argument.

While the code examples of this guide use only the decorator syntax,
they also apply to the declarative syntax with ``ComputedField``.


Automatic Updates
-----------------

The  `depends` keyword argument can be used with any relation
to indicate dependencies to fields on other models as well.

The example above extended by a model ``Address``:

.. code-block:: python

    class Address(ComputedFieldsModel):
        person = models.ForeignKeyField(Person)
        street = models.CharField(max_length=32)
        postal = models.CharField(max_length=32)
        city = models.CharField(max_length=32)

        @computed(models.CharField(max_length=256), depends=[
            ('self', ['street', 'postal', 'city']),
            ('person', ['combined'])
        ])
        def full_address(self):
            return f'{self.person.combined}, {self.street}, {self.postal} {self.city}'

Now a change to ``self.street``, ``self.postal``, ``self.city`` or ``person.combined``
will update ``full_address``. Also changing ``self.person`` will trigger an update of ``full_address``.

Dependencies should be listed as ``['relation_path', list_of_concrete_fieldnames]``.
The relation path can span serveral models, simply name the relation
in python style with a dot (e.g. ``'a.b.c'``). A relation can be any of
foreign key, m2m, o2o and their back relations.
The fieldnames should be a list of strings of concrete fields on the foreign model the method
pulls data from.

.. NOTE::

    The example above contains a special depends rule with ``'self'`` as relation name.
    While it looks awkward to declare model local dependencies explicitly, it is needed
    to correctly trigger computed field updates under any circumstances.
    
    Rule of thumb regarding `depends` - list **ALL** concrete fields a computed field pulls data from,
    even local ones with ``'self'``. Also see examples for further details and more complicated
    situations with annotated fields.

.. NOTE::

    If you allow relations to contain ``NULL`` values you have to handle this case explicitly:

    .. CODE:: python

        @computed(models.CharField(max_length=32), depends=[('nullable_relation', ['field'])])
        def compfield(self):
            # special handling of NULL here as access to
            # self.nullable_relation.field would fail
            if not self.nullable_relation:
                return 'something else'
            # normal invocation with correct data pull across correct relation
            return self.nullable_relation.field

    A special case in this regard are m2m relations (and also backrelations under Django >=4.1)
    during the first save of a newly created instance, which cannot access the relation yet.
    You have to handle this case explicitly:

    .. CODE:: python

        @computed(models.CharField(max_length=32), depends=[('m2m', ['field'])])
        def compfield(self):
            # no pk yet, access to .m2m will fail
            if not self.pk:
                return ''
            # normal data pull across m2m relation
            return ''.join(self.m2m.all().values_list('field', flat=True))

    Pulling field dependencies over m2m relations has several more drawbacks, in general
    it is a good idea to avoid m2m relations in `depends` as much as possible.
    Also see examples about m2m relations.

.. WARNING::

    With `depends` rules you can easily end up with recursive updates.
    The dependency resolver tries to detect cycling dependencies and might
    raise a ``CycleNodeException`` during startup.


Custom `save` method
--------------------

If you have a custom ``save`` method defined on your model, it is important to note,
that by default local computed field values are not yet updated to their new values during the invocation,
as this happens in ``ComputedFieldModel.save`` afterwards. Thus code in ``save`` still sees old values.

With the decorator ``@precomputed`` you can change that behavior to also update computed fields
before entering your custom save method:

.. code-block:: python

    class SomeModel(ComputedFieldsModel):
        fieldA = ...

        @computed(..., depends=[('self', ['fieldA'])])
        def comp(self):
            # do something with self.fieldA
            return ...
        
        @precomputed
        def save(self, *args, **kwargs):
            # with @precomputed self.comp already contains
            # the updated value based on self.fieldA changes
            ...
            super(SomeModel, self).save(*args, **kwargs)

It is also possible to further customize the update behavior by applying `skip_computedfields=True`
to ``save`` or by using the ``precomputed`` decorator with the keyword argument `skip_after=True`.
Both will skip the late field updates done by default in ``ComputedFieldModel.save``, thus you have to
make sure to correctly update field values yourself, e.g. by calling ``update_computedfields`` manually.

Fur further guidance see API docs and the source of :meth:`ComputedFieldsModel.save<.models.ComputedFieldsModel.save>` and
:meth:`@precomputed<.resolver.Resolver.precomputed>`.


How does it work internally?
----------------------------

On django startup the dependency resolver collects registered models and computed fields.
Once all project-wide models are constructed and available (on ``app.ready``)
the models and fields are merged and resolved into model and field endpoints.

In the next step the dependency endpoints and computed fields are converted into an adjacency list and inserted
into a directed graph (inter-model dependency graph). The graph does a cycle check during path linearization and
removes redundant subpaths. The remaining edges are converted into a reverse lookup map containing source models
and computed fields to be updated with their queryset access string. For model local field dependencies a similar
graph reduction per model takes place, returning an MRO for local computed fields methods. Finally a union graph of
inter-model and local dependencies is build and does a last cycle check.

During runtime certain signal handlers in `handlers.py` hook into model instance actions and trigger
the needed additional changes on associated computed fields given by the resolver maps.
The signal handlers itself call into ``update_dependent``, which creates select querysets for all needed
computed field updates.

In the next step ``resolver.bulk_updater`` applies `select_related` and `prefetch_related` optimizations
to the queryset (if defined) and executes the queryset pulling all possible affected records. It walks the
instances calculating computed field values in in topological order and places the results
in the database by batched `bulk_update` calls.

If another computed field on a different model depends on these changes the process repeats until all
computed fields have been finally updated.

.. NOTE::

    Computed field updates on foreign models are guarded by transactions and get triggered by a `post_save`
    signal handler. Their database values are always in sync between two database relevant model instance
    actions in Python, unless a transaction error occured. Note that this transaction guard does not include
    local computed fields, as they are recalculated during a normal ``save()`` call prior the foreign dependency
    handling. It is your own responsibility to apply appropriate guards over a batch of model instances.
    
    For more advanced usage in conjunction with bulk actions and `update_dependent` see below and in the
    examples documentation.

On ORM level all updates are turned into select querysets filtering on dependent computed field models
in ``update_dependent``. A dependency like ``['a.b.c', [...]]`` of a computed field on model `X` will either
be turned into a queryset like ``X.objects.filter(a__b__c=instance)`` or ``X.objects.filter(a__b__c__in=instance)``,
depending on `instance` being a single model instance or a queryset of model `C`.

The auto resolver only triggers field updates for real values changes by comparing old and new value.
If a `depends` rule contains a 1:`n` relation (reverse fk relation), ``update_dependent`` additionally updates
old relations, that were grabbed by a `pre_save` signal handler.
Similar measures to catch old relations are in place for m2m relations and delete actions (see `handlers.py`).

.. NOTE::

    The fact that you have list all field dependencies explicitly would allow another aggressive optimization in
    the resolver by filtering the select for update queryset for tracked concrete field changes.
    But to achieve arbitrary concrete field change tracking, a before-after comparison is needed, either by
    another SELECT query, or by some copy-on-write logic on any dependency chain model field.
    Currently both seems inappropriate, compared to a slightly sub-optimal single SELECT query for pending updates.


Advanced Bulk Usage
-------------------

The runtime model described above does not work with bulk actions.
:mod:`django-computedfields` still can be used in combination with bulk actions,
but you have to trigger the needed updates yourself by calling ``update_dependent``, example:

    >>> from computedfields.models import update_dependent
    >>> Entry.objects.filter(pub_date__year=2010).update(comments_on=False)
    >>> update_dependent(Entry.objects.filter(pub_date__year=2010))

Special care is needed, if the bulk changes involve foreign key fields itself,
that are part of a dependency chain. Here related computed model instances have to be collected
before doing the bulk change to correctly update the old relations as well after the bulk action took place:

    >>> # given: some computed fields model depends somehow on Entry.fk_field
    >>> from computedfields.models import update_dependent, preupdate_dependent
    >>> old_relations = preupdate_dependent(Entry.objects.filter(pub_date__year=2010))
    >>> Entry.objects.filter(pub_date__year=2010).update(fk_field=new_related_obj)
    >>> update_dependent(Entry.objects.filter(pub_date__year=2010), old=old_relations)

.. NOTE::

    Handling of old relations doubles the needed database interactions and should not be used,
    if the bulk action does not involve any relation updates at all. It can also be skipped,
    if the foreign key fields do not contribute to a computed field. Since this is sometimes hard to spot,
    :mod:`django-computedfields` provides a convenient mapping of models and their
    contributing foreign key fields accessible by ``get_contributing_fks()`` or as admin view
    (if ``COMPUTEDFIELDS_ADMIN`` is set).

See method description in the API Reference for further details.


Model Inheritance Support
-------------------------

Abstract Base Classes
^^^^^^^^^^^^^^^^^^^^^

Computed fields are fully supported with abstract model class inheritance. They can be defined
on abstract models or on the final model. They are treated as local computed fields on the final model.

Multi Table Inheritance
^^^^^^^^^^^^^^^^^^^^^^^

Multi table inheritance is supported with the following restriction:

.. NOTE::

    **No automatic up- or downcasting** - the resolver strictly limits updates to model types listed in `depends`.
    Also see example documentation on how to expand updates to neighboring model types manually.


Proxy Models
^^^^^^^^^^^^

Computed fields cannot be placed on proxy models, as it would involve a change to the table,
which is not allowed. Computed fields inherited from the parent model keep working on proxy models
(treated as alias). Constructing depends rules from proxy models is not supported (untested).


f-expressions
-------------

While f-expressions are a nice way to offload some work to the database, they are not supported
with computed fields. In particular this means, that computed fields should not depend on
fields with expression values and should not return expression values itself. This gets not
explicitly tested by the library, so mixing computed field calculations with expressions will
probably lead to weird errors, or even might just work for some edge cases (like strictly sticking
to expression algebra, not using `fast_update` etc).

Note that :mod:`django-computedfields` tries to calculate as much as possible
on python side before invoking the database, which makes f-expressions somewhat to an antithesis
of :mod:`django-computedfields`.


Type Hints
----------

Since version 0.2.0 :mod:`django-computedfields` supports type hints.
A fully type annotated example would look like this:


.. CODE:: python

    from django.db.models import CharField
    from computedfields.models import ComputedFieldsModel, computed
    from typing import cast

    class MyModel(ComputedFieldsModel):
        name: 'CharField[str, str]' = CharField(max_length=32)

        @computed(
            cast('CharField[str, str]', CharField(max_length=32)),
            depends=[('self', ['name'])]
        )
        def upper(self) -> str:
            return self.name.upper()

    # run this in mypy
    reveal_type(MyModel.name)       # Revealed type is "django.db.models.fields.CharField[builtins.str, builtins.str]"
    reveal_type(MyModel().name)     # Revealed type is "builtins.str*"
    reveal_type(MyModel.upper)      # Revealed type is "django.db.models.fields.Field[builtins.str, builtins.str]"
    reveal_type(MyModel().upper)    # Revealed type is "builtins.str*"


This works with any IDE using a recent `mypy` version with :mod:`django-stubs` (while `Visual Studio Code` works,
`PyCharm` does not work, seems it does its own type guessing).

Currently it is needed to explicitly cast the fields as shown above,
otherwise mypy cannot infer the instance field value types properly.

Note, that the field instance on the class got widened to the more general `Field` type,
since :mod:`django-computedfields` does not care about field specifics
(if that is an issue, just cast it back to your more specific field type).

The `depends` argument is typed as ``Sequence[Tuple[str, Sequence[str]]]``.
Note the change of a single depends rule into a tuple, while the other types got widened to a sequence.
While the old format keeps working as before, it is needed to change the rules to a tuple to silence
type warnings, e.g.:

.. CODE:: python

    # marked as wrong now
    @computed(..., depends=[['path', ['list', 'of', 'fieldnames']], ...])
    def ...

    # passes type test
    @computed(..., depends=[('path', ['list', 'of', 'fieldnames']), ...])
    def ...


Management Commands
-------------------

- ``rendergraph <filename>``
    renders the inter-model dependency graph to `filename`. Note that this command currently only handles
    the inter-model graph, not the individual model graphs and final union graph (PRs are welcome).

- ``checkdata``
    checks values for all computed fields of the given models / apps. Unlike `updatedata`, which also does
    an implicit value check during DFS, this is an explicit flat value check without tree descent. Therefore
    it runs much faster in most cases.

    If desync values were found, the command will try to get an idea of tainted follow-up computed fields.
    Note that the tainted information is only a rough indicator of the real desync state in the database,
    as it has no means to do a deep value check of all dependants.

    Supported arguments:

    - ``applabel[.modelname]``
        Check only for models in `applabel`, or model `applabel.modelname`. Leave this empty to check for all
        known computed field models project-wide.
    - ``--progress``
        Show a progressbar during the run (needs :mod:`tqdm` to be installed).
    - ``--querysize NUMBER``
        See ``COMPUTEDFIELDS_QUERYSIZE`` setting.
    - ``--json FILENAME``
        Output desync field data to `FILENAME` as JSONL. Can be used to speedup a later `updatedata` call.
    - ``--silent``
        Silence normal output.
    - ``--skip-tainted``
        Skip scanning for tainted follow-ups.

- ``updatedata``
    does a full update on computed fields and their follow-up dependants of the given models / apps.
    After bigger project manipulations like applying fixtures, heavy migrations or even after a bunch
    of bulk changes without calling `update_dependent`, you might face serious desync issues of
    computed fields (can be checked with `checkdata` command). In such a case use `updatedata` to get
    field values back in sync.

    Supported arguments:

    - ``applabel[.modelname]``
        Update only fields on models in `applabel`, or on model `applabel.modelname`. Leave this empty to update
        all computed fields on all models project-wide.
    - ``--from-json FILENAME``
        Read desync field data from `FILENAME`. The desync data can be created with the ``--json`` argument
        of `checkdata`. Using this mode will greatly lower the needed runtime, as `updatedata` will only
        walk desync'ed fields and its dependants. For CI scripts the commands can be combined similar to this::

            # run updatedata conditionally
            ./manage.py checkdata --json file || ./manage.py updatedata --from-json file
            # pipe desync data through
            ./manage.py checkdata --silent --json - | ./manage.py updatedata --from-json -

        Note that this command mode does not work with applabels or modelnames (always takes models/fields
        from desync data).

    - ``--progress``
        Show a progressbar during the run (needs :mod:`tqdm` to be installed).
    - ``--mode {loop,bulk,fast}``
        Set the update operation mode explicitly. By default either `bulk` or `fast` will be used, depending on
        ``COMPUTEDFIELDS_FASTUPDATE`` in `settings.py`. The mode `loop` resembles the old command behavior
        and will update all computed fields instances by loop-saving. Its usage is strongly discouraged,
        as it shows very bad update performance (can easily take hours to update bigger tables). This argument
        has no effect in conjunction with ``--from-json`` (always uses mode from `settings.py`).
    - ``--querysize NUMBER``
        See ``COMPUTEDFIELDS_QUERYSIZE`` setting.

- ``showdependencies``
    lists all related models and fields on which a computed field depends. While the `depends` rules
    in the code are defined as backward dependencies (`"this computed field shall get updated from ..."`),
    this listing shows the forward dependencies as seen by the resolver after the graph reduction
    (`"a change to this field shall update computed field ..."`). The forward direction makes it a lot easier
    to comprehend, when the resolver kicks in or when you have to call `update_dependent` explicitly after
    bulk actions. The output marks contributing fk fields yellow to emphasize their special need for
    `preupdate_dependent`. The output reads as follows::

        - source_model:
            source_field -> target_model [target_field]

    where a change of `source_model.source_field` should create a recalculation of `target_model.target_field`.
    Note that this listing only contains inter-model and no local field dependencies (`self` rules), thus the
    full inverse cannot be constructed from it.


General Usage Notes
-------------------

:mod:`django-computedfields` provides an easy way to denormalize database data with Django in an automated fashion.
As with any denormalization it should only be used as a last resort to optimize certain query bottlenecks for otherwise
highly normalized data.


Best Practices
^^^^^^^^^^^^^^

- start highly normalized
- cover needed field calculations with field annotations where possible
- do other calculations in normal methods/properties

These steps should be followed first, as they guarantee low to no redundancy of the data if properly done,
before resorting to any denormalization trickery. Of course complicated field calculations create
additional workload either on the database or in Python, which might turn into serious query bottlenecks in your project.

That is the point where :mod:`django-computedfields` can help by creating pre-computed fields.
It can remove the recurring calculation workload during queries by providing precalculated values.
Please keep in mind, that this comes to a price:

- additional space requirement in database
- redundant data (as with any denormalization)
- possible data integrity issues (sync vs. desync state)
- higher project complexity on Django side (signal hooks, ``app.ready`` hook with resolver initialization)
- higher insert/update costs, which might create new bottlenecks

If your project suffers from query bottlenecks created by recurring field calculations and
you have ruled out worse negative side effects from the list above,
:mod:`django-computedfields` can help to speed up some parts of your Django project.


Specific Usage Hints
^^^^^^^^^^^^^^^^^^^^

- Try to avoid deep nested dependencies in general. The way :mod:`django-computedfields` works internally
  will create rather big JOIN tables for many or long relations. If you hit that ground, either try to resort
  to bulk actions with manually using ``update_dependent`` or rework your scheme by introducing additional
  denormalization models or interim computed fields higher up in the dependency chain.
- Try to avoid multiple 1:`n` relations in a dependency chain like ``['fk_back_a.fk_back_b...', [...]]`` or
  ``['m2m_a.m2m_b...', [...]]``, as the query load might explode. Although the auto resolver tries to touch
  affected computed fields only once, it does not help much, if method invocations have to touch 80%
  of all database entries to get the updates done.
- Try to apply `select_related` and `prefetch_related` optimizations for complicated dependencies. While this can
  reduce the query load by far, it also increases memory usage alot, thus it needs proper testing to find the sweep spot.
  Also see optimization examples documentation.
- Try to reduce the "update pressure" by grouping update paths by dimensions like update frequency or update penalty
  (isolate the slowpokes). Mix in fast turning entities late.


Fixtures
--------

:mod:`django-computedfields` skips intermodel computed fields updates during fixtures.
Run the management command `updatedata` after applying fixtures to resynchronize their values.


Migrations
----------

On migration level computed fields are handled as other ordinary concrete fields defined on a model,
thus you can apply any migration to them as with other concrete fields.

Still for computed fields you should not rely on data migrations by default and instead resynchronize
their values manually. If you have made changes to a field, that a computed field depends on
(or a computed field itself), either resynchronize the values by calling `update_dependent` with
a full queryset of the changed model (partial update), or do a full resync with the management command
`updatedata`. The latter should be preferred, if you made several changes or have changes,
that affect relations on the dependency graph.


Motivation
----------

:mod:`django-computedfields` is inspired by odoo's computed fields and the lack of
a similar feature in Django's ORM.


Changelog
---------

- 0.2.9
    - fix related_query_name issue
- 0.2.8
    - Django 5.2 support
- 0.2.7
    - setuptools issue fixed
- 0.2.6
    - Django 5.1 support
- 0.2.5
    - Django 5.0 & Python 3.12 support
    - Django 3.2 support dropped
- 0.2.4
    - performance improvement: use OR for simple multi dependency query construction
    - performance improvement: better queryset narrowing for M2M lookups
    - `ComputedField` for a more declarative code style added
- 0.2.3
    - performance improvement: use UNION for multi dependency query construction
- 0.2.2
    - Django 4.2 support
    - Use `model._base_manager` instead of `model.objects`
- 0.2.1
    - Django 4.1 support
- 0.2.0 - next beta release
    - new features:
        - better memory control for the update resolver via
          ``COMPUTEDFIELDS_QUERYSIZE`` or as argument on ``@computed``
        - update optimization - early update-tree exit
        - faster updates with ``COMPUTEDFIELDS_FASTUPDATE``
        - `checkdata` command
        - `showdependencies` command
        - typing support for computed fields

    - enhancements:
        - better `updatedata` command

    - removed features:
        - transitive reduction on intermodel graph (due to negative impact)
        - pickled resolver map (due to showing low benefit)
        - `update_dependent_multi` and `preupdate_dependent_multi`
          (due to showing low benefit and being a code nuisance)
        - Django 2.2 shims removed

    - bug fixes:
        - regression on proxy models fixed
        - sliced querset support for mysql fixed


- 0.1.7
    - add list type support for ``update_fields`` in signal handlers
- 0.1.6
    - maintenace version with CI test dependencies changes:
        - removed Python 3.6
        - removed Django 2.2
        - added Python 3.10
        - added Django 4.0
        - move dev environment to Python 3.10 and Django 3.2

      Note that Django 2.2 will keep working until real incompatible code changes occur.
      This may happen by any later release, thus treat 0.1.6 as last compatible version.

- 0.1.5
    - fix error on model instance cloning
- 0.1.4
    - Django 3.2 support
- 0.1.3
    - better multi table inheritance support and test cases
    - explicit docs for multi table inheritance
- 0.1.2
    - bugfix: o2o reverse name access
    - add docs about model inheritance support
- 0.1.1
    - bugfix: add missing migration
- 0.1.0
    - fix recursion on empty queryset
    - dependency expansion on M2M fields
    - `m2m_changed` handler with filtering on m2m fields
    - remove custom metaclass, introducing `Resolver` class
    - new decorator `@precomputed` for custom save methods
    - remove old `depends` syntax
    - docs update
- 0.0.23:
    - Bugfix: Fixing leaking computed fields in model inheritance.
- 0.0.22:
    - Automatic dependency expansion on reverse relations.
    - Example documentation.
- 0.0.21:
    - Bugfix: Fixing undefined _batchsize for pickled map usage.
- 0.0.20
    - Use `bulk_update` for computed field updates.
    - Allow custom update optimizations with `select_related` and `prefetch_related`.
    - Respect computed field MRO in `compute`.
    - Allow updates on local computed fields from `update_dependent` simplifying bulk actions on `ComputedFieldsModel`.
- 0.0.19
    - Better graph expansion on relation paths with support for `update_fields`.
- 0.0.18
    - New `depends` syntax deprecating the old one.
    - MRO of local computed field methods implemented.
- 0.0.17
    - Dropped Python 2.7 and Django 1.11 support.
