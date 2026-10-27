"""
Formulários do app contratos — Etapa E1.
"""
from django import forms
from .models import Empresa, Contrato


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = ["cnpj", "razao_social"]
        widgets = {
            "cnpj": forms.TextInput(attrs={
                "placeholder": "00.000.000/0000-00",
                "maxlength": 18,
            }),
            "razao_social": forms.TextInput(attrs={
                "placeholder": "Razão social da empresa",
            }),
        }


class ContratoForm(forms.ModelForm):
    class Meta:
        model = Contrato
        fields = [
            "numero", "pregao", "empresa",
            "inicio_vigencia", "fim_vigencia",
            "fiscal", "solicitante", "ordenador",
        ]
        widgets = {
            "numero": forms.TextInput(attrs={
                "placeholder": "Ex: 07.2909/2025",
            }),
            "pregao": forms.TextInput(attrs={
                "placeholder": "Ex: PE 024/2025",
            }),
            "inicio_vigencia": forms.DateInput(attrs={
                "type": "date",
            }),
            "fim_vigencia": forms.DateInput(attrs={
                "type": "date",
            }),
        }