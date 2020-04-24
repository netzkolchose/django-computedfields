from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('computedfields', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContributingModelsModel',
            fields=[
            ],
            options={
                'verbose_name': 'Model with contributing Fk Fields',
                'verbose_name_plural': 'Models with contributing Fk Fields',
                'ordering': ('app_label', 'model'),
                'managed': False,
                'proxy': True,
            },
            bases=('contenttypes.contenttype',),
        ),
    ]
