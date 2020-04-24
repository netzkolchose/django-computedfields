from django.contrib import admin
from .models import Foo, Bar, Baz


class FooAdmin(admin.ModelAdmin):
    list_display = ('name', 'bazzes')


class BarAdmin(admin.ModelAdmin):
    list_display = ('name', 'foo_bar')


class BazAdmin(admin.ModelAdmin):
    list_display = ('name', 'foo_bar_baz')


admin.site.register(Foo, FooAdmin)
admin.site.register(Bar, BarAdmin)
admin.site.register(Baz, BazAdmin)
