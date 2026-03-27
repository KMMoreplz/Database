from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    DateTime,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Bank(Base):
    __tablename__ = "banks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bank_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    license_no: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    rating: Mapped[str] = mapped_column(String(5), nullable=False)

    products = relationship("Product", back_populates="bank")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    passport: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    products = relationship("Product", back_populates="client")


class ProductType(Base):
    __tablename__ = "product_types"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    type_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    products = relationship("Product", back_populates="product_type")


class RiskLevel(Base):
    __tablename__ = "risk_level"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    category: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    products = relationship("Product", back_populates="risk")


class Currency(Base):
    __tablename__ = "tbl_currencies"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    currency_code: Mapped[str] = mapped_column(String(3), unique=True, nullable=False)

    products = relationship("Product", back_populates="currency")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("interest_rate >= 0 AND interest_rate <= 30", name="ck_rate_range"),
        CheckConstraint("min_deposit >= 0 AND min_deposit <= 1000000", name="ck_min_deposit_range"),
        CheckConstraint("term_months >= 0 AND term_months <= 600", name="ck_term_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bank_id: Mapped[int] = mapped_column(ForeignKey("banks.id"), nullable=False)
    type_id: Mapped[int] = mapped_column(ForeignKey("product_types.id"), nullable=False)
    risk_id: Mapped[int] = mapped_column(ForeignKey("risk_level.id"), nullable=False)
    currency_id: Mapped[int] = mapped_column(ForeignKey("tbl_currencies.id"), nullable=False)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    product_title: Mapped[str] = mapped_column(String(150), nullable=False)
    interest_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    min_deposit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bank = relationship("Bank", back_populates="products")
    product_type = relationship("ProductType", back_populates="products")
    risk = relationship("RiskLevel", back_populates="products")
    currency = relationship("Currency", back_populates="products")
    client = relationship("Client", back_populates="products")
