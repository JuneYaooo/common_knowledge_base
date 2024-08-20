# django
from django.urls import path, include
# rest_framework
from rest_framework.routers import DefaultRouter
# function
from customize_kb import views

router = DefaultRouter()

urlpatterns = [
    # 将router.urls添加到urlpatterns中
    path('', include(router.urls)),
    path('recreate_kb/', views.CustomizeKBView.as_view({'post': 'recreate_kb'}), name='recreate_kb'),
    path('delete_kb/', views.CustomizeKBView.as_view({'post': 'delete_kb'}), name='delete_kb'),
    path('import_kb/', views.CustomizeKBView.as_view({'post': 'import_kb'}), name='import_kb'),
    path('check_task_status/', views.CustomizeKBView.as_view({'get': 'check_task_status'}), name='check_task_status'),
    path('get_vector_search/', views.CustomizeKBView.as_view({'post': 'get_vector_search'}), name='get_vector_search'),
    path('get_merged_vector_search/', views.CustomizeKBView.as_view({'post': 'get_merged_vector_search'}), name='get_merged_vector_search')
]