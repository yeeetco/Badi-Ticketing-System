from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str


class TicketCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    customer_email: EmailStr
    order_id: str | None = Field(default=None, max_length=100)
    category: Literal["INSTALLATION", "ACTIVATION", "CONNECTIVITY", "ORDER", "TOPUP", "REFUND", "OTHER"]
    subject: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"] = "MEDIUM"


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    number: str
    customer_email: str
    subject: str
    category: str
    status: str
    priority: str
    assigned_agent_id: int | None
    created_at: datetime
