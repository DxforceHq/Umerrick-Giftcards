from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views
from giftcards.auth import PermissionAwareLoginView
from . import pwa
urlpatterns=[path('django-admin/',admin.site.urls),
             path('pwa/manifest.json',pwa.manifest,name='pwa_manifest'),
             path('pwa/prices-worker.js',pwa.prices_worker,name='prices_worker'),
             path('pwa/icon-<int:size>.png',pwa.icon,name='pwa_icon'),
             path('accounts/login/',PermissionAwareLoginView.as_view(template_name='registration/login.html'),name='login'),
             path('accounts/logout/',auth_views.LogoutView.as_view(),name='logout'),
             path('',include('giftcards.urls'))]
