from pydantic import BaseModel


class MetricsRead(BaseModel):
    total_patients: int
    appointments_booked: int
    cancelled_appointments: int
    completed_visits: int
    upcoming_appointments: int
    cancellation_rate: float
    avg_wait_time_seconds: float
