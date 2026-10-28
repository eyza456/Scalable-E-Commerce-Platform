import unittest
import uuid
from pydantic import ValidationError
from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker

from app.database import Base,engine as production_engine
from app.models import User
from app.schemas.user import UserCreate,UserLogin,UserUpdate
from app.routers.auth import register,login
from app.core.security import hash_password,verify_password


class InputLimits(unittest.TestCase):
    def test_password_above_72_bytes_is_rejected_by_both_schemas(self):
        for password in ("x"*80,"é"*37):
            with self.subTest(bytes=len(password.encode())):
                with self.assertRaises(ValidationError):UserCreate(name="User",email="test@example.com",password=password)
                with self.assertRaises(ValidationError):UserLogin(email="test@example.com",password=password)

    def test_72_byte_ascii_password_is_not_truncated(self):
        password="x"*71+"a"
        UserCreate(name="User",email="test@example.com",password=password)
        hashed=hash_password(password)
        self.assertTrue(verify_password(password,hashed))
        self.assertFalse(verify_password("x"*71+"b",hashed))
        self.assertFalse(verify_password(password+"more",hashed))

    def test_utf8_limit_uses_bytes_not_characters(self):
        password="é"*36
        UserCreate(name="User",email="test@example.com",password=password)
        self.assertTrue(verify_password(password,hash_password(password)))

    def test_long_valid_email_registers_and_logs_in(self):
        schema="test_input_"+uuid.uuid4().hex
        with production_engine.begin() as c:c.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine=create_engine(production_engine.url,connect_args={"options":f"-csearch_path={schema}"})
        try:
            Base.metadata.create_all(engine)
            email="a"*50+"@"+"b"*60+"."+"c"*50+".com"
            self.assertGreater(len(email),150)
            with sessionmaker(bind=engine)() as db:
                created=register(UserCreate(name="Email test",email=email,password="Safe-Test-2026"),db)
                self.assertEqual(created.email,email)
                self.assertEqual(db.query(User).count(),1)
                self.assertIn("access_token",login(UserLogin(email=email.upper(),password="Safe-Test-2026"),db))
            UserUpdate(email=email)
        finally:
            engine.dispose()
            with production_engine.begin() as c:c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


if __name__=="__main__":unittest.main(verbosity=2)
