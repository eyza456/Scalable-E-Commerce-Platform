import concurrent.futures
import unittest
import uuid

from fastapi import HTTPException
from jose import jwt
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base, engine as production_engine
from app.models import User
from app.schemas.user import UserUpdate
from app.routers.users import update_me
from app.core.config import settings


class ProfileStability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_profile_" + uuid.uuid4().hex
        with production_engine.begin() as c:
            c.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.engine = create_engine(production_engine.url, connect_args={"options":f"-csearch_path={cls.schema}"})
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with production_engine.begin() as c:
            c.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))

    def setUp(self):
        with self.engine.begin() as c:
            c.execute(User.__table__.delete())
        with self.sessions() as db:
            db.add_all([User(id=1,name="First user",email="first@example.com",password_hash="unchanged"),
                        User(id=2,name="Other user",email="other@example.com",password_hash="other")])
            db.commit()

    def test_partial_name_update_keeps_email_password_and_role(self):
        with self.sessions() as db:
            profile = update_me(UserUpdate(name="  New name  "), db.get(User,1), db)
            self.assertEqual(profile.name,"New name")
            self.assertEqual(profile.email,"first@example.com")
            self.assertEqual(db.get(User,1).password_hash,"unchanged")
            self.assertEqual(profile.role,"Customer")
            self.assertEqual(db.get(User,2).name,"Other user")
            self.assertNotIn("password_hash",profile.model_dump())

    def test_email_update_renews_token(self):
        with self.sessions() as db:
            profile = update_me(UserUpdate(email="new@example.com"),db.get(User,1),db)
        claims = jwt.decode(profile.access_token,settings.SECRET_KEY,algorithms=[settings.JWT_ALGORITHM])
        self.assertEqual(claims["email"],"new@example.com")
        self.assertEqual(claims["sub"],"1")
        self.assertEqual(claims["role"],"Customer")

    def test_duplicate_email_rejects_entire_update(self):
        with self.sessions() as db:
            with self.assertRaises(HTTPException) as caught:
                update_me(UserUpdate(name="Changed",email="OTHER@example.com"),db.get(User,1),db)
            self.assertEqual(caught.exception.status_code,409)
            db.rollback()
            self.assertEqual(db.get(User,1).name,"First user")

    def test_same_email_is_allowed(self):
        with self.sessions() as db:
            self.assertEqual(update_me(UserUpdate(email="first@example.com"),db.get(User,1),db).email,"first@example.com")

    def test_forbid_privileged_fields_and_invalid_data(self):
        for data in ({},{"role":"admin"},{"id":2},{"is_active":False},{"password":"test"},
                     {"name":None},{"email":None},{"name":"  "},{"email":"invalid"}):
            with self.subTest(data=data),self.assertRaises(ValidationError):
                UserUpdate(**data)

    def test_concurrent_email_claims_only_allow_one_account(self):
        def update(user_id):
            with self.sessions() as db:
                try:
                    update_me(UserUpdate(email="shared@example.com"),db.get(User,user_id),db)
                    return 200
                except HTTPException as exc:
                    return exc.status_code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(update,[1,2])),[200,409])


if __name__ == "__main__":
    unittest.main(verbosity=2)
