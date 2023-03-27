from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='upload'),
    path('<str:cellname>/readpoints', views.readpoints, name='readpoints'),
    path('<str:cellname>', views.cell, name='cellpage'),
]