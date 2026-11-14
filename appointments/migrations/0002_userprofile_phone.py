from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="phone",
            field=models.CharField(blank=True, max_length=24, verbose_name="teléfono de contacto"),
        ),
    ]
