# Generated by Django 2.2.12 on 2020-05-01 23:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exampleapp', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SelfRef',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=32)),
                ('c1', models.CharField(editable=False, max_length=32)),
                ('c2', models.CharField(editable=False, max_length=32)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
