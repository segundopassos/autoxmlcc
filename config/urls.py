from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("api/", include("api.urls")),
    path("", include("contratos.urls")),
    path("importacao/", include("importacao.urls")),
    path("notas/", include("notas.urls")),
    path("ordens/", include("ordens.urls")),
    path("relatorios/", include("relatorios.urls")),
    path("seguranca/", include("seguranca.urls")),
    path("admin/", admin.site.urls),
]