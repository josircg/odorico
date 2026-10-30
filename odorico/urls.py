
from django.contrib import admin
from django.conf.urls import url, include
from django.contrib.auth import views as auth_views
from django.conf.urls.static import static

from django.conf import settings
from django.urls import path
from django.views.generic import RedirectView

from odorico.forms import EmailValidationOnForgotPassword

# Settings site admin
admin.site.empty_value_display = '-'
admin.site.site_header = 'Odorico'
admin.site.index_title = 'Odorico'
admin.site.site_title = 'Odorico'

urlpatterns = [
                  url(r'^favicon\.ico$', RedirectView.as_view(url='/static/favicon.ico')),
                  url(r'^admin/', admin.site.urls),
                  url(r'^admin_tools/', include('admin_tools.urls')),
                  url(r'^password_reset/$',
                      auth_views.PasswordResetView.as_view(form_class=EmailValidationOnForgotPassword),
                      name='password_reset'),
                  path('select2/', include('django_select2.urls')),
                  path('chaining/', include('smart_selects.urls')),
                  url(r'^', include('nucleo.urls')),
                  url('^', include('django.contrib.auth.urls')),
                  url(r'^', include('utils.urls')),
                  url(r'^', include('qualis.urls')),
                  url(r'^', include('editais.urls')),
              ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if hasattr(settings, 'ESCOLA'):
    urlpatterns += [ url(r'^', include('escola.urls')) ]

# Include django debug toolbar if DEBUG is on
if settings.DEBUG:
    urlpatterns += [
        path("__debug__/", include('debug_toolbar.urls')),
    ]

if settings.SQLEXPLORER:
    urlpatterns += [
        path('explorer/', include('explorer.urls')),
    ]
