import unittest
import uuid

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base, engine as production_engine
from app.models import Category, Product
from app.schemas import ProductCreate, ProductUpdate
from app.schemas.category import CategoryCreate
from app.crud.product import create_product, update_product, get_products
from app.routers.categories import create_category, update_category, delete_category


class CatalogStability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_catalog_" + uuid.uuid4().hex
        with production_engine.begin() as c:
            c.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.engine = create_engine(production_engine.url, connect_args={"options": f"-csearch_path={cls.schema}"})
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with production_engine.begin() as c:
            c.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(Product.__table__.delete())
            c.execute(Category.__table__.delete())
        self.db = self.sessions()
        self.addCleanup(self.db.close)
        self.category = create_category(CategoryCreate(name="Electronics"), self.db, {})

    def product(self, name="Laptop", **fields):
        data = {"name": name, "price": "10.00", "stock": 3, **fields}
        return create_product(self.db, ProductCreate(**data))

    def test_create_update_and_delete_category(self):
        result = update_category(self.category.id, CategoryCreate(name="Hardware", description="Devices"), self.db, {})
        self.assertEqual(result.name, "Hardware")
        category_id = result.id
        delete_category(category_id, self.db, {})
        self.assertIsNone(self.db.get(Category, category_id))

    def test_category_names_are_trimmed_and_case_insensitive_unique(self):
        with self.assertRaises(HTTPException) as caught:
            create_category(CategoryCreate(name=" electronics "), self.db, {})
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.db.query(Category).count(), 1)

    def test_category_assignment_and_legacy_name(self):
        product = self.product(category_id=self.category.id)
        self.assertEqual(product.category, "Electronics")
        legacy = self.product(name="Desktop", category=" electronics ")
        self.assertEqual(legacy.category_id, self.category.id)

    def test_unknown_category_is_not_created_implicitly(self):
        for fields in ({"category_id":999999}, {"category":"Missing"}):
            with self.subTest(fields=fields), self.assertRaises(HTTPException) as caught:
                self.product(**fields)
            self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(self.db.query(Product).count(), 0)

    def test_cannot_delete_used_category(self):
        self.product(category_id=self.category.id)
        with self.assertRaises(HTTPException) as caught:
            delete_category(self.category.id, self.db, {})
        self.assertEqual(caught.exception.status_code, 409)

    def test_renaming_category_updates_product_display(self):
        product = self.product(category_id=self.category.id)
        update_category(self.category.id, CategoryCreate(name="Hardware"), self.db, {})
        self.db.refresh(product)
        self.assertEqual(product.category, "Hardware")

    def test_clear_category_preserves_product(self):
        product = self.product(category_id=self.category.id)
        update_product(self.db, product, ProductUpdate(category_id=None))
        self.assertIsNone(product.category_id)
        self.assertIsNone(product.category)
        delete_category(self.category.id, self.db, {})
        self.assertEqual(self.db.query(Product).count(), 1)

    def test_combined_filters_and_stable_pagination(self):
        first = self.product(category_id=self.category.id)
        self.product(name="Laptop empty", stock=0, category_id=self.category.id)
        other = self.product(name="Laptop second", category_id=self.category.id)
        self.product(name="Laptop uncategorized")
        rows = get_products(self.db, name="LAP", category_id=self.category.id, available=True, skip=1, limit=1)
        self.assertEqual([p.id for p in rows], [other.id])
        self.assertEqual(get_products(self.db, name="LAP", category_id=self.category.id, available=True)[0].id, first.id)

    def test_unavailable_includes_inactive_and_out_of_stock(self):
        empty = self.product(name="Empty", stock=0)
        inactive = self.product(name="Inactive")
        update_product(self.db, inactive, ProductUpdate(is_active=False))
        self.product(name="Available")
        self.assertEqual({p.id for p in get_products(self.db, available=False)}, {empty.id, inactive.id})

    def test_search_treats_percent_and_underscore_as_literal(self):
        literal = self.product(name="Rate 100%_special")
        self.product(name="Rate 100ABCspecial")
        self.assertEqual([p.id for p in get_products(self.db, name="%_")], [literal.id])

    def test_empty_result(self):
        self.product()
        self.assertEqual(get_products(self.db, category_id=999999), [])

    def test_reject_ambiguous_category_or_null_required_fields(self):
        with self.assertRaises(ValidationError):
            ProductCreate(name="Test", price=1, stock=1, category="Electronics", category_id=self.category.id)
        for field in ("name", "price", "stock", "is_active"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                ProductUpdate(**{field:None})
        with self.assertRaises(ValidationError):
            CategoryCreate(name="   ")


if __name__ == "__main__":
    unittest.main(verbosity=2)
