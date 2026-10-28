from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contratos', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemcontrato',
            name='nota_que_esgotou',
            field=models.CharField(blank=True, help_text="Ex: 'PLANILHA INICIAL', 'NF 3432'.", max_length=100, null=True, verbose_name='Nota que esgotou o saldo'),
        ),
        migrations.AddField(
            model_name='itemcontrato',
            name='qnt_aditivada',
            field=models.DecimalField(decimal_places=4, default=Decimal('0'), max_digits=14, verbose_name='Quantidade aditivada'),
        ),
        migrations.AddField(
            model_name='itemcontrato',
            name='qnt_faturada',
            field=models.DecimalField(decimal_places=4, default=Decimal('0'), help_text='Soma de qnt_faturada_base + lançamentos de NF.', max_digits=14, verbose_name='Quantidade faturada total'),
        ),
        migrations.AddField(
            model_name='itemcontrato',
            name='qnt_faturada_base',
            field=models.DecimalField(decimal_places=4, default=Decimal('0'), help_text='Faturado que já veio na planilha inicial de importação.', max_digits=14, verbose_name='Quantidade faturada base (planilha inicial)'),
        ),
        migrations.AddField(
            model_name='itemcontrato',
            name='ultimo_hash_planilha',
            field=models.CharField(blank=True, help_text='Evita duplicar planilha no modo somar.', max_length=64, null=True, verbose_name='Último hash SHA-256 da planilha'),
        ),
    ]
