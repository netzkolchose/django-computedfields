__version__ = '0.1.7'

import django

if django.VERSION < (3, 2):
    default_app_config = 'computedfields.apps.ComputedfieldsConfig'
