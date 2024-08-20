from django.db import models


class BaseModelFunc:
    @classmethod
    def filter(cls, **kwargs):
        return cls.objects.filter(**kwargs)

    @classmethod
    def get(cls, **kwargs):
        return cls.objects.get(**kwargs)

    @classmethod
    def create(cls, **kwargs):
        return cls.objects.create(**kwargs)


class BaseModel(models.Model, BaseModelFunc):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    is_deleted = models.BooleanField(default=False, verbose_name="是否删除")

    class Meta:
        abstract = True
        verbose_name_plural = "公共字段表"
        db_table = "BaseTable"
