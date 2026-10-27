"""
Views de segurança — throttle de login e gestão de sessões.
CLAUDE.md: 'Limite de tentativas de login com bloqueio temporário.'
"""

from django.http import JsonResponse


def status_seguranca(request):
    """Endpoint simples para verificação de saúde do módulo de segurança."""
    if not request.user.is_authenticated:
        return JsonResponse({"erro": "Autenticação necessária"}, status=401)
    return JsonResponse({
        "usuario": request.user.username,
        "sessoes_ativas": request.user.sessoes_ativas.count(),
    })