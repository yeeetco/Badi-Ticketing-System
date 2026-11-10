"""Administrator-only staff CRUD. Role changes revoke access immediately."""
from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from .models import Agent, AgentSession, Ticket
from .routing import dispatch_waiting, lock_routing, return_to_pool
from .schemas import AgentRead, StaffCreate, StaffUpdate
from .security import CurrentAdmin, Db, password_hasher

router = APIRouter(prefix='/admin')


@router.get('/users', response_model=list[AgentRead])
def users(db: Db, admin: CurrentAdmin):
    return db.scalars(select(Agent).order_by(Agent.name, Agent.id)).all()


def serialize_admin_change(db, admin):
    lock_routing(db)
    current = db.scalar(select(Agent).where(Agent.id == admin.id).execution_options(populate_existing=True))
    if current is None or not current.is_active or current.role != 'ADMIN':
        raise HTTPException(403, 'Administrator access has changed. Sign in again.')


def save(db):
    try:
        db.flush()
        dispatch_waiting(db)
        db.commit()
    except IntegrityError as failure:
        db.rollback()
        raise HTTPException(409, 'An account with that email already exists.') from failure


@router.post('/users', response_model=AgentRead, status_code=201)
def create_user(body: StaffCreate, db: Db, admin: CurrentAdmin):
    serialize_admin_change(db, admin)
    values = body.model_dump(exclude={'password'})
    values['email'] = str(body.email).lower()
    user = Agent(**values, password_hash=password_hasher.hash(body.password))
    db.add(user)
    save(db)
    return user


def user_or_404(db, user_id):
    user = db.get(Agent, user_id)
    if not user:
        raise HTTPException(404, 'Staff account not found.')
    return user


@router.get('/users/{user_id}', response_model=AgentRead)
def read_user(user_id: int, db: Db, admin: CurrentAdmin):
    return user_or_404(db, user_id)


def preserve_admin(db, user, role, active):
    if user.role == 'ADMIN' and user.is_active and (role != 'ADMIN' or not active):
        other = db.scalar(select(Agent.id).where(Agent.role == 'ADMIN', Agent.is_active.is_(True), Agent.id != user.id).limit(1))
        if other is None:
            raise HTTPException(409, 'Keep at least one active administrator.')


@router.put('/users/{user_id}', response_model=AgentRead)
def update_user(user_id: int, body: StaffUpdate, db: Db, admin: CurrentAdmin):
    serialize_admin_change(db, admin)
    user = user_or_404(db, user_id)
    preserve_admin(db, user, body.role, body.is_active)
    values = body.model_dump(exclude={'password'})
    values['email'] = str(body.email).lower()
    security_change = body.password is not None or any(getattr(user, key) != values[key] for key in ('email', 'role', 'area', 'tier', 'is_active'))
    if security_change:
        # Return handles before changing role/area, preserving assignment history.
        return_to_pool(db, user.id, f'Account access changed by {admin.name}.')
        db.execute(delete(AgentSession).where(AgentSession.agent_id == user.id))
        user.availability = 'OFFLINE'
        user.is_available = False
    for field, value in values.items():
        setattr(user, field, value)
    if body.password:
        user.password_hash = password_hasher.hash(body.password)
    save(db)
    return user


@router.delete('/users/{user_id}', status_code=204)
def delete_user(user_id: int, db: Db, admin: CurrentAdmin):
    serialize_admin_change(db, admin)
    user = user_or_404(db, user_id)
    if user.id == admin.id:
        raise HTTPException(409, 'You cannot delete the account you are signed in with.')
    preserve_admin(db, user, None, False)
    return_to_pool(db, user.id, f'Account deleted by {admin.name}.')
    # Keep historical cases/messages/audits; clear only the foreign-key links.
    for ticket in db.scalars(select(Ticket).where(Ticket.assigned_agent_id == user.id)).all():
        ticket.assigned_agent_id = None
    for ticket in db.scalars(select(Ticket).where(Ticket.requeue_agent_id == user.id)).all():
        ticket.requeue_agent_id = None
        ticket.requeue_until = None
    db.flush()
    db.delete(user)
    save(db)
    return Response(status_code=204)
