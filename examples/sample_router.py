"""Sample FastAPI router for testing faex."""

from fastapi import APIRouter

router = APIRouter()


# Custom exceptions
class UnauthorizedException(Exception):
    pass


class ForbiddenException(Exception):
    pass


class NotFoundException(Exception):
    pass


class PaymentFailedException(Exception):
    pass


# Helper function that raises an exception
def check_permission(user_id: int) -> None:
    if user_id < 0:
        raise ForbiddenException()


def get_user_data(user_id: int) -> dict:
    if user_id == 0:
        raise NotFoundException()
    return {"id": user_id, "name": "Test User"}


# Endpoint with properly declared exceptions
@router.get(
    "/users/{user_id}",
    exceptions=[UnauthorizedException, NotFoundException],
)
async def get_user(user_id: int):
    if user_id < 0:
        raise UnauthorizedException()
    return get_user_data(user_id)


# Endpoint with missing exception declaration
@router.post(
    "/users/{user_id}/action",
    exceptions=[UnauthorizedException],  # Missing ForbiddenException!
)
async def perform_action(user_id: int):
    if user_id < 0:
        raise UnauthorizedException()
    check_permission(user_id)  # This raises ForbiddenException
    return {"status": "ok"}


# Endpoint with no exceptions declared but raises them
@router.delete("/users/{user_id}")
async def delete_user(user_id: int):
    if user_id < 0:
        raise UnauthorizedException()
    if user_id == 0:
        raise ForbiddenException()
    return {"deleted": True}


# Endpoint with no exceptions
@router.get("/health")
async def health_check():
    return {"status": "healthy"}
