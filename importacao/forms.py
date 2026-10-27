"""
Formulários do app importacao — Etapa E2.
Upload de planilha e confirmação de mapeamento.
"""
from django import forms
from .models import SessaoImportacao


class UploadPlanilhaForm(forms.Form):
    """Formulário de upload de planilha Excel."""
    arquivo = forms.FileField(
        label="Planilha Excel (.xlsx)",
        help_text="Selecione o arquivo da planilha de contrato.",
        widget=forms.ClearableFileInput(attrs={
            "accept": ".xlsx,.xls",
            "class": "block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-emerald-600 file:text-white hover:file:bg-emerald-700",
        }),
    )
    contrato_id = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(),
    )


class ConfirmarImportacaoForm(forms.Form):
    """Formulário de confirmação após pré-visualização."""
    sessao_id = forms.IntegerField(widget=forms.HiddenInput())
    confirmar = forms.BooleanField(
        required=True,
        label="Confirmo que os dados estão corretos",
    )