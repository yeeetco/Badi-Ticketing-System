from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator, field_validator

Status = Literal['OPEN', 'IN_PROGRESS', 'WAITING_FOR_CUSTOMER', 'WAITING_FOR_PROVIDER', 'RESOLVED', 'CLOSED']
Priority = Literal['LOW', 'MEDIUM', 'HIGH', 'URGENT']
Category = Literal['INSTALLATION', 'ACTIVATION', 'CONNECTIVITY', 'ORDER', 'TOPUP', 'REFUND', 'OTHER']


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class TransferRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    agent_id: int = Field(gt=0)


class ReturnToQueueRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    tier: str
    is_available: bool
    max_active_chats: int
    role: Literal['AGENT', 'TEAM_LEAD', 'ADMIN']
    area: str
    availability: Literal['ONLINE', 'BREAK', 'OFFLINE']
    is_active: bool


class StaffCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    role: Literal['AGENT', 'TEAM_LEAD', 'ADMIN'] = 'AGENT'
    area: str = Field(default='BADI_SUPPORT', min_length=1, max_length=80, pattern=r'^[A-Z0-9_]+$')
    tier: Literal['T1', 'T2'] = 'T1'
    max_active_chats: int = Field(default=5, ge=1, le=20)
    is_active: bool = True

    @field_validator('name')
    @classmethod
    def reserve_system_name(cls, value):
        if value.casefold() == 'system update':
            raise ValueError('Choose a staff name that does not impersonate system activity.')
        return value


class StaffUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    role: Literal['AGENT', 'TEAM_LEAD', 'ADMIN']
    area: str = Field(min_length=1, max_length=80, pattern=r'^[A-Z0-9_]+$')
    tier: Literal['T1', 'T2']
    max_active_chats: int = Field(ge=1, le=20)
    is_active: bool
    password: str | None = Field(default=None, min_length=12, max_length=256)

    @field_validator('name')
    @classmethod
    def reserve_system_name(cls, value):
        if value.casefold() == 'system update':
            raise ValueError('Choose a staff name that does not impersonate system activity.')
        return value


class AvailabilityUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    is_available: bool | None = None
    availability: Literal['ONLINE', 'BREAK', 'OFFLINE'] | None = None
    max_active_chats: int | None = Field(default=None, ge=1, le=20)

    @model_validator(mode='after')
    def validate_state(self):
        if self.is_available is None and self.availability is None and self.max_active_chats is None:
            raise ValueError('Choose a status or capacity to update.')
        if self.is_available is not None and self.availability is not None:
            if self.is_available != (self.availability == 'ONLINE'):
                raise ValueError('Availability fields disagree.')
        return self


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
    area: str
    emergency_closed: bool
    unread_count: int = 0
    awaiting_reply_since: datetime | None = None


class MessageCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    body: str = Field(min_length=1, max_length=10000)
    kind: Literal['PUBLIC', 'INTERNAL'] = 'PUBLIC'


class CustomerMessageCreate(BaseModel):
    # Customers cannot choose INTERNAL or impersonate a sender.
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    body: str = Field(min_length=1, max_length=10000)


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    content_type: str
    size: int
    available: bool = True


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sender_role: str
    sender_name: str
    kind: str
    body: str
    created_at: datetime
    attachments: list[AttachmentRead] = Field(default_factory=list)
    seen_at: datetime | None = None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor: str
    field: str
    old_value: str | None
    new_value: str | None
    created_at: datetime
    reason: str | None


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
    customer_ended_at: datetime | None
    agent_is_typing: bool = False


class ReadReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message_id: int = Field(gt=0)


class TypingUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    is_typing: bool
    visibility: Literal['PUBLIC', 'INTERNAL'] = 'PUBLIC'


class CustomerCreated(BaseModel):
    ticket: CustomerTicket
    access_code: str


class AgentCreated(TicketRead):
    access_code: str


class CustomerAccess(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    ticket_number: str | None = Field(default=None, pattern=r'^BD-[0-9]+$', max_length=30)
    access_code: str = Field(min_length=20, max_length=100)


class TicketPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Status | None = None
    priority: Priority | None = None
    assigned_agent_id: int | None = Field(default=None, gt=0)


class EmergencyClose(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    reason: str = Field(min_length=10, max_length=1000)
