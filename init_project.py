from database import init_db, seed_admin

if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    print("Database initialized.")

    print("Seeding admin user...")
    # Default admin credentials.
    # In production, this should be changed immediately or passed via env vars.
    seed_admin('admin', 'admin123')
    print("Done.")
