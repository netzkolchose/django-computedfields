from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Bar',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=32)),
                ('foo_bar', models.CharField(editable=False, max_length=32)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Baz',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=32)),
                ('foo_bar_baz', models.CharField(editable=False, max_length=32)),
                ('bar', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='exampleapp.Bar')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Foo',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=32)),
                ('bazzes', models.CharField(editable=False, max_length=32)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='bar',
            name='foo',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='exampleapp.Foo'),
        ),
    ]
