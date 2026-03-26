from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

PayloadT = TypeVar("PayloadT")


class BaseResponse(BaseModel, Generic[PayloadT]):
    is_success: bool = True
    message: str
    data: PayloadT
