import os
import django
from celery import Celery
from django.conf import settings


# 设置系统环境变量，安装django，必须设置，否则在启动celery时会报错
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'common_knowledge_base.settings')
django.setup()

app = Celery('common_knowledge_base')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# 一个测试任务
@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')