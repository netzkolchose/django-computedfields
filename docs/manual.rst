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

For graph rendering also install :mod:`graphviz`:

.. code:: bash

    $ pip install graphviz


Settings
--------

The module respects optional settings in settings.py:

- ``COMPUTEDFIELDS_MAP``
    Used to set a file path for the pickled resolver map. To create the pickled resolver map
    point this setting to a writeable path and call the management command ``createmap``.
    This should always be used in production mode in multi process environments
    to avoid the expensive map creation on every process launch. If set, the file must
    be recreated after model changes.

- ``COMPUTEDFIELDS_ADMIN``
    Set this to ``True`` to get a listing of ``ComputedFieldsModel`` models with their field
    dependencies in admin. Useful during development.

- ``COMPUTEDFIELDS_ALLOW_RECURSION``
    Normally cycling updates to the same model field indicate an error in database design.
    Therefore the dependency resolver raises a ``CycleNodeException`` if a cycle was
    encountered. For more complicated setups (like tree structures) you can disable the
    recursion check. This comes with the drawback, that the underlying graph cannot
    linearize and optimize the update paths anymore.


Basic usage
-----------

Simply derive your model from ``ComputedFieldsModel`` and place
the ``@computed`` decorator on a method:

.. code-block:: python

    from django.db import models
    from computedfields.models import ComputedFieldsModel, computed

    class Person(ComputedFieldsModel):
        forename = models.CharField(max_length=32)
        surname = models.CharField(max_length=32)

        @computed(models.CharField(max_length=32))
        def combined(self):
            return u'%s, %s' % (self.surname, self.forename)

``combined`` will be turned into a real database field and can be accessed
and searched like any other database field. During saving the associated method gets called
and it's result written to the database. With the method ``compute('fieldname')`` you can
inspect the value that will be written, which is useful if you have pending
changes:

    >>> person = Person(forename='Leeroy', surname='Jenkins')
    >>> person.combined             # empty since not saved yet
    >>> person.compute('combined')  # outputs 'Jenkins, Leeroy'
    >>> person.save()
    >>> person.combined             # outputs 'Jenkins, Leeroy'
    >>> Person.objects.filter(combined__<some condition>)  # used in a queryset

The ``@computed`` decorator expects a model field as first argument to hold the
result of the decorated method.


Automatic Updates
-----------------

The ``@computed`` decorator understands a keyword argument ``depends`` to indicate
dependencies to related model fields. If set, the computed field gets automatically
updated upon changes of the related fields.

The example above extended by a model ``Address``:

.. code-block:: python

    class Address(ComputedFieldsModel):
        person = models.ForeignKeyField(Person)
        street = models.CharField(max_length=32)
        postal = models.CharField(max_length=32)
        city = models.CharField(max_length=32)

        @computed(models.CharField(max_length=256), depends=['person#combined'])
        def full_address(self):
            return u'%s, %s, %s %s' % (self.person.combined, self.street,
                                       self.postal, self.city)

Now if the name of a person changes, the field ``full_address`` will be updated
accordingly.

Note the format of the depends string - it consists of the relation name
and the field name separated by '#'. The field name is mandatory for any
dependency to trigger a proper update. (In fact it can be omitted for normal
fields if you never use ``.save`` with explicit setting ``update_fields``.
But that is an implementation detail you should not rely on.)
The relation name part can span serveral models, simply name the relation
in python style with a dot (e.g. ``'a.b.c'``).
A relation can be of any of foreign key, m2m, o2o and their back relations.

.. NOTE::

    The computed method gets evaluated in the model instance save method. If you
    allow relations to contain ``NULL`` values you have to handle this case explicitly:

    .. CODE:: python

        @computed(models.CharField(max_length=32), depends=['nullable_relation#field'])
        def compfield(self):
            if not self.nullable_relation:          # special handling of NULL here
                return 'something else'
            return self.nullable_relation.field     # some code referring the correct field

    Computed fields directly depending on m2m relations cannot run the associated
    method successfully on the first ``save`` if the instance was newly created
    (due to Django's order of saving the instance and m2m relations). Therefore
    you have to handle this case explicitly as well:

    .. CODE:: python

        @computed(models.CharField(max_length=32), depends=['m2m#field'])
        def compfield(self):
            if not self.pk:  # no pk yet, access to .m2m will fail
                return ''
            return ''.join(self.m2m.all().values_list('field', flat=True))

    Generally you should avoid nested m2m relations in dependendies
    as much as possible since the update penalty will explode.

.. CAUTION::

    With the depends strings you can easily end up with recursive updates.
    The dependency resolver tries to detect cycling dependencies and might
    raise a ``CycleNodeException``.

.. NOTE::

    Updates of computed fields from fields on the same model behave a little
    different than dependencies to fields on related models. To ensure proper updates,
    either call ``save`` without ``update_fields`` (full save) or
    include the computed fields explicitly in ``update_fields``:

    .. CODE:: python

        address.city = 'New City'
        address.save()                                          # also updates .full_address
        address.save(update_fields=['city'])                    # does not update .full_address
        address.save(update_fields=['city', 'full_address'])    # make it explicit

    Note that there is currently no way to circumvent this slightly different behavior
    due to the way the autoresolver works internally.
    Future versions might allow declarations like ``self#fieldname`` and handle it transparently.


How does it work internally?
----------------------------

``ComputedFieldsModel`` is based on its own metaclass derived from django's model metaclass.
The metaclass collects methods annotated by ``@computed`` and creates the needed database fields
during model construction. Once all project-wide models are constructed and available (on ``app.ready``)
the collected dependency strings are resolved into model and field endpoints with a certain query access string.

In the next step the depend endpoints and computed fields are converted into an adjacency list and inserted
into a directed graph. The graph does a cycle check during path linearization and removes redundant subpaths.
The remaining edges are finally converted into a reverse lookup map containing source models and computed fields
to be updated with their queryset access string. The expensive graph sanitizing process can be skipped
in production by using a precalculated lookup map (see above).

During runtime certain signal handlers in ``handlers.py`` hook into model instance actions and trigger
the needed additional changes on associated computed fields given by the lookup map.
The signal handlers itself call into ``update_dependent``, which creates querysets for all needed
computed fields updates. A computed field finally gets updated in the database by calling the instance's save method,
which itself calls the method associated with the computed field name and places the result in the database.
Currently this is done on individual instance basis (room for improvement). If a computed field depends on other
computed fields the process repeats until all computed fields have been updated.

.. NOTE::

    The computed field updates are guarded by transactions and get triggered by post signal handlers.
    The database values of computed fields are always in sync between two database relevant
    model instance actions in Python, unless a transaction error occured.


Advanced Usage
--------------

The runtime model described above does not work with bulk actions.
:mod:`django-computedfields` still can be used in combination with bulk actions,
but you have to trigger the needed updates yourself by calling ``update_dependent``, example:

    >>> from computedfields.models import update_dependent
    >>> Entry.objects.filter(pub_date__year=2010).update(comments_on=False)
    >>> update_dependent(Entry.objects.filter(pub_date__year=2010))

Special care is needed, if the bulk changes involve foreign key fields itself,
that are part of a dependency chain. Here related computed model instances have to be collected
before doing the bulk change to correctly update the old relations as well after the action took place:

    >>> # given: some computed fields model depends somehow on Entry.fk_field
    >>> from computedfields.models import update_dependent, preupdate_dependent
    >>> dirty = preupdate_dependent(Entry.objects.filter(pub_date__year=2010))
    >>> Entry.objects.filter(pub_date__year=2010).update(fk_field=new_related_obj)
    >>> update_dependent(Entry.objects.filter(pub_date__year=2010), dirty=dirty)

.. NOTE::

    The dirty handling triples the needed database interactions and should not be used,
    if the bulk action does not involve any relation updates at all. It can also be skipped,
    if the foreign key fields to be updated are not part of any computed fields dependency chain.
    Since this is sometimes hard to spot, :mod:`django-computedfields` provides a convenient listing
    of vulnerable foreign key fields accessible by .......TODO: cmdline access, admin view........


For multiple bulk actions consider using ``update_dependent_multi`` in conjunction with
``preupdate_dependent_multi``, which will avoid unnecessary multiplied updates across the database tables.

See method description in the API Reference for further details.


Management Commands
-------------------

- ``createmap``
    recreates the pickled resolver map. Set the file path with ``COMPUTEDFIELDS_MAP``
    in settings.py.

- ``rendergraph <filename>``
    renders the dependency graph to <filename>.

- ``updatedata``
    does a full update on all computed fields in the project. Only useful after
    tons of bulk changes, e.g. from fixtures.


General Usage Notes
-------------------

:mod:`django-computedfields` provides an easy way to denormalize database data with Django in an automated fashion.
As with any denormalization it should only be used as a last resort to optimize certain query bottlenecks for otherwise
highly normalized data.

Best Practices
^^^^^^^^^^^^^^

- always start highly normalized
- cover needed field calculations with field annotations where possible
- do other calculations, that cannot be covered in field annotations, in normal methods/properties

These steps should always be followed, as they guarantee low to no redundancy of the data if properly done,
before resorting to any denormalization trickery. Of course complicated field calculations create
additional workload either on the database or in Python, which might turn into serious query bottlenecks in your project.

That is the point where :mod:`django-computedfields` can help by creating (pre-) computed fields.
It can greatly lower recurring query workload by providing a precalculated value instead of recalculating it everytime.
Please keep in mind, that this comes to a price:

- additional space in database needed
- redundant data (as any denormalization)
- higher project complexity (different model metaclass, signal hooks, ``app.ready`` hook)
- higher insert/update costs, which might create new bottlenecks if carelessly used

If your project suffers from query bottlenecks created by recurring field calculations and
you have ruled out worse negative side effects from the list above,
:mod:`django-computedfields` certainly can help to speed up some parts of your Django project.


Motivation
----------

:mod:`django-computedfields` is highly inspired by odoo's computed fields and the lack of
a similar feature in Django's ORM.
