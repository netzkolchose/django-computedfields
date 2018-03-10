User Guide
==========


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

The module respects two optional settings in settings.py:

- ``COMPUTEDFIELDS_MAP``
    Used to set a file path for the pickled resolver map. To create the pickled resolver map
    point this setting to a writeable path and call the management command ``createmap``.
    This should always be used in production mode in multi process environments
    to avoid the expensive map creation on every process launch. If set, the file must
    be recreated after model changes.

- ``COMPUTEDFIELDS_ADMIN``
    Set this to ``True`` to get a listing of ``ComputedFieldsModel`` models with their field
    dependencies in admin. Useful during development.


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
and searched like any other field. During saving the value gets calculated and
written to the database. With the method ``compute('fieldname')`` you can
inspect the value that will be written, which is useful if you have pending
changes:

    >>> person = Person(forename='Leeroy', surname='Jenkins')
    >>> person.combined             # empty since not saved yet
    >>> person.compute('combined')  # outputs 'Jenkins, Leeroy'
    >>> person.save()
    >>> person.combined             # outputs 'Jenkins, Leeroy'
    >>> Person.objects.filter(combined__<some condition>)  # used in a queryset

The ``@computed`` decorator expects a model field as first argument to hold
result of the decorated method.


Automatic Updates
-----------------

The ``@computed`` decorator understands a keyword argument ``depends`` to indicate
dependencies to related model fields. If set, the computed field gets automatically
updated upon changes of the related fields.

The example above extended by a model ``Address``:

.. code-block:: python

    class Address(ComputedFieldsModel):
        person = models.ManyToManyField(Person)
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
and the field name separated by '#'. The field name is mandatory (due to the way
the dependency resolver works) and can either point to another computed field or
any ordinary database field. The relation name part can span serveral models,
simply name the relation in python style with a dot (e.g. ``'a.b.c#field'``).
A relation can be of any of django's relation type (foreign keys, m2m, one2one
and their back relations are supported).

.. CAUTION::

    With the depends strings you can easily end up with recursive updates.
    The dependency resolver tries to detect cycling dependencies and might
    raise a ``CycleNodeException``.


Advanced Usage
--------------

For bulk creation and updates you can trigger the update of dependent computed
fields directly by calling ``update_dependent``:

    >>> from computedfields.models import update_dependent
    >>> Entry.objects.filter(pub_date__year=2010).update(comments_on=False)
    >>> update_dependent(Entry.objects.filter(pub_date__year=2010))

See API Reference for further details.


Management Commands
-------------------

- ``createmap``
    recreates the pickled resolver map. Set the file path with ``COMPUTEDFIELDS_MAP``
    in settings.py.

- ``rendergraph <filename>``
    renders the dependency graph to <filename>.

- ``updatedata``
    updates all computed fields of the project. Useful after tons of bulk changes,
    e.g. from fixtures.
