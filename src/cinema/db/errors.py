"""Перевод ошибок СУБД в понятные пользователю сообщения."""

from __future__ import annotations

from sqlalchemy.exc import DBAPIError


class ProcedureError(Exception):
    """Ошибка бизнес-логики, возникающая в процедурах."""


def describe_error(exc: BaseException) -> str:
    if isinstance(exc, ProcedureError):
        return str(exc)
    message = str(exc.orig) if isinstance(exc, DBAPIError) else str(exc)
    if "UNIQUE constraint failed: tickets" in message:
        return "Это место на сеанс уже продано"
    if message.startswith("UNIQUE constraint failed"):
        return f"Запись с таким значением уже существует ({message.split(': ', 1)[1]})"
    if message.startswith("FOREIGN KEY constraint failed"):
        return "Операция нарушает ссылочную целостность: есть связанные записи"
    if message.startswith("CHECK constraint failed"):
        return f"Нарушено ограничение целостности: {message.split(': ', 1)[1]}"
    if message.startswith("NOT NULL constraint failed"):
        return f"Не заполнено обязательное поле: {message.split(': ', 1)[1]}"
    return message
