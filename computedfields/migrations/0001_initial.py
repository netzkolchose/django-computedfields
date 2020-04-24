from django.db import migrations


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='ComputedFieldsAdminModel',
            fields=[
            ],
            options={
                'managed': False,
                'ordering': ('app_label', 'model'),
                'verbose_name_plural': 'Computed Fields Models',
                'proxy': True,
                'verbose_name': 'Computed Fields Model',
            },
            bases=('contenttypes.contenttype',),
        ),
    ]
