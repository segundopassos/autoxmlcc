import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contratos', '0002_itemcontrato_nota_que_esgotou_and_more'),
        ('importacao', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='HistoricoHashArquivo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('PLANILHA', 'Planilha de Itens'), ('NOTA_FISCAL', 'Nota Fiscal (XML/PDF)'), ('MESTRE', 'Planilha Mestre')], max_length=15, verbose_name='Tipo de arquivo')),
                ('nome_arquivo', models.CharField(max_length=255, verbose_name='Nome do arquivo')),
                ('hash_sha256', models.CharField(db_index=True, max_length=64, verbose_name='Hash SHA-256')),
                ('data_upload', models.DateTimeField(auto_now_add=True, verbose_name='Data de upload')),
                ('contrato', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='historico_hashes', to='contratos.contrato', verbose_name='Contrato associado')),
            ],
            options={
                'verbose_name': 'Histórico de Hash de Arquivo',
                'verbose_name_plural': 'Históricos de Hash de Arquivos',
                'ordering': ['-data_upload'],
                'constraints': [models.UniqueConstraint(fields=('hash_sha256', 'tipo', 'contrato'), name='unique_hash_tipo_contrato')],
            },
        ),
    ]
