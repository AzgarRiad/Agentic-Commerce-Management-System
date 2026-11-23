from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, DateTime, Integer, NUMERIC, String, func

Base = declarative_base()
class Product(Base):
    __tablename__ = "product"
    id = Column(Integer, primary_key= True, index= True)
    name = Column(String)
    category = Column(String)
    price = Column(NUMERIC(10,2))
    stock_quantity = Column(Integer)
class Order(Base):
    __tablename__ = "order_list"
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_name = Column(String)
    product_name = Column(String)
    size = Column(String)
    phone = Column(String, nullable=False, default="")
    quantity = Column(Integer)
    status = Column(String)
    created_at = Column(
                        DateTime(timezone=True),
                        nullable=False,
                        server_default=func.now(),
                        )

