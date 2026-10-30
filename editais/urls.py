from django.urls import path, re_path

from . import views

urlpatterns = [
    path('nova_inscricao_edital/<int:id_edital>/', views.nova_inscricao_edital, name='nova_inscricao_edital'),
    path('inscricao_edital/<int:id_inscricao>/<str:hash>/', views.inscricao_edital, name='inscricao_edital'),
    path('edital_lattes/<int:id_inscricao>/', views.edital_lattes, name='edital_lattes'),
]
