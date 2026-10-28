from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notas', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='notafiscal',
            name='hash_sha256',
            field=models.CharField(blank=True, db_index=True, help_text='Usado para bloquear duplicidade de upload (RN25).', max_length=64, null=True, verbose_name='Hash SHA-256 do arquivo de origem'),
        ),
    ]
