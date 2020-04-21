[![Build Status](https://travis-ci.org/netzkolchose/django-computedfields.svg?branch=master)](https://travis-ci.org/netzkolchose/django-computedfields)
[![Coverage Status](https://coveralls.io/repos/github/netzkolchose/django-computedfields/badge.svg?branch=master)](https://coveralls.io/github/netzkolchose/django-computedfields?branch=master)

### django-computedfields ###

django-computedfields provides autoupdated database fields
for model methods.

Tested with Django 1.11, 2.2 and 3.0 (Python 3.6 to 3.8, also Python 2.7 where possible).


#### Example ####

Just derive your model from `ComputedFieldsModel` and place
the `@computed` decorator at a method:

```python
from django.db import models
from computedfields.models import ComputedFieldsModel, computed

class MyModel(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32))
    def computed_field(self):
        return self.name.upper()
```

`computed_field` will be turned into a real database field
and can be accessed and searched like any other database field.
During saving the associated method gets called and it’s result
written to the database. With the method `compute('fieldname')`
you can inspect the value that will be written, which is useful
if you have pending changes:

```python
>>> person = MyModel(forename='berty')
>>> person.computed_field             # empty since not saved yet
>>> person.compute('computed_field')  # outputs 'BERTY'
>>> person.save()
>>> person.computed_field             # outputs 'BERTY'
```

The `computed` decorator supports a `depends` keyword argument
to indicate dependencies to other model fields. If set, the computed field
gets automatically updated upon changes of the related fields:

```python
from django.db import models
from computedfields.models import ComputedFieldsModel, computed

class MyModel(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    fk = models.ForeignKey(SomeModel)

    @computed(models.CharField(max_length=32), depends=['fk#fieldname'])
    def computed_field(self):
        return self.name.upper() + self.fk.fieldname
```

Now changes to `fk.fieldname` will now also update `computed_field`.


#### Documentation ####

The documentation can be found [here](https://django-computedfields.readthedocs.io/en/latest/index.html).
