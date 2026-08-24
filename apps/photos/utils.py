import uuid

ANON_ID_COOKIE = "photostudio_anon_id"
ANON_ID_MAX_AGE = 60 * 60 * 24 * 90  # 90 дней


def get_or_create_anon_id(request) -> tuple[str, bool]:
    """
    Возвращает анонимный идентификатор пользователя из cookie.
    Второе значение — нужно ли выставить cookie в ответе (True, если создан новый).
    Так незарегистрированный пользователь может сгенерировать фото и увидеть
    результат, а при последующей регистрации историю можно "приклеить" к юзеру.
    """
    anon_id = request.COOKIES.get(ANON_ID_COOKIE)
    if anon_id:
        return anon_id, False
    return str(uuid.uuid4()), True
