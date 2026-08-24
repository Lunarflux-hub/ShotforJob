"""
Django сам по себе НЕ удаляет файл с диска при удалении объекта модели с
ImageField/FileField — только запись из БД. Без этих сигналов удаление
заказа/фото (например, вручную из админки, или каскадом при удалении
пользователя) оставляло бы файл в media/uploads навсегда.
"""

from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver

from .models import Order, UploadedPhoto


@receiver(post_delete, sender=UploadedPhoto)
def delete_uploaded_photo_file(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)


@receiver(pre_delete, sender=Order)
def delete_order_background_image_file(sender, instance, **kwargs):
    if instance.background_image:
        instance.background_image.delete(save=False)
