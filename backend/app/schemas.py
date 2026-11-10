from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Status = Literal['OPEN', 'IN_PROGRESS', 'WAITING_FOR_CUSTOMER', 'WAITING_FOR_PROVIDER', 'RESOLVED', 'CLOSED']
Priority = Literal['LOW', 'MEDIUM', 'HIGH', 'URGENT']
Category = Literal['INSTALLATION', 'ACTIVATION', 'CONNECTIVITY', 'ORDER', 'TOPUP', 'REFUND', 'OTHER']


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    tier: str
    is_available: bool
    max_active_chats: int


class AvailabilityUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    is_available: bool
    max_active_chats: int = Field(ge=1, le=20)


class CustomerIntake(BaseModel):
    # Status, priority, subject, and assignee are deliberately not accepted.
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    customer_email: EmailStr
    category: Category
    description: str = Field(min_length=5, max_length=10000)
    order_id: str | None = Field(default=None, max_length=100)


class SummaryRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    category: Category
    description: str = Field(min_length=5, max_length=10000)


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
    updated_at: datetime
    order_id: str | None


class MessageCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    body: str = Field(min_length=1, max_length=10000)
    kind: Literal['PUBLIC', 'INTERNAL'] = 'PUBLIC'


class CustomerMessageCreate(BaseModel):
    # Customers cannot choose INTERNAL or impersonate a sender.
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    body: str = Field(min_length=1, max_length=10000)


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sender_role: str
    sender_name: str
    kind: str
    body: str
    created_at: datetime


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor: str
    field: str
    old_value: str | None
    new_value: str | None
    created_at: datetime


class TicketDetail(TicketRead):
    description: str
    messages: list[MessageRead]
    events: list[EventRead]


class CustomerTicket(BaseModel):
    # Deliberate allowlist: no audit history, assignee, private notes, or hashes.
    model_config = ConfigDict(from_attributes=True)
    id: int
    number: str
    subject: str
    category: str
    priority: str
    status: str
    created_at: datetime
    messages: list[MessageRead]
    customer_email: str
    order_id: str | None
    routing_state: Literal['WAITING', 'ASSIGNED', 'COMPLETE']
    queue_position: int | None
    assigned_agent_name: str | None


class CustomerCreated(BaseModel):
    ticket: CustomerTicket
    access_code: str


class AgentCreated(TicketRead):
    access_code: str


class CustomerAccess(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    ticket_number: str = Field(pattern=r'^BD-[0-9]+$', max_length=30)
    access_code: str = Field(min_length=20, max_length=100)


class TicketPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Status | None = None
    priority: Priority | None = None
    assigned_agent_id: int | None = Field(default=None, gt=0)
