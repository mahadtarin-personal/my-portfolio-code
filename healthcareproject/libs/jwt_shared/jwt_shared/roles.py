from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    """The four roles from the PRD (§3.1). Shared across services since
    RBAC decisions happen both in Profiles (who can register what) and in
    Booking (who can act on which appointment) without either service
    owning the other's data."""

    PATIENT = "patient"
    PROVIDER = "provider"
    FRONT_DESK = "front_desk"
    ADMIN = "admin"
