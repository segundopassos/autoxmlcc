"""
Forms do app ordens — Etapa E5.
Formulários para aditivos, OF antecipada (reserva) e exclusão/edição de nota.
RN06: Reajuste. RN12: Aditivo. RN13: Reserva. RN14: Exclusão/edição.
RN16: Data da OF = primeiro dia útil.
"""
from decimal import Decimal
from django import forms
from .models import Aditivo, ItemAditivo, OrdemFornecimento, Feriado


class AditivoForm(forms.ModelForm):
    """Formulário para lançamento de aditivo contratual."""

    class Meta:
        model = Aditivo
        fields = [
            "contrato",
            "numero",
            "data_assinatura",
            "tipo",
            "novo_fim_vigencia",
            "arquivo_origem",
            "observacoes",
        ]
        widgets = {
            "data_assinatura": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "novo_fim_vigencia": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }


class ItemAditivoForm(forms.Form):
    """Formulário para item de aditivo de quantidade ou valor."""

    item_contrato_id = forms.IntegerField(widget=forms.HiddenInput())
    quantidade_aditivada = forms.DecimalField(
        max_digits=14,
        decimal_places=4,
        required=False,
        label="Qtd. aditivada",
        help_text="Positivo para acréscimo, negativo para decréscimo.",
    )
    novo_valor_unitario = forms.DecimalField(
        max_digits=14,
        decimal_places=4,
        required=False,
        label="Novo valor unitário",
    )


ItemAditivoFormSet = forms.formset_factory(
    ItemAditivoForm, extra=0, can_delete=True, validate_min=False
)


class OrdemFornecimentoForm(forms.ModelForm):
    """
    Formulário para criação/edição de OF.
    RN13: Pode ser criada antes da nota (reserva).
    RN16: Data de assinatura padrão = primeiro dia útil do mês.
    """

    class Meta:
        model = OrdemFornecimento
        fields = ["nota", "data_assinatura", "status"]
        widgets = {
            "data_assinatura": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Define data padrão como primeiro dia útil do mês atual
        if not self.instance.pk and not self.initial.get("data_assinatura"):
            from django.utils import timezone
            from .utils import primeiro_dia_util

            hoje = timezone.now().date()
            self.initial["data_assinatura"] = primeiro_dia_util(
                hoje.year, hoje.month
            )


class ExcluirNotaForm(forms.Form):
    """
    Formulário de confirmação para exclusão de nota.
    RN14: Excluir devolve saldo e exclui OF vinculada.
    """

    confirmacao = forms.BooleanField(
        label="Confirmo que desejo excluir esta nota e devolver o saldo.",
        required=True,
    )