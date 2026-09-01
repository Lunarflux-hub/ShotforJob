from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


def _unique_username(base: str) -> str:
    """Тот же приём, что и в apps.social_auth.views — модель User не имеет
    отдельного поля-логина, поэтому username генерируем из email и просто
    гарантируем уникальность."""
    username = base or "user"
    suffix = 1
    while User.objects.filter(username=username).exists():
        suffix += 1
        username = f"{base}{suffix}"
    return username


class RegisterSerializer(serializers.ModelSerializer):
    """
    Регистрация по email+паролю (ТЕСТОВЫЙ вход для интеграции с платёжкой).
    Почта выступает логином: username генерируется автоматически и на
    фронте нигде не используется.
    """

    password = serializers.CharField(write_only=True, validators=[validate_password])
    email = serializers.EmailField()

    class Meta:
        model = User
        fields = ["id", "email", "password"]

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Пользователь с таким email уже зарегистрирован.")
        return value

    def create(self, validated_data):
        email = validated_data["email"]
        return User.objects.create_user(
            username=_unique_username(email.split("@")[0]),
            email=email,
            password=validated_data["password"],
        )


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Логин по email+паролю вместо username+пароль (simplejwt по умолчанию
    требует USERNAME_FIELD, у нас это username — здесь просто находим
    пользователя по email и дальше используем стандартную проверку пароля).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Родитель уже создал self.fields["username"] (это self.username_field,
        # у нашей User-модели он равен "username") — прячем его и просим email.
        # username_field намеренно НЕ трогаем: authenticate() ниже ждёт кварг
        # "username", а не "email", у стандартного ModelBackend.
        self.fields.pop(self.username_field, None)
        self.fields["email"] = serializers.EmailField()

    def validate(self, attrs):
        email = attrs.pop("email", "").strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            raise serializers.ValidationError(
                {"detail": "Неверный email или пароль."}, code="authorization"
            )
        # Подставляем реальный username и отдаём родительской реализации —
        # она сама вызовет authenticate() и проверит пароль/is_active.
        attrs[self.username_field] = user.get_username()
        return super().validate(attrs)
