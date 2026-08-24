from rest_framework import serializers


class GoogleLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField(help_text="Google ID token (credential) с фронтенда")


class YandexLoginSerializer(serializers.Serializer):
    access_token = serializers.CharField(help_text="OAuth access_token от Yandex ID")
