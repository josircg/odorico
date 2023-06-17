"""odorico URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf.urls import url, include
from django.contrib.auth import views as auth_views
from django.conf.urls.static import static

from django.conf import settings
from django.urls import path

from odorico.forms import EmailValidationOnForgotPassword

# Settings site admin
admin.site.empty_value_display = '-'
admin.site.site_header = 'Odorico'
admin.site.index_title = 'Odorico'
admin.site.site_title = 'Odorico'

urlpatterns = [
                  url(r'^admin/', admin.site.urls),
                  url(r'^admin_tools/', include('admin_tools.urls')),
                  url(r'^password_reset/$',
                      auth_views.PasswordResetView.as_view(form_class=EmailValidationOnForgotPassword),
                      name='password_reset'),
                  path('select2/', include('django_select2.urls')),
                  path('chaining/', include('smart_selects.urls')),
                  url('^', include('django.contrib.auth.urls')),
                  url(r'^', include('nucleo.urls')),
                  url(r'^', include('qualis.urls')),
              ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
