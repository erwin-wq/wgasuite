from app.db.session import SessionLocal
from app.services.development_admin import configure_development_admin
from app.services.development_credentials import load_development_credentials


def main() -> None:
    credentials = load_development_credentials()
    if credentials is None:
        print("Development admin configuration skipped outside the development environment.")
        return

    with SessionLocal() as db:
        user = configure_development_admin(db, credentials.email, credentials.password)

    print(f"Development admin configured: {user.email}")


if __name__ == "__main__":
    main()
