# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin
from exampleapp.models import Test, Foo, Bar


class TestAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'pansen'
    )


admin.site.register(Test, TestAdmin)


class FooAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'drilldown'
    )


admin.site.register(Foo, FooAdmin)


class BarAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'klaus'
    )


admin.site.register(Bar, BarAdmin)