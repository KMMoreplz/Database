from pydantic import BaseModel, Field


RATE_MIN = 0
RATE_MAX = 30
DEPOSIT_MIN = 0
DEPOSIT_MAX = 1_000_000
TERM_MIN = 0
TERM_MAX = 600


class BankCreate(BaseModel):
    bank_name: str = Field(min_length=2, max_length=100)
    license_no: str = Field(min_length=1, max_length=15)
    rating: str = Field(min_length=1, max_length=5)


class ProductCreate(BaseModel):
    bank_id: int
    type_id: int
    risk_id: int
    currency_id: int
    client_id: int | None = None
    product_title: str = Field(min_length=2, max_length=150)
    interest_rate: float = Field(ge=RATE_MIN, le=RATE_MAX)
    min_deposit: float = Field(ge=DEPOSIT_MIN, le=DEPOSIT_MAX)
    term_months: int = Field(ge=TERM_MIN, le=TERM_MAX)
    description: str | None = None


class ProductRateUpdate(BaseModel):
    interest_rate: float = Field(ge=RATE_MIN, le=RATE_MAX)
    min_deposit: float = Field(ge=DEPOSIT_MIN, le=DEPOSIT_MAX)
    term_months: int = Field(ge=TERM_MIN, le=TERM_MAX)


class ProductFullUpdate(BaseModel):
    bank_id: int
    type_id: int
    risk_id: int
    currency_id: int
    client_id: int | None = None
    product_title: str = Field(min_length=2, max_length=150)
    interest_rate: float = Field(ge=RATE_MIN, le=RATE_MAX)
    min_deposit: float = Field(ge=DEPOSIT_MIN, le=DEPOSIT_MAX)
    term_months: int = Field(ge=TERM_MIN, le=TERM_MAX)
    description: str | None = None
    is_active: bool
