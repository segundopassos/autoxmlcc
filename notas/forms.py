"""
Forms do app notas — Etapa E3.
Formulários para lançamento manual de notas fiscais.
RN05: Preço exato. RN10: Totais respeitados. RN11: Bloqueio com justificativa.
"""
from decimal import Decimal

from django import forms

from .models import NotaFiscal, ItemNota


class NotaFiscalManualForm(forms.ModelForm):
    """Formulário para lançamento manual de nota fiscal."""

    class Meta:
        model = NotaFiscal
        fields = [
            "empresa",
            "contrato",
            "numero",
            "serie",
            "data_emissao",
            "valor_total",
            "informacoes_complementares",
        ]
        widgets = {
            "data_emissao": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "valor_total": forms.NumberInput(
                attrs={"step": "0.01", "min": "0"},
            ),
            "informacoes_complementares": forms.Textarea(
                attrs={"rows": 3},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtra contratos apenas da empresa selecionada (se já escolhida)
        if self.data.get("empresa"):
            self.fields["contrato"].queryset = (
                self.fields["contrato"]
                .queryset.filter(empresa_id=self.data["empresa"])
            )


class ItemNotaForm(forms.Form):
    """Formulário para um item individual da nota."""

    codigo_fornecedor = forms.CharField(
        max_length=50, required=False, label="Código fornecedor",
    )
    descricao = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}))
    unidade = forms.CharField(max_length=20, initial="UN")
    quantidade = forms.DecimalField(
        max_digits=14, decimal_places=4, min_value=Decimal("0"),
    )
    valor_unitario = forms.DecimalField(
        max_digits=14, decimal_places=4, min_value=Decimal("0"),
    )
    valor_total = forms.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"),
    )
    item_contrato_id = forms.IntegerField(required=False, widget=forms.HiddenInput())


ItemNotaFormSet = forms.formset_factory(
    ItemNotaForm, extra=1, can_delete=True, validate_min=True, min_num=1,
)


class LiberacaoNotaForm(forms.Form):
    """
    Formulário para liberação de nota bloqueada.
    RN11: Justificativa obrigatória.
    """

    justificativa = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        label="Justificativa de liberação",
        help_text="Explique o motivo da liberação desta nota.",
    )

    def clean_justificativa(self):
        texto = self.cleaned_data.get("justificativa", "").strip()
        if not texto:
            raise forms.ValidationError("A justificativa é obrigatória.")
        return texto