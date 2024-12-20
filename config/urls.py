from django.contrib import admin
from django.urls import path

from bdr_deposits_uploader_app import views

urlpatterns = [
    ## main ---------------------------------------------------------
    path('info/', views.info, name='info_url'),
    path('pre_login/', views.pre_login, name='pre_login_url'),
    path('login/', views.login, name='login_url'),
    path('logout/', views.logout, name='logout_url'),
    path('config/new/', views.config_new, name='config_new_url'),
    path('config/<str:slug>/', views.config_slug, name='config_slug_url'),
    path('upload/<str:slug>/', views.upload_slug, name='upload_slug_url'),
    ## htmx helpers -------------------------------------------------
    path('hlpr_generate_slug/', views.hlpr_generate_slug, name='hlpr_generate_slug_url'),
    path('hlpr_check_name_and_slug/', views.hlpr_check_name_and_slug, name='hlpr_check_name_and_slug_url'),
    ## other --------------------------------------------------------
    path('', views.root, name='root_url'),
    path('admin/', admin.site.urls),
    path('error_check/', views.error_check, name='error_check_url'),
    path('version/', views.version, name='version_url'),
]
