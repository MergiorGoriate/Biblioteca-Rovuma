from django.contrib.auth import views as auth
from django.urls import path
from django.views.generic import TemplateView

from accounts import views as account
from audit.views import events
from catalog import views as catalog
from documents import views as document
from reading import views as reading


urlpatterns = [
    path("", catalog.home, name="home"),
    path("entrar/", account.LocalLogin.as_view(), name="login"),
    path("sair/", account.sign_out, name="logout"),
    path("conta/activar/<str:token>/", account.activate, name="activate"),
    path("conta/recuperar/", account.LocalReset.as_view(), name="password_reset"),
    path("conta/recuperar/enviado/", auth.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("conta/recuperar/<uidb64>/<token>/", auth.PasswordResetConfirmView.as_view(token_generator=account.ResetToken()), name="password_reset_confirm"),
    path("conta/recuperar/concluido/", auth.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("conta/senha/", account.LocalChange.as_view(), name="password_change"),
    path("conta/senha/guardada/", auth.PasswordChangeDoneView.as_view(), name="password_change_done"),
    path("perfil/", account.profile, name="profile"),
    path("catalogo/", catalog.catalogue, name="catalogue"),
    path("obra/<int:pk>/", catalog.detail, name="work"),
    path("obra/<int:pk>/capa/", catalog.cover, name="cover"),
    path("leituras/", catalog.library, name="library"),
    path("ler/<uuid:pk>/", reading.reader, name="reader"),
    path("ler/<uuid:pk>/progresso/", reading.update, name="reading_update"),
    path("documento/<uuid:pk>/pdf/", document.pdf, name="pdf"),
    path("documento/<uuid:pk>/descarregar/", document.download, name="download"),
    path("gestao/obras/", catalog.collection, name="collection"),
    path("gestao/obras/nova/", catalog.edit_work, name="new_work"),
    path("gestao/obras/<int:pk>/", catalog.manage_work, name="manage_work"),
    path("gestao/obras/<int:pk>/editar/", catalog.edit_work, name="edit_work"),
    path("gestao/obras/<int:pk>/estado/", catalog.work_state, name="work_state"),
    path("gestao/localizacoes/", catalog.locations, name="locations"),
    path("gestao/registo/<slug:kind>/", catalog.edit_related, name="new_location"),
    path("gestao/registo/<slug:kind>/editar/<int:pk>/", catalog.edit_related, name="edit_location"),
    path("gestao/registo/<slug:kind>/<int:parent>/", catalog.edit_related, name="new_related"),
    path("gestao/registo/<slug:kind>/<int:parent>/<int:pk>/", catalog.edit_related, name="edit_related"),
    path("gestao/carregar/<int:pk>/", document.upload_page, name="upload"),
    path("gestao/carregar/<int:pk>/iniciar/", document.start_upload, name="start_upload"),
    path("gestao/partes/<uuid:upload_id>/", document.chunks, name="upload_chunks"),
    path("gestao/documento/<uuid:pk>/", document.editorial, name="editorial"),
    path("gestao/estudantes/", account.students, name="students"),
    path("gestao/estudantes/<int:pk>/", account.credential, name="credential"),
    path("gestao/estudantes/<int:pk>/corrigir/", account.correct, name="correct"),
    path("gestao/importar/", account.imports, name="imports"),
    path("gestao/importar/<int:pk>/", account.import_preview, name="import_preview"),
    path("gestao/auditoria/", events, name="audit"),
]
