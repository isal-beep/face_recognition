from app import app, db
from models import User
from werkzeug.security import generate_password_hash

owner_email = "owner@company.com"
owner_password = "owner123"
owner_role = "OWNER"

with app.app_context():
    # cek apakah owner sudah ada
    existing_owner = User.query.filter_by(email=owner_email).first()
    
    if existing_owner:
        print("Owner sudah ada di database.")
    else:
        owner = User(
            email=owner_email,
            password_hash=generate_password_hash(owner_password),
            role=owner_role
        )
        db.session.add(owner)
        db.session.commit()
        print(f"Owner berhasil ditambahkan: {owner_email} / {owner_password}")
