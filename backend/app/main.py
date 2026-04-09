import os
import re
from datetime import datetime
from urllib.parse import quote_plus
from decimal import Decimal
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import get_db
from .models import Bank, Currency, Product, ProductType, RiskLevel
from .schemas import BankCreate, ProductCreate, ProductFullUpdate, ProductRateUpdate

SITE_TITLE = "Обозреватель банковских продуктов"
FOOTER_DB_NAME = "БД Банковские продукты"
FOOTER_SITE_DESC = "Информационная площадка аналитики банковских продуктов"
STATIC_ASSET_VERSION = "2026-04-09-03"

DB_BACKEND_CODE = os.getenv("DB_DIALECT", "postgresql").strip().lower()
DB_BACKEND_LABEL = "MySQL" if DB_BACKEND_CODE in {"mysql", "mariadb"} else "PostgreSQL"
DB_SWITCH_ENABLED = os.getenv("DB_SWITCH_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
DB_SWITCH_TARGET_URL = os.getenv("DB_SWITCH_TARGET_URL", "").strip()
DB_SWITCH_TARGET_LABEL = os.getenv("DB_SWITCH_TARGET_LABEL", "Другая версия").strip() or "Другая версия"
DB_SWITCH_TARGET_PORT = os.getenv("DB_SWITCH_TARGET_PORT", "8001" if DB_BACKEND_CODE in {"mysql", "mariadb"} else "8000").strip()
DB_SWITCH_READY = DB_SWITCH_ENABLED

HOME_DB_NAME = "<Информационная система подбора банковских продуктов>"
HOME_DB_AUTHOR = "<Травкин М.Е.  / ИВТ-Б23>"
HOME_DB_DESC = "<Содержит информацию о банках, их продуктах, типах продуктов, уровнях риска и валютах.>"

app = FastAPI(title=SITE_TITLE, version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates.env.globals.update(
    site_title=SITE_TITLE,
    footer_db_name=FOOTER_DB_NAME,
    footer_site_desc=FOOTER_SITE_DESC,
    current_year=datetime.now().year,
    static_asset_version=STATIC_ASSET_VERSION,
    db_backend_code=DB_BACKEND_CODE,
    db_backend_label=DB_BACKEND_LABEL,
    db_switch_enabled=DB_SWITCH_ENABLED,
    db_switch_ready=DB_SWITCH_READY,
    db_switch_target_url=DB_SWITCH_TARGET_URL,
    db_switch_target_label=DB_SWITCH_TARGET_LABEL,
    db_switch_target_port=DB_SWITCH_TARGET_PORT,
)
RATE_MIN = 0.0
RATE_MAX = 30.0
DEPOSIT_MIN = 0.0
DEPOSIT_MAX = 1_000_000.0
TERM_MIN = 0
TERM_MAX = 600
DEFAULT_RATING_CHOICES = [
    "AAA",
    "AA+",
    "AA",
    "AA-",
    "A+",
    "A",
    "A-",
    "BBB+",
    "BBB",
    "BBB-",
    "BB+",
    "BB",
    "BB-",
    "B+",
    "B",
]


def collapse_spaces(value: str) -> str:
    return " ".join((value or "").strip().split())


def normalize_text(value: str) -> str:
    return collapse_spaces(value).lower()


def normalize_title(value: str, field_label: str, min_len: int = 2, max_len: int = 150) -> str:
    normalized = collapse_spaces(value)
    if not (min_len <= len(normalized) <= max_len):
        raise HTTPException(
            status_code=400,
            detail=f"{field_label}: длина должна быть от {min_len} до {max_len} символов",
        )
    return normalized


def normalize_license_number(raw_value: str) -> str:
    value = collapse_spaces(raw_value)
    if value.startswith("№"):
        value = value[1:].strip()
    if not value.isdigit() or not (4 <= len(value) <= 10):
        raise HTTPException(status_code=400, detail="Номер лицензии: только цифры, длина 4..10")
    return f"№{value}"


def normalize_license_key(raw_value: str) -> str:
    value = collapse_spaces(raw_value)
    if value.startswith("№"):
        value = value[1:].strip()
    if not value:
        return ""
    if value.isdigit():
        return value.lstrip("0") or "0"
    return value.lower()

def normalize_currency_code(raw_value: str) -> str:
    code = collapse_spaces(raw_value).upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise HTTPException(
            status_code=400,
            detail="Код валюты: только 3 заглавные латинские буквы (например, USD)",
        )
    return code


def has_duplicate_normalized(values: list[tuple[int, str]], candidate: str, exclude_id: int | None = None) -> bool:
    target = normalize_text(candidate)
    for row_id, row_value in values:
        if exclude_id is not None and int(row_id) == int(exclude_id):
            continue
        if normalize_text(row_value) == target:
            return True
    return False


def normalize_rating(raw_value: str) -> str:
    rating = collapse_spaces(raw_value).upper()
    if rating not in DEFAULT_RATING_CHOICES:
        raise HTTPException(
            status_code=400,
            detail=f"Кредитный рейтинг должен быть одним из: {', '.join(DEFAULT_RATING_CHOICES)}",
        )
    return rating


def validate_product_limits(interest_rate: float, min_deposit: float, term_months: int):
    if not (RATE_MIN <= float(interest_rate) <= RATE_MAX):
        raise HTTPException(
            status_code=400,
            detail=f"Ставка должна быть в диапазоне {RATE_MIN}..{RATE_MAX}",
        )
    if not (DEPOSIT_MIN <= float(min_deposit) <= DEPOSIT_MAX):
        raise HTTPException(
            status_code=400,
            detail=f"Минимальный взнос должен быть в диапазоне {DEPOSIT_MIN}..{DEPOSIT_MAX}",
        )
    if not (TERM_MIN <= int(term_months) <= TERM_MAX):
        raise HTTPException(
            status_code=400,
            detail=f"Срок должен быть в диапазоне {TERM_MIN}..{TERM_MAX}",
        )


def row_to_dict(row) -> dict:
    data = dict(row)
    for key, value in data.items():
        if isinstance(value, Decimal):
            data[key] = float(value)
    return data


def list_products(
    db: Session,
    type_name: str | None = None,
    bank_name: str | None = None,
    currency_code: str | None = None,
):
    stmt = (
        select(
            Product.id.label("id"),
            Product.product_title.label("product_name"),
            ProductType.type_name.label("type_name"),
            Bank.bank_name.label("bank_name"),
            Currency.currency_code.label("currency_code"),
            Product.interest_rate.label("interest_rate"),
            Product.min_deposit.label("min_deposit"),
            Product.term_months.label("term_months"),
        )
        .join(Bank, Product.bank_id == Bank.id)
        .join(ProductType, Product.type_id == ProductType.id)
        .join(Currency, Product.currency_id == Currency.id)
        .where(Product.is_active.is_(True))
    )

    if type_name:
        stmt = stmt.where(ProductType.type_name == type_name)
    if bank_name:
        stmt = stmt.where(Bank.bank_name == bank_name)
    if currency_code:
        stmt = stmt.where(Currency.currency_code == currency_code)

    rows = db.execute(stmt.order_by(Product.id)).mappings().all()
    return [row_to_dict(r) for r in rows]


def list_banks(db: Session, bank_name: str | None = None, rating: str | None = None):
    stmt = select(
        Bank.id.label("id"),
        Bank.bank_name.label("bank_name"),
        Bank.license_no.label("license_no"),
        Bank.rating.label("rating"),
    )
    if bank_name:
        stmt = stmt.where(Bank.bank_name.ilike(f"%{bank_name}%"))
    if rating:
        stmt = stmt.where(Bank.rating == rating)

    rows = db.execute(stmt.order_by(Bank.bank_name)).mappings().all()
    return [row_to_dict(r) for r in rows]


def products_by_bank(db: Session, bank_name: str):
    stmt = (
        select(
            Product.id.label("id"),
            Product.product_title.label("product_name"),
            ProductType.type_name.label("type_name"),
            Product.interest_rate.label("interest_rate"),
            Product.min_deposit.label("min_deposit"),
        )
        .join(Bank, Product.bank_id == Bank.id)
        .join(ProductType, Product.type_id == ProductType.id)
        .where(Product.is_active.is_(True))
        .where(Bank.bank_name.ilike(f"%{bank_name}%"))
        .order_by(Product.id)
    )
    rows = db.execute(stmt).mappings().all()
    return [row_to_dict(r) for r in rows]


def bank_by_product(db: Session, product_name: str):
    stmt = (
        select(
            Bank.id.label("id"),
            Bank.bank_name.label("bank_name"),
            Bank.license_no.label("license_no"),
            Bank.rating.label("rating"),
        )
        .join(Product, Product.bank_id == Bank.id)
        .where(Product.product_title.ilike(f"%{product_name}%"))
        .limit(1)
    )
    row = db.execute(stmt).mappings().first()
    return row_to_dict(row) if row else None


def products_count_by_bank_type(db: Session):
    stmt = text(
        """
        SELECT
            b.bank_name,
            pt.type_name,
            COALESCE(COUNT(p.id), 0) AS count
        FROM banks b
        CROSS JOIN product_types pt
        LEFT JOIN products p
            ON p.bank_id = b.id
           AND p.type_id = pt.id
           AND p.is_active = TRUE
        GROUP BY b.bank_name, pt.type_name
        ORDER BY b.bank_name, pt.type_name
        """
    )
    rows = db.execute(stmt).mappings().all()
    return [row_to_dict(r) for r in rows]


def products_count_in_bank(db: Session, bank_name: str):
    stmt = text(
        """
        SELECT
            b.bank_name,
            COALESCE(COUNT(p.id), 0) AS count
        FROM banks b
        LEFT JOIN products p
            ON p.bank_id = b.id
           AND p.is_active = TRUE
        WHERE b.bank_name LIKE :bank_name
        GROUP BY b.bank_name
        ORDER BY b.bank_name
        """
    )
    rows = db.execute(stmt, {"bank_name": f"%{bank_name}%"}).mappings().all()
    return [row_to_dict(r) for r in rows]


def product_summary(db: Session):
    stmt = text(
        """
        SELECT
            pt.type_name AS product_type,
            (SELECT COUNT(*) FROM product_types) AS type_count,
            COALESCE(ROUND(AVG(p.interest_rate), 2), 0) AS avg_rate,
            COALESCE(ROUND(AVG(p.min_deposit), 2), 0) AS min_deposit_avg,
            COALESCE(COUNT(p.id), 0) AS total_active_products
        FROM product_types pt
        LEFT JOIN products p
            ON p.type_id = pt.id
           AND p.is_active = TRUE
        GROUP BY pt.id, pt.type_name
        ORDER BY pt.type_name
        """
    )
    rows = db.execute(stmt).mappings().all()
    return [row_to_dict(r) for r in rows]


def build_search_options(db: Session):
    # Для фильтров на странице поиска продуктов показываем только реально используемые значения.
    matrix = product_filter_matrix(db)

    type_names = sorted({row["type_name"] for row in matrix if row.get("type_name")})
    bank_names = sorted({row["bank_name"] for row in matrix if row.get("bank_name")})
    currency_codes = sorted({row["currency_code"] for row in matrix if row.get("currency_code")})

    ratings = DEFAULT_RATING_CHOICES
    return {
        "bank_names": bank_names,
        "type_names": type_names,
        "ratings": ratings,
        "currency_codes": currency_codes,
    }

def product_filter_matrix(db: Session):
    stmt = text(
        """
        SELECT DISTINCT
            pt.type_name,
            b.bank_name,
            c.currency_code
        FROM products p
        JOIN product_types pt ON pt.id = p.type_id
        JOIN banks b ON b.id = p.bank_id
        JOIN tbl_currencies c ON c.id = p.currency_id
        WHERE p.is_active = TRUE
        ORDER BY pt.type_name, b.bank_name, c.currency_code
        """
    )
    rows = db.execute(stmt).mappings().all()
    return [row_to_dict(r) for r in rows]


def market_reference(db: Session):
    stmt = text(
        """
        SELECT
            COALESCE(ROUND(AVG(p.interest_rate), 2), 0) AS avg_rate,
            COALESCE(ROUND(AVG(p.min_deposit), 2), 0) AS avg_deposit,
            COALESCE(ROUND(AVG(p.term_months), 2), 0) AS avg_term
        FROM products p
        WHERE p.is_active = TRUE
        """
    )
    row = db.execute(stmt).mappings().first()
    return row_to_dict(row) if row else {"avg_rate": 0, "avg_deposit": 0, "avg_term": 0}


def format_vs_market(value: float, market: float, mode: str) -> str:
    if market == 0:
        return "Нет данных для сравнения"

    ratio = value / market
    if mode == "rate":
        if ratio >= 1.05:
            return "выше рынка"
        if ratio <= 0.95:
            return "ниже рынка"
        return "на уровне рынка"

    if mode == "deposit":
        if ratio <= 0.95:
            return "ниже рынка (вход доступнее)"
        if ratio >= 1.05:
            return "выше рынка (вход дороже)"
        return "на уровне рынка"

    if mode == "term":
        if ratio >= 1.05:
            return "длиннее среднего по рынку"
        if ratio <= 0.95:
            return "короче среднего по рынку"
        return "на уровне рынка"

    return "на уровне рынка"


def bank_cards(db: Session):
    stmt = text(
        """
        SELECT
            b.id,
            b.bank_name,
            COALESCE(COUNT(p.id), 0) AS product_count,
            COALESCE(ROUND(AVG(p.interest_rate), 2), 0) AS avg_rate
        FROM banks b
        LEFT JOIN products p
            ON p.bank_id = b.id
           AND p.is_active = TRUE
        GROUP BY b.id, b.bank_name
        ORDER BY b.bank_name
        """
    )
    rows = db.execute(stmt).mappings().all()
    return [row_to_dict(r) for r in rows]

def bank_comparison_rows(db: Session):
    stmt = text(
        """
        SELECT
            b.id,
            b.bank_name,
            b.license_no,
            b.rating,
            COALESCE(COUNT(p.id), 0) AS total_products,
            COALESCE(ROUND(AVG(p.interest_rate), 2), 0) AS avg_rate,
            COALESCE(ROUND(AVG(p.min_deposit), 2), 0) AS avg_deposit,
            COALESCE(ROUND(AVG(p.term_months), 2), 0) AS avg_term
        FROM banks b
        LEFT JOIN products p
            ON p.bank_id = b.id
           AND p.is_active = TRUE
        GROUP BY b.id, b.bank_name, b.license_no, b.rating
        ORDER BY b.bank_name
        """
    )
    rows = db.execute(stmt).mappings().all()
    return [row_to_dict(r) for r in rows]

def bank_analytics(db: Session, bank_id: int):
    bank_row = db.execute(
        text(
            """
            SELECT b.id, b.bank_name, b.license_no, b.rating
            FROM banks b
            WHERE b.id = :bank_id
            """
        ),
        {"bank_id": bank_id},
    ).mappings().first()

    if not bank_row:
        return None

    summary_row = db.execute(
        text(
            """
            SELECT
                COALESCE(COUNT(p.id), 0) AS total_products,
                COALESCE(ROUND(AVG(p.interest_rate), 2), 0) AS avg_rate,
                COALESCE(ROUND(AVG(p.min_deposit), 2), 0) AS avg_deposit,
                COALESCE(ROUND(AVG(p.term_months), 2), 0) AS avg_term
            FROM products p
            WHERE p.bank_id = :bank_id
              AND p.is_active = TRUE
            """
        ),
        {"bank_id": bank_id},
    ).mappings().first()

    by_type_rows = db.execute(
        text(
            """
            SELECT
                pt.type_name,
                COALESCE(COUNT(p.id), 0) AS count
            FROM product_types pt
            LEFT JOIN products p
                ON p.type_id = pt.id
               AND p.bank_id = :bank_id
               AND p.is_active = TRUE
            GROUP BY pt.id, pt.type_name
            ORDER BY pt.type_name
            """
        ),
        {"bank_id": bank_id},
    ).mappings().all()

    product_rows = db.execute(
        text(
            """
            SELECT
                p.id,
                p.product_title,
                pt.type_name,
                p.interest_rate,
                p.min_deposit,
                p.term_months,
                c.currency_code
            FROM products p
            JOIN product_types pt ON pt.id = p.type_id
            JOIN tbl_currencies c ON c.id = p.currency_id
            WHERE p.bank_id = :bank_id
              AND p.is_active = TRUE
            ORDER BY p.product_title
            """
        ),
        {"bank_id": bank_id},
    ).mappings().all()

    return {
        "bank": row_to_dict(bank_row),
        "summary": row_to_dict(summary_row) if summary_row else None,
        "by_type": [row_to_dict(r) for r in by_type_rows],
        "products": [row_to_dict(r) for r in product_rows],
    }


def overall_type_analytics(db: Session):
    stmt = text(
        """
        SELECT
            pt.type_name,
            COALESCE(COUNT(p.id), 0) AS total_products,
            COALESCE(ROUND(AVG(p.interest_rate), 2), 0) AS avg_rate,
            COALESCE(ROUND(AVG(p.min_deposit), 2), 0) AS avg_min_deposit,
            COALESCE(ROUND(AVG(p.term_months), 2), 0) AS avg_term_months
        FROM product_types pt
        LEFT JOIN products p
            ON p.type_id = pt.id
           AND p.is_active = TRUE
        GROUP BY pt.id, pt.type_name
        ORDER BY pt.type_name
        """
    )
    rows = db.execute(stmt).mappings().all()
    return [row_to_dict(r) for r in rows]


def top_rate_products(db: Session, limit: int = 5):
    stmt = text(
        """
        SELECT
            p.product_title,
            b.bank_name,
            pt.type_name,
            p.interest_rate,
            p.min_deposit,
            p.term_months
        FROM products p
        JOIN banks b ON b.id = p.bank_id
        JOIN product_types pt ON pt.id = p.type_id
        WHERE p.is_active = TRUE
        ORDER BY p.interest_rate DESC, p.min_deposit ASC
        LIMIT :limit_value
        """
    )
    rows = db.execute(stmt, {"limit_value": limit}).mappings().all()
    return [row_to_dict(r) for r in rows]


def currency_distribution(db: Session):
    stmt = text(
        """
        SELECT
            c.currency_code,
            COALESCE(COUNT(p.id), 0) AS products_count
        FROM tbl_currencies c
        LEFT JOIN products p
            ON p.currency_id = c.id
           AND p.is_active = TRUE
        GROUP BY c.id, c.currency_code
        ORDER BY c.currency_code
        """
    )
    rows = db.execute(stmt).mappings().all()
    return [row_to_dict(r) for r in rows]


def create_bank(db: Session, payload: BankCreate):
    bank_name = normalize_title(payload.bank_name, "Название банка", min_len=2, max_len=100)
    license_no = normalize_license_number(payload.license_no)
    rating = normalize_rating(payload.rating)

    existing_names = db.execute(select(Bank.id, Bank.bank_name)).all()
    if has_duplicate_normalized(existing_names, bank_name):
        raise HTTPException(status_code=400, detail="Банк с таким названием уже существует")

    existing_licenses = db.execute(select(Bank.id, Bank.license_no)).all()
    for row_id, row_license in existing_licenses:
        if normalize_license_key(row_license) == normalize_license_key(license_no):
            raise HTTPException(status_code=400, detail="Банк с таким номером лицензии уже существует")

    bank = Bank(bank_name=bank_name, license_no=license_no, rating=rating)
    db.add(bank)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Имеются ошибки ввода") from exc

    db.refresh(bank)
    return {
        "id": bank.id,
        "bank_name": bank.bank_name,
        "license_no": bank.license_no,
        "rating": bank.rating,
    }


def update_bank(db: Session, bank_id: int, payload: BankCreate):
    bank = db.get(Bank, bank_id)
    if not bank:
        raise HTTPException(status_code=404, detail="Банк не найден")

    bank_name = normalize_title(payload.bank_name, "Название банка", min_len=2, max_len=100)
    license_no = normalize_license_number(payload.license_no)
    rating = normalize_rating(payload.rating)

    existing_names = db.execute(select(Bank.id, Bank.bank_name)).all()
    if has_duplicate_normalized(existing_names, bank_name, exclude_id=bank_id):
        raise HTTPException(status_code=400, detail="Банк с таким названием уже существует")

    existing_licenses = db.execute(select(Bank.id, Bank.license_no)).all()
    for row_id, row_license in existing_licenses:
        if int(row_id) == int(bank_id):
            continue
        if normalize_license_key(row_license) == normalize_license_key(license_no):
            raise HTTPException(status_code=400, detail="Банк с таким номером лицензии уже существует")

    bank.bank_name = bank_name
    bank.license_no = license_no
    bank.rating = rating

    db.add(bank)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Имеются ошибки ввода") from exc

    db.refresh(bank)
    return {
        "id": bank.id,
        "bank_name": bank.bank_name,
        "license_no": bank.license_no,
        "rating": bank.rating,
    }


def delete_bank(db: Session, bank_id: int):
    bank = db.get(Bank, bank_id)
    if not bank:
        raise HTTPException(status_code=404, detail="Банк не найден")

    linked_products = (
        db.execute(select(func.count()).select_from(Product).where(Product.bank_id == bank_id))
        .scalar_one()
    )
    if int(linked_products or 0) > 0:
        raise HTTPException(status_code=400, detail="Нельзя удалить банк: есть связанные продукты")

    db.delete(bank)
    db.commit()
    return {"status": "deleted", "id": bank_id}


def create_product_type(db: Session, type_name: str):
    clean_name = normalize_title(type_name, "Название типа продукта", min_len=2, max_len=50)

    existing_names = db.execute(select(ProductType.id, ProductType.type_name)).all()
    if has_duplicate_normalized(existing_names, clean_name):
        raise HTTPException(status_code=400, detail="Тип продукта уже существует")

    next_id = db.execute(select(func.coalesce(func.max(ProductType.id), 0) + 1)).scalar_one()
    product_type = ProductType(id=int(next_id), type_name=clean_name)
    db.add(product_type)
    db.commit()
    return {"id": product_type.id, "type_name": product_type.type_name}


def update_product_type(db: Session, type_id: int, type_name: str):
    clean_name = normalize_title(type_name, "Название типа продукта", min_len=2, max_len=50)

    product_type = db.get(ProductType, type_id)
    if not product_type:
        raise HTTPException(status_code=404, detail="Тип продукта не найден")

    existing_names = db.execute(select(ProductType.id, ProductType.type_name)).all()
    if has_duplicate_normalized(existing_names, clean_name, exclude_id=type_id):
        raise HTTPException(status_code=400, detail="Тип продукта с таким названием уже есть")

    product_type.type_name = clean_name
    db.add(product_type)
    db.commit()
    db.refresh(product_type)
    return {"id": product_type.id, "type_name": product_type.type_name}


def delete_product_type(db: Session, type_id: int):
    product_type = db.get(ProductType, type_id)
    if not product_type:
        raise HTTPException(status_code=404, detail="Тип продукта не найден")

    linked_products = (
        db.execute(select(func.count()).select_from(Product).where(Product.type_id == type_id))
        .scalar_one()
    )
    if int(linked_products or 0) > 0:
        raise HTTPException(status_code=400, detail="Нельзя удалить тип: есть связанные продукты")

    db.delete(product_type)
    db.commit()
    return {"status": "deleted", "id": type_id}


def create_currency(db: Session, currency_code: str):
    clean_code = normalize_currency_code(currency_code)

    exists = db.execute(
        select(Currency.id).where(func.upper(Currency.currency_code) == clean_code)
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Валюта уже существует")

    next_id = db.execute(select(func.coalesce(func.max(Currency.id), 0) + 1)).scalar_one()
    currency = Currency(id=int(next_id), currency_code=clean_code)
    db.add(currency)
    db.commit()
    return {"id": currency.id, "currency_code": currency.currency_code}


def update_currency(db: Session, currency_id: int, currency_code: str):
    clean_code = normalize_currency_code(currency_code)

    currency = db.get(Currency, currency_id)
    if not currency:
        raise HTTPException(status_code=404, detail="Валюта не найдена")

    duplicate = db.execute(
        select(Currency.id)
        .where(func.upper(Currency.currency_code) == clean_code)
        .where(Currency.id != currency_id)
    ).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status_code=400, detail="Валюта с таким кодом уже есть")

    currency.currency_code = clean_code
    db.add(currency)
    db.commit()
    db.refresh(currency)
    return {"id": currency.id, "currency_code": currency.currency_code}


def delete_currency(db: Session, currency_id: int):
    currency = db.get(Currency, currency_id)
    if not currency:
        raise HTTPException(status_code=404, detail="Валюта не найдена")

    linked_products = (
        db.execute(select(func.count()).select_from(Product).where(Product.currency_id == currency_id))
        .scalar_one()
    )
    if int(linked_products or 0) > 0:
        raise HTTPException(status_code=400, detail="Нельзя удалить валюту: есть связанные продукты")

    db.delete(currency)
    db.commit()
    return {"status": "deleted", "id": currency_id}


def create_product(db: Session, payload: ProductCreate):
    validate_product_limits(payload.interest_rate, payload.min_deposit, payload.term_months)
    product_title = normalize_title(payload.product_title, "Название продукта", min_len=2, max_len=150)

    existing_titles = db.execute(select(Product.id, Product.product_title)).all()
    if has_duplicate_normalized(existing_titles, product_title):
        raise HTTPException(status_code=400, detail="Продукт с таким названием уже существует")

    product = Product(
        bank_id=payload.bank_id,
        type_id=payload.type_id,
        risk_id=payload.risk_id,
        currency_id=payload.currency_id,
        client_id=payload.client_id,
        product_title=product_title,
        interest_rate=payload.interest_rate,
        min_deposit=payload.min_deposit,
        term_months=payload.term_months,
        description=collapse_spaces(payload.description or "") or None,
    )
    db.add(product)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Имеются ошибки ввода") from exc
    db.refresh(product)
    return {
        "id": product.id,
        "product_title": product.product_title,
    }


def update_product_rate(db: Session, product_id: int, payload: ProductRateUpdate):
    validate_product_limits(payload.interest_rate, payload.min_deposit, payload.term_months)
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден")

    product.interest_rate = payload.interest_rate
    product.min_deposit = payload.min_deposit
    product.term_months = payload.term_months

    db.add(product)
    db.commit()
    db.refresh(product)

    return {
        "id": product.id,
        "interest_rate": float(product.interest_rate),
        "min_deposit": float(product.min_deposit),
        "term_months": product.term_months,
    }


def update_product_full(db: Session, product_id: int, payload: ProductFullUpdate):
    validate_product_limits(payload.interest_rate, payload.min_deposit, payload.term_months)
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден")

    product_title = normalize_title(payload.product_title, "Название продукта", min_len=2, max_len=150)
    existing_titles = db.execute(select(Product.id, Product.product_title)).all()
    if has_duplicate_normalized(existing_titles, product_title, exclude_id=product_id):
        raise HTTPException(status_code=400, detail="Продукт с таким названием уже существует")

    product.bank_id = payload.bank_id
    product.type_id = payload.type_id
    product.risk_id = payload.risk_id
    product.currency_id = payload.currency_id
    product.client_id = payload.client_id
    product.product_title = product_title
    product.interest_rate = payload.interest_rate
    product.min_deposit = payload.min_deposit
    product.term_months = payload.term_months
    product.description = collapse_spaces(payload.description or "") or None
    product.is_active = payload.is_active

    db.add(product)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Имеются ошибки ввода") from exc
    db.refresh(product)

    return {
        "id": product.id,
        "product_title": product.product_title,
        "is_active": product.is_active,
    }


def delete_product(db: Session, product_id: int):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден")

    db.delete(product)
    db.commit()
    return {"status": "deleted", "id": product_id}

@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(func.count()).select_from(Bank))
    return {"status": "ok"}


@app.get("/api/products")
def api_products(
    type_name: str | None = Query(default=None),
    bank_name: str | None = Query(default=None),
    currency_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return list_products(db, type_name, bank_name, currency_code)


@app.get("/api/banks")
def api_banks(
    bank_name: str | None = Query(default=None),
    rating: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return list_banks(db, bank_name, rating)


@app.get("/api/products/by-bank/{bank_name}")
def api_products_by_bank(bank_name: str, db: Session = Depends(get_db)):
    return products_by_bank(db, bank_name)


@app.get("/api/banks/by-product/{product_name}")
def api_bank_by_product(product_name: str, db: Session = Depends(get_db)):
    bank = bank_by_product(db, product_name)
    if not bank:
        raise HTTPException(status_code=404, detail="Bank for this product was not found")
    return bank


@app.get("/api/analytics/products-count-by-bank-type")
def api_products_count_by_bank_type(db: Session = Depends(get_db)):
    return products_count_by_bank_type(db)


@app.get("/api/analytics/products-count-by-bank")
def api_products_count_by_bank(
    bank_name: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    return products_count_in_bank(db, bank_name)


@app.get("/api/analytics/product-summary")
def api_product_summary(db: Session = Depends(get_db)):
    return product_summary(db)


@app.post("/api/banks")
def api_create_bank(payload: BankCreate, db: Session = Depends(get_db)):
    return create_bank(db, payload)


@app.post("/api/products")
def api_create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    return create_product(db, payload)


@app.put("/api/products/{product_id}/rate")
def api_update_product_rate(
    product_id: int,
    payload: ProductRateUpdate,
    db: Session = Depends(get_db),
):
    return update_product_rate(db, product_id, payload)


@app.put("/api/products/{product_id}")
def api_update_product_full(
    product_id: int,
    payload: ProductFullUpdate,
    db: Session = Depends(get_db),
):
    return update_product_full(db, product_id, payload)


@app.delete("/api/products/{product_id}")
def api_delete_product(product_id: int, db: Session = Depends(get_db)):
    return delete_product(db, product_id)


@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    total_banks = db.scalar(select(func.count()).select_from(Bank)) or 0
    total_products = db.scalar(select(func.count()).select_from(Product)) or 0
    total_types = db.scalar(select(func.count()).select_from(ProductType)) or 0
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "total_banks": total_banks,
            "total_products": total_products,
            "total_types": total_types,
            "db_name": HOME_DB_NAME,
            "db_author": HOME_DB_AUTHOR,
            "db_desc": HOME_DB_DESC,
        },
    )


@app.get("/products")
def products_page(
    request: Request,
    type_name: str | None = None,
    bank_name: str | None = None,
    currency_code: str | None = None,
    reset: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    if reset:
        type_name = None
        bank_name = None
        currency_code = None

    rows = list_products(db, type_name, bank_name, currency_code)
    options = build_search_options(db)
    matrix = product_filter_matrix(db)
    return templates.TemplateResponse(
        "products.html",
        {
            "request": request,
            "rows": rows,
            "type_name": type_name or "",
            "bank_name": bank_name or "",
            "currency_code": currency_code or "",
            "type_names": options["type_names"],
            "bank_names": options["bank_names"],
            "currency_codes": options["currency_codes"],
            "matrix": matrix,
        },
    )


@app.get("/banks")
def banks_page(
    request: Request,
    rating: str | None = None,
    reset: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    if reset:
        rating = None

    rows = list_banks(db, None, rating)
    options = build_search_options(db)
    return templates.TemplateResponse(
        "banks.html",
        {
            "request": request,
            "rows": rows,
            "rating": rating or "",
            "ratings": options["ratings"],
        },
    )


@app.get("/analytics")
def analytics_page(
    request: Request,
    selected_bank_id: int | None = None,
    db: Session = Depends(get_db),
):
    cards = bank_cards(db)
    if not selected_bank_id and cards:
        selected_bank_id = int(cards[0]["id"])

    selected = bank_analytics(db, selected_bank_id) if selected_bank_id else None
    market = market_reference(db)
    comparison_rows = bank_comparison_rows(db)
    for row in comparison_rows:
        row["rate_phrase"] = format_vs_market(float(row["avg_rate"]), float(market["avg_rate"]), "rate")
        row["deposit_phrase"] = format_vs_market(float(row["avg_deposit"]), float(market["avg_deposit"]), "deposit")
        row["term_phrase"] = format_vs_market(float(row["avg_term"]), float(market["avg_term"]), "term")

    type_analytics = overall_type_analytics(db)
    top_products = top_rate_products(db, 5)
    currency_stats = currency_distribution(db)

    if selected and selected["summary"]:
        summary = selected["summary"]
        selected["phrases"] = {
            "rate": format_vs_market(float(summary["avg_rate"]), float(market["avg_rate"]), "rate"),
            "deposit": format_vs_market(
                float(summary["avg_deposit"]), float(market["avg_deposit"]), "deposit"
            ),
            "term": format_vs_market(float(summary["avg_term"]), float(market["avg_term"]), "term"),
        }

    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "cards": cards,
            "selected": selected,
            "selected_bank_id": selected_bank_id,
            "market": market,
            "comparison_rows": comparison_rows,
            "type_analytics": type_analytics,
            "top_products": top_products,
            "currency_stats": currency_stats,
        },
    )


@app.get("/manage")
def manage_page(
    request: Request,
    selected_product_id: str | None = None,
    selected_product_id_manual: str = "",
    selected_bank_id: str | None = None,
    selected_bank_id_manual: str = "",
    selected_type_id: str | None = None,
    selected_type_id_manual: str = "",
    selected_currency_id: str | None = None,
    selected_currency_id_manual: str = "",
    bank_mode: str | None = None,
    type_mode: str | None = None,
    currency_mode: str | None = None,
    product_mode: str | None = None,
    message: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    def parse_optional_id(raw_value: str | None) -> int | None:
        if raw_value is None:
            return None
        value = raw_value.strip()
        if not value:
            return None
        return int(value) if value.isdigit() else None

    selected_product_id = parse_optional_id(selected_product_id)
    selected_bank_id = parse_optional_id(selected_bank_id)
    selected_type_id = parse_optional_id(selected_type_id)
    selected_currency_id = parse_optional_id(selected_currency_id)

    if selected_product_id_manual.strip().isdigit():
        selected_product_id = int(selected_product_id_manual.strip())
    if selected_bank_id_manual.strip().isdigit():
        selected_bank_id = int(selected_bank_id_manual.strip())
    if selected_type_id_manual.strip().isdigit():
        selected_type_id = int(selected_type_id_manual.strip())
    if selected_currency_id_manual.strip().isdigit():
        selected_currency_id = int(selected_currency_id_manual.strip())

    if bank_mode not in {"create", "edit"}:
        bank_mode = "edit" if selected_bank_id else "create"
    if type_mode not in {"create", "edit"}:
        type_mode = "edit" if selected_type_id else "create"
    if currency_mode not in {"create", "edit"}:
        currency_mode = "edit" if selected_currency_id else "create"
    if product_mode not in {"create", "edit"}:
        product_mode = "edit" if selected_product_id else "create"

    if bank_mode == "create":
        selected_bank_id = None
    if type_mode == "create":
        selected_type_id = None
    if currency_mode == "create":
        selected_currency_id = None
    if product_mode == "create":
        selected_product_id = None

    banks = db.execute(select(Bank).order_by(Bank.bank_name)).scalars().all()
    types = db.execute(select(ProductType).order_by(ProductType.type_name)).scalars().all()
    risks = db.execute(select(RiskLevel).order_by(RiskLevel.id)).scalars().all()
    currencies = db.execute(select(Currency).order_by(Currency.currency_code)).scalars().all()
    rating_choices = DEFAULT_RATING_CHOICES

    product_options = (
        db.execute(
            select(Product.id, Product.product_title, Bank.bank_name)
            .join(Bank, Product.bank_id == Bank.id)
            .order_by(Product.product_title, Product.id)
        )
        .mappings()
        .all()
    )
    product_options = [row_to_dict(r) for r in product_options]

    selected_product = None
    if selected_product_id:
        selected_product = (
            db.execute(
                select(
                    Product.id,
                    Product.bank_id,
                    Product.type_id,
                    Product.risk_id,
                    Product.currency_id,
                    Product.client_id,
                    Product.product_title,
                    Product.interest_rate,
                    Product.min_deposit,
                    Product.term_months,
                    Product.description,
                    Product.is_active,
                    Bank.bank_name,
                    ProductType.type_name,
                )
                .join(Bank, Product.bank_id == Bank.id)
                .join(ProductType, Product.type_id == ProductType.id)
                .where(Product.id == selected_product_id)
            )
            .mappings()
            .first()
        )
        selected_product = row_to_dict(selected_product) if selected_product else None

    selected_bank = None
    if selected_bank_id:
        selected_bank = (
            db.execute(
                select(
                    Bank.id,
                    Bank.bank_name,
                    Bank.license_no,
                    Bank.rating,
                    func.count(Product.id).label("products_count"),
                )
                .outerjoin(Product, Product.bank_id == Bank.id)
                .where(Bank.id == selected_bank_id)
                .group_by(Bank.id, Bank.bank_name, Bank.license_no, Bank.rating)
            )
            .mappings()
            .first()
        )
        selected_bank = row_to_dict(selected_bank) if selected_bank else None

    selected_type = None
    if selected_type_id:
        selected_type = (
            db.execute(
                select(
                    ProductType.id,
                    ProductType.type_name,
                    func.count(Product.id).label("products_count"),
                )
                .outerjoin(Product, Product.type_id == ProductType.id)
                .where(ProductType.id == selected_type_id)
                .group_by(ProductType.id, ProductType.type_name)
            )
            .mappings()
            .first()
        )
        selected_type = row_to_dict(selected_type) if selected_type else None

    selected_currency = None
    if selected_currency_id:
        selected_currency = (
            db.execute(
                select(
                    Currency.id,
                    Currency.currency_code,
                    func.count(Product.id).label("products_count"),
                )
                .outerjoin(Product, Product.currency_id == Currency.id)
                .where(Currency.id == selected_currency_id)
                .group_by(Currency.id, Currency.currency_code)
            )
            .mappings()
            .first()
        )
        selected_currency = row_to_dict(selected_currency) if selected_currency else None

    selected_bank_license_digits = ""
    if selected_bank and selected_bank.get("license_no"):
        selected_bank_license_digits = selected_bank["license_no"].replace("№", "", 1)

    message_map: dict[str, tuple[str, str]] = {
        "bank-created": ("success", "Ввод прошел успешно"),
        "bank-updated": ("success", "Изменения банка сохранены"),
        "bank-deleted": ("success", "Банк удален"),
        "type-created": ("success", "Тип продукта добавлен"),
        "type-updated": ("success", "Тип продукта обновлен"),
        "type-deleted": ("success", "Тип продукта удален"),
        "currency-created": ("success", "Валюта добавлена"),
        "currency-updated": ("success", "Валюта обновлена"),
        "currency-deleted": ("success", "Валюта удалена"),
        "product-created": ("success", "Продукт добавлен"),
        "product-full-updated": ("success", "Продукт обновлен"),
        "product-deleted": ("success", "Продукт удален"),
    }

    modal_message = None
    modal_status = None
    if message:
        if message in message_map:
            modal_status, modal_message = message_map[message]
        else:
            modal_status = status if status in {"success", "error", "info"} else "error"
            modal_message = message

    return templates.TemplateResponse(
        "manage.html",
        {
            "request": request,
            "message": modal_message,
            "message_status": modal_status,
            "selected_product_id": selected_product_id,
            "selected_bank_id": selected_bank_id,
            "selected_type_id": selected_type_id,
            "selected_currency_id": selected_currency_id,
            "selected_product": selected_product,
            "selected_bank": selected_bank,
            "selected_type": selected_type,
            "selected_currency": selected_currency,
            "product_options": product_options,
            "banks": banks,
            "types": types,
            "risks": risks,
            "currencies": currencies,
            "rating_choices": rating_choices,
            "bank_mode": bank_mode,
            "type_mode": type_mode,
            "currency_mode": currency_mode,
            "product_mode": product_mode,
            "selected_bank_license_digits": selected_bank_license_digits,
        },
    )


@app.post("/manage/banks")
def manage_create_bank(
    bank_name: str = Form(...),
    license_no_digits: str = Form(...),
    rating: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        create_bank(
            db,
            BankCreate(
                bank_name=bank_name,
                license_no=f"№{license_no_digits.strip()}",
                rating=rating,
            ),
        )
    except HTTPException as exc:
        return RedirectResponse(
            url=f"/manage?bank_mode=create&status=error&message={quote_plus(str(exc.detail))}",
            status_code=303,
        )
    return RedirectResponse(url="/manage?bank_mode=create&status=success&message=bank-created", status_code=303)


@app.post("/manage/banks/{bank_id}/update")
def manage_update_bank(
    bank_id: int,
    bank_name: str = Form(...),
    license_no_digits: str = Form(...),
    rating: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        update_bank(
            db,
            bank_id,
            BankCreate(
                bank_name=bank_name,
                license_no=f"№{license_no_digits.strip()}",
                rating=rating,
            ),
        )
    except HTTPException as exc:
        return RedirectResponse(
            url=f"/manage?bank_mode=edit&selected_bank_id={bank_id}&status=error&message={quote_plus(str(exc.detail))}",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/manage?bank_mode=edit&selected_bank_id={bank_id}&status=success&message=bank-updated",
        status_code=303,
    )


@app.post("/manage/banks/{bank_id}/delete")
def manage_delete_bank(bank_id: int, db: Session = Depends(get_db)):
    try:
        delete_bank(db, bank_id)
    except HTTPException as exc:
        return RedirectResponse(
            url=f"/manage?bank_mode=edit&selected_bank_id={bank_id}&status=error&message={quote_plus(str(exc.detail))}",
            status_code=303,
        )
    return RedirectResponse(url="/manage?bank_mode=create&status=success&message=bank-deleted", status_code=303)


@app.post("/manage/product-types")
def manage_create_product_type(type_name: str = Form(...), db: Session = Depends(get_db)):
    try:
        create_product_type(db, type_name)
    except HTTPException as exc:
        return RedirectResponse(
            url=f"/manage?type_mode=create&status=error&message={quote_plus(str(exc.detail))}",
            status_code=303,
        )
    return RedirectResponse(url="/manage?type_mode=create&status=success&message=type-created", status_code=303)


@app.post("/manage/product-types/{type_id}/update")
def manage_update_product_type(
    type_id: int,
    type_name: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        update_product_type(db, type_id, type_name)
    except HTTPException as exc:
        return RedirectResponse(
            url=f"/manage?type_mode=edit&selected_type_id={type_id}&status=error&message={quote_plus(str(exc.detail))}",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/manage?type_mode=edit&selected_type_id={type_id}&status=success&message=type-updated",
        status_code=303,
    )


@app.post("/manage/product-types/{type_id}/delete")
def manage_delete_product_type(type_id: int, db: Session = Depends(get_db)):
    try:
        delete_product_type(db, type_id)
    except HTTPException as exc:
        return RedirectResponse(
            url=f"/manage?type_mode=edit&selected_type_id={type_id}&status=error&message={quote_plus(str(exc.detail))}",
            status_code=303,
        )
    return RedirectResponse(url="/manage?type_mode=create&status=success&message=type-deleted", status_code=303)


@app.post("/manage/currencies")
def manage_create_currency(currency_code: str = Form(...), db: Session = Depends(get_db)):
    try:
        create_currency(db, currency_code)
    except HTTPException as exc:
        return RedirectResponse(
            url=f"/manage?currency_mode=create&status=error&message={quote_plus(str(exc.detail))}",
            status_code=303,
        )
    return RedirectResponse(url="/manage?currency_mode=create&status=success&message=currency-created", status_code=303)


@app.post("/manage/currencies/{currency_id}/update")
def manage_update_currency(
    currency_id: int,
    currency_code: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        update_currency(db, currency_id, currency_code)
    except HTTPException as exc:
        return RedirectResponse(
            url=f"/manage?currency_mode=edit&selected_currency_id={currency_id}&status=error&message={quote_plus(str(exc.detail))}",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/manage?currency_mode=edit&selected_currency_id={currency_id}&status=success&message=currency-updated",
        status_code=303,
    )


@app.post("/manage/currencies/{currency_id}/delete")
def manage_delete_currency(currency_id: int, db: Session = Depends(get_db)):
    try:
        delete_currency(db, currency_id)
    except HTTPException as exc:
        return RedirectResponse(
            url=f"/manage?currency_mode=edit&selected_currency_id={currency_id}&status=error&message={quote_plus(str(exc.detail))}",
            status_code=303,
        )
    return RedirectResponse(url="/manage?currency_mode=create&status=success&message=currency-deleted", status_code=303)


@app.post("/manage/products")
def manage_create_product(
    bank_id: int = Form(...),
    type_id: int = Form(...),
    risk_id: int = Form(...),
    currency_id: int = Form(...),
    product_title: str = Form(...),
    interest_rate: float = Form(...),
    min_deposit: float = Form(...),
    term_months: int = Form(...),
    description: str = Form(default=""),
    db: Session = Depends(get_db),
):
    try:
        created = create_product(
            db,
            ProductCreate(
                bank_id=bank_id,
                type_id=type_id,
                risk_id=risk_id,
                currency_id=currency_id,
                client_id=None,
                product_title=product_title,
                interest_rate=interest_rate,
                min_deposit=min_deposit,
                term_months=term_months,
                description=description,
            ),
        )
    except HTTPException as exc:
        return RedirectResponse(
            url=f"/manage?product_mode=create&status=error&message={quote_plus(str(exc.detail))}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/manage?product_mode=edit&selected_product_id={created['id']}&status=success&message=product-created",
        status_code=303,
    )


@app.post("/manage/products/{product_id}/full")
def manage_update_product_full(
    product_id: int,
    bank_id: int = Form(...),
    type_id: int = Form(...),
    risk_id: int = Form(...),
    currency_id: int = Form(...),
    product_title: str = Form(...),
    interest_rate: float = Form(...),
    min_deposit: float = Form(...),
    term_months: int = Form(...),
    description: str = Form(default=""),
    is_active: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    try:
        update_product_full(
            db,
            product_id,
            ProductFullUpdate(
                bank_id=bank_id,
                type_id=type_id,
                risk_id=risk_id,
                currency_id=currency_id,
                client_id=None,
                product_title=product_title,
                interest_rate=interest_rate,
                min_deposit=min_deposit,
                term_months=term_months,
                description=description.strip() or None,
                is_active=bool(is_active),
            ),
        )
    except HTTPException as exc:
        return RedirectResponse(
            url=f"/manage?product_mode=edit&selected_product_id={product_id}&status=error&message={quote_plus(str(exc.detail))}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/manage?product_mode=edit&selected_product_id={product_id}&status=success&message=product-full-updated",
        status_code=303,
    )


@app.post("/manage/products/{product_id}/delete")
def manage_delete_product(product_id: int, db: Session = Depends(get_db)):
    try:
        delete_product(db, product_id)
    except HTTPException as exc:
        return RedirectResponse(
            url=f"/manage?product_mode=edit&selected_product_id={product_id}&status=error&message={quote_plus(str(exc.detail))}",
            status_code=303,
        )
    return RedirectResponse(url="/manage?product_mode=create&status=success&message=product-deleted", status_code=303)








































