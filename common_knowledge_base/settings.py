"""
Django settings for common_knowledge_base project.

Generated by 'django-admin startproject' using Django 3.2.18.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.2/ref/settings/
"""

from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure--r(^st^2xy6rn5gnms@kfg^fui^)=odf5%+lqmmwl=znfl-b!&'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'customize_kb'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'common_knowledge_base.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'common_knowledge_base.wsgi.application'


# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/3.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/3.2/topics/i18n/

LANGUAGE_CODE = 'zh-Hans'

TIME_ZONE = 'Asia/Shanghai'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.2/howto/static-files/

STATIC_URL = '/static/'

# Default primary key field type
# https://docs.djangoproject.com/en/3.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000
DATA_UPLOAD_MAX_MEMORY_SIZE = 20971520 
FILE_UPLOAD_MAX_MEMORY_SIZE = 20971520
# Broker配置，使用Redis作为消息中间件
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL")

# BACKEND配置，这里使用redis
CELERY_RESULT_BACKEND = os.getenv("CELERY_BROKER_URL")

# 结果序列化方案
CELERY_RESULT_SERIALIZER = 'json'
# CELERY_RESULT_BACKEND = "django-db"
# celery内容等消息的格式设置，默认json
CELERY_ACCEPT_CONTENT = ['application/json', ]
CELERY_TASK_SERIALIZER = 'json'
CELERY_TASK_TIME_LIMIT = 60 * 30 *10
CELERY_RESULT_EXPIRES = 0
# 任务结果过期时间，秒
CELERY_TASK_RESULT_EXPIRES = 60 * 30 *10

# 时区配置
CELERY_TIMEZONE='Asia/Shanghai'
# 任务限流
CELERY_TASK_ANNOTATIONS = {'tasks.add': {'rate_limit': '10/s'}}

# Worker并发数量，一般默认CPU核数，可以不设置
CELERY_WORKER_CONCURRENCY = 2

# 每个worker执行了多少任务就会死掉，默认是无限的
CELERY_WORKER_MAX_TASKS_PER_CHILD = 800

CELERY_TASK_ACKS_LATE=False

CELERY_WORKER_PREFETCH_MULTIPLIER=1

CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

#导入全局的Embedding模型
from sentence_transformers import SentenceTransformer
MY_GLOBAL_EMBEDDING_MODEL = SentenceTransformer(os.getenv("EMBEDDING_MODEL_PATH"), device=os.getenv('DEVICE'))
if os.getenv("M3E_BASE_EMBEDDING_MODEL_PATH"):
    M3E_BASE_EMBEDDING_MODEL = SentenceTransformer(os.getenv("M3E_BASE_EMBEDDING_MODEL_PATH"), device=os.getenv('DEVICE'))
if os.getenv("E5_LARGE_EMBEDDING_MODEL_PATH"):
    E5_LARGE_EMBEDDING_MODEL = SentenceTransformer(os.getenv("E5_LARGE_EMBEDDING_MODEL_PATH"), device=os.getenv('DEVICE'))
if os.getenv("BGE_M3_EMBEDDING_MODEL_PATH"):
    BGE_M3_EMBEDDING_MODEL = SentenceTransformer(os.getenv("BGE_M3_EMBEDDING_MODEL_PATH"), device=os.getenv('DEVICE'))
    
# 读取全局config文件
import yaml
yaml_file_path = 'common/config.yaml'
with open(yaml_file_path, 'r') as yaml_file:
    data = yaml.safe_load(yaml_file)
EMBEDDING_DB_MAPPING = data.get('embedding_db_mapping', {})
