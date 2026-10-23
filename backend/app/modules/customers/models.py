from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, ForeignKey
from app.database import Base

class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint(
            "length(phone_number) = 10 AND phone_number NOT GLOB '*[^0-9]*'",
            name="ck_customer_phone_10_digits",
        )
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable= False)
    phone_number: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now())


