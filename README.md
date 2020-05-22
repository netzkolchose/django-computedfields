[![Build Status](https://travis-ci.org/netzkolchose/django-computedfields.svg?branch=master)](https://travis-ci.org/netzkolchose/django-computedfields)
[![Coverage Status](https://coveralls.io/repos/github/netzkolchose/django-computedfields/badge.svg?branch=master)](https://coveralls.io/github/netzkolchose/django-computedfields?branch=master)

### django-computedfields ###

django-computedfields provides autoupdated database fields
for model methods.

Tested with Django 2.2 and 3.0 (Python 3.6 to 3.8).


#### Example ####

Just derive your model from `ComputedFieldsModel` and place
the `@computed` decorator at a method:

```python
from django.db import models
from computedfields.models import ComputedFieldsModel, computed

class MyModel(ComputedFieldsModel):
    name = models.CharField(max_length=32)

    @computed(models.CharField(max_length=32), depends=[['self', ['name']]])
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

The  `depends` keyword argument can be used with any relation to indicate dependencies to fields on other models as well:

```python
from django.db import models
from computedfields.models import ComputedFieldsModel, computed

class MyModel(ComputedFieldsModel):
    name = models.CharField(max_length=32)
    fk = models.ForeignKey(SomeModel)

    @computed(models.CharField(max_length=32), depends=[['self', ['name']], ['fk', ['fieldname']]])
    def computed_field(self):
        return self.name.upper() + self.fk.fieldname
```

Now changes to `self.name` or `fk.fieldname` will update `computed_field`.

**NOTE:** The old depends syntax is deprecated and should be replaced with the new syntax.
It also should contain a `self` entry with local fields to get reliable updates from local field changes.
This is especially true for advanced usage with `save(update_fields=[...])` or bulk actions.
The old syntax will be removed with a future version.


#### Documentation ####

The documentation can be found [here](https://django-computedfields.readthedocs.io/en/latest/index.html).
