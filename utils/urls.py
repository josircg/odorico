from django.conf.urls import url
from django.urls import path

from .views import *

urlpatterns = [
    path('system_update/', system_update, name='system_update' ),
    path('deploy-tema/', execute_deploy_tema, name='execute_deploy_tema'),
]
