# Generated by Django 5.2 on 2025-05-08 16:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('meets', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='result',
            name='best_points',
            field=models.FloatField(default=0),
        ),
    ]
