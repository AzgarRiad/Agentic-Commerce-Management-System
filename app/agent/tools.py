"""Tool functions the LLM can call."""
from app.agent.database import session
from app.agent.database_models import Product, Order


def _like(text: str) -> str:
    """Escape % and _ so user text is not treated as a wildcard."""
    return text.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def get_product_info(product_name: str) -> dict:
    """Find products by full or partial name and return their price and stock.

    Args:
        product_name: Full or partial product name.

    Returns:
        A dict with a 'products' list (name, price, stock) or an 'error'.
    """
    db = session()
    try:
        rows = (
            db.query(Product)
            .filter(Product.name.ilike(f"%{_like(product_name.strip())}%", escape="\\"))
            .all()
        )
        products = [
            {"name": p.name, "price": float(p.price or 0), "stock": p.stock_quantity or 0}
            for p in rows
        ]
    finally:
        db.close()

    if not products:
        return {"error": f"No product found matching '{product_name}'"}
    return {"products": products}


def get_products() -> list[dict]:
    """Get all available products.

    Returns:
        A list of products with id, name, category, price and stock.
    """
    db = session()
    try:
        return [
            {
                "id": p.id,
                "name": p.name or "",
                "category": p.category or "",
                "price": float(p.price or 0),
                "stock": p.stock_quantity or 0,
            }
            for p in db.query(Product).order_by(Product.id).all()
        ]
    finally:
        db.close()


def add_order(customer_name: str, size: str, phone: str, product_name: str, quantity: int) -> dict:
    """Save an order. Ask the customer for their name and phone number first.

    Args:
        customer_name: Name of the customer who wants to order.
        phone: Phone number of the customer (text, keep leading zeros and +).
        size: Size of the product, E.g S, M, L, Xl, XXL.
        product_name: Name of the product (use get_product_info to find the exact name).
        quantity: Number of units requested (1 to 10000).
    """
    customer_name, phone, size, product_name = customer_name.strip(),  str(phone).strip(), size.strip(), product_name.strip()
    if not customer_name:
        return {"status": "error", "message": "Customer name is required."}
    if not phone:
        return {"status": "error", "message": "Phone number is required."}
    if not size:
        return {"status": "error", "message": "size is required."}
    if not product_name:
        return {"status": "error", "message": "Product name is required."}
    if not 1 <= quantity <= 10000:
        return {"status": "error", "message": "Quantity must be between 1 and 10000."}
    if len(customer_name) > 200 or len(phone) > 40:
        return {"status": "error", "message": "Customer name or phone number is too long."}

    db = session()
    try:
        # Same rule as the dashboard: the product must exist (exact name, any case).
        product = (
            db.query(Product)
            .filter(Product.name.ilike(_like(product_name), escape="\\"))
            .first()
        )
        if product is None:
            return {"status": "error", "message": f"Product '{product_name}' not found. Use get_product_info to find the exact name."}
        if (product.stock_quantity or 0) < quantity:
            return {"status": "error", "message": f"Only {product.stock_quantity or 0} in stock for '{product.name}'."}

        order = Order(
            customer_name=customer_name,
            phone=phone,
            product_name=product.name,   # canonical name, so the dashboard can price it
            size=size,
            quantity=quantity,
            status="pending",
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return {
            "status": "success",
            "order_id": order.id,
            "customer_name": order.customer_name,
            "phone": order.phone,
            "product_name": order.product_name,
            "size": order.size,
            "quantity": order.quantity,
        }
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": f"Failed to save order: {e}"}
    finally:
        db.close()


AVAILABLE_TOOLS = {
    "get_product_info": get_product_info,
    "add_order": add_order,
    "get_products": get_products,
}