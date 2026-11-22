"""Dashboard API backed by the ACMS database."""

from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.database import session
from app.agent.database_models import Product, Order

router = APIRouter(prefix="/api")


class ProductInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=200)
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    stock: int = Field(ge=0)


class OrderInput(BaseModel):
    customer: str = Field(default="Walk-in", min_length=1, max_length=200)
    phone: str = Field(default="", max_length=40)
    product_name: str = Field(min_length=1, max_length=200)
    size: str = Field(default="", max_length=100)
    quantity: int = Field(ge=1, le=10000)


class OrderStatusInput(BaseModel):
    status: str = Field(pattern="^(pending|paid|cancelled)$")


def _product_dict(product: Product) -> dict:
    return {
        "id": product.id,
        "name": product.name or "",
        "category": product.category or "",
        "price": float(product.price or 0),
        "stock": product.stock_quantity or 0,
    }


def _order_dict(order: Order) -> dict:
    return {
        "id": order.id,
        "customer": order.customer_name or "",
        "phone": order.phone or "",
        "items": order.product_name or "",
        "size": order.size or "",
        "quantity": order.quantity or 0,
        "status": order.status or "pending",
        "date": (
            order.created_at.strftime("%d/%m/%Y %H:%M:%S")
            if order.created_at
            else ""
        ),
    }


def _clean_required_text(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} cannot be blank",
        )
    return value


@router.get("/products")
def list_products():
    db: Session = session()
    try:
        return [
            _product_dict(item)
            for item in db.query(Product).order_by(Product.id).all()
        ]
    finally:
        db.close()


@router.post("/products", status_code=201)
def create_product(payload: ProductInput):
    name = _clean_required_text(payload.name, "Product name")
    category = _clean_required_text(payload.category, "Category")

    db: Session = session()
    try:
        product = Product(
            name=name,
            category=category,
            price=payload.price,
            stock_quantity=payload.stock,
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return _product_dict(product)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.put("/products/{product_id}")
def update_product(product_id: int, payload: ProductInput):
    name = _clean_required_text(payload.name, "Product name")
    category = _clean_required_text(payload.category, "Category")

    db: Session = session()
    try:
        product = db.get(Product, product_id)
        if product is None:
            raise HTTPException(
                status_code=404,
                detail="Product not found",
            )

        product.name = name
        product.category = category
        product.price = payload.price
        product.stock_quantity = payload.stock

        db.commit()
        db.refresh(product)
        return _product_dict(product)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int):
    db: Session = session()
    try:
        product = db.get(Product, product_id)
        if product is None:
            raise HTTPException(
                status_code=404,
                detail="Product not found",
            )

        db.delete(product)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.get("/orders")
def list_orders():
    db: Session = session()
    try:
        orders = db.query(Order).order_by(Order.id).all()
        return [_order_dict(order) for order in orders]
    finally:
        db.close()


@router.post("/orders", status_code=201)
def create_order(payload: OrderInput):
    customer = _clean_required_text(payload.customer, "Customer name")
    product_name = _clean_required_text(
        payload.product_name,
        "Product name",
    )
    phone = payload.phone.strip()
    size = payload.size.strip()

    db: Session = session()
    try:
        # Reject orders for products that do not exist.
        product = (
            db.query(Product)
            .filter(Product.name == product_name)
            .first()
        )

        if product is None:
            raise HTTPException(
                status_code=404,
                detail="Product not found",
            )

        order = Order(
            customer_name=customer,
            product_name=product.name,
            size=size,
            phone=phone,
            quantity=payload.quantity,
            status="pending",
        )

        db.add(order)
        db.commit()
        db.refresh(order)
        return _order_dict(order)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.patch("/orders/{order_id}")
def update_order_status(
    order_id: int,
    payload: OrderStatusInput,
):
    db: Session = session()
    try:
        order = db.get(Order, order_id)
        if order is None:
            raise HTTPException(
                status_code=404,
                detail="Order not found",
            )

        order.status = payload.status
        db.commit()
        db.refresh(order)
        return _order_dict(order)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.delete("/orders/{order_id}", status_code=204)
def delete_order(order_id: int):
    db: Session = session()
    try:
        order = db.get(Order, order_id)
        if order is None:
            raise HTTPException(
                status_code=404,
                detail="Order not found",
            )

        db.delete(order)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()