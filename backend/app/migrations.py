from sqlalchemy import text

from .database import engine


def run_startup_migrations() -> None:
    if engine.dialect.name != "sqlite":
        # Production uses PostgreSQL, where create_all does not add fields to
        # existing tables. Keep this small additive migration safe to run at startup.
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE appointments ADD COLUMN IF NOT EXISTS stripe_processing_fee_cents INTEGER DEFAULT 0"
            ))
            connection.execute(text(
                "ALTER TABLE checkout_attempts ADD COLUMN IF NOT EXISTS stripe_processing_fee_cents INTEGER DEFAULT 0"
            ))
        return

    with engine.begin() as connection:
        user_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(users)").all()}
        if "google_subject" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN google_subject VARCHAR(255)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_subject ON users (google_subject)"))
        if "last_login_at" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN last_login_at DATETIME"))
        shop_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(barber_shops)").all()
        }
        if "booking_window_days" not in shop_columns:
            connection.execute(
                text("ALTER TABLE barber_shops ADD COLUMN booking_window_days INTEGER DEFAULT 30")
            )
        for column_name, column_type in {
            "admin_message": "TEXT",
            "access_warning_month": "VARCHAR(7)",
            "access_suspended": "BOOLEAN DEFAULT 0",
            "monthly_access_paid_month": "VARCHAR(7)",
        }.items():
            if column_name not in shop_columns:
                connection.execute(text(f"ALTER TABLE barber_shops ADD COLUMN {column_name} {column_type}"))

        appointment_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(appointments)").all()}
        if "sms_opt_in" not in appointment_columns:
            connection.execute(text("ALTER TABLE appointments ADD COLUMN sms_opt_in BOOLEAN DEFAULT 1"))
        if "stripe_processing_fee_cents" not in appointment_columns:
            connection.execute(text("ALTER TABLE appointments ADD COLUMN stripe_processing_fee_cents INTEGER DEFAULT 0"))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS client_notes (
                id INTEGER NOT NULL PRIMARY KEY, shop_id INTEGER NOT NULL, barber_id INTEGER NOT NULL,
                client_key VARCHAR(300) NOT NULL, body TEXT NOT NULL, created_at DATETIME,
                FOREIGN KEY(shop_id) REFERENCES barber_shops (id), FOREIGN KEY(barber_id) REFERENCES barber_profiles (id)
            )
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_client_notes_client_key ON client_notes (client_key)"))

        service_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(services)").all()
        }
        if "barber_id" not in service_columns:
            connection.execute(text("ALTER TABLE services ADD COLUMN barber_id INTEGER"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_services_barber_id ON services (barber_id)"))
            connection.execute(
                text(
                    """
                    UPDATE services
                    SET barber_id = (
                        SELECT id FROM barber_profiles
                        WHERE barber_profiles.shop_id = services.shop_id
                        ORDER BY barber_profiles.is_owner DESC, barber_profiles.id ASC
                        LIMIT 1
                    )
                    WHERE barber_id IS NULL
                    """
                )
            )
        service_table_sql = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'services'")
        ).scalar() or ""
        if "UNIQUE (shop_id, name)" in service_table_sql or "UNIQUE(shop_id, name)" in service_table_sql:
            # SQLite cannot drop a named unique constraint. Rebuild while preserving service IDs,
            # so existing appointments keep their service references intact.
            connection.execute(text("PRAGMA foreign_keys = OFF"))
            connection.execute(text("""
                CREATE TABLE services_rebuilt (
                    id INTEGER NOT NULL PRIMARY KEY,
                    shop_id INTEGER NOT NULL,
                    barber_id INTEGER,
                    name VARCHAR(120) NOT NULL,
                    description TEXT,
                    duration_minutes INTEGER,
                    price_cents INTEGER,
                    booking_fee_cents INTEGER,
                    deposit_cents INTEGER,
                    platform_fee_cents INTEGER,
                    is_active BOOLEAN,
                    FOREIGN KEY(shop_id) REFERENCES barber_shops (id),
                    FOREIGN KEY(barber_id) REFERENCES barber_profiles (id),
                    CONSTRAINT uq_services_shop_barber_name UNIQUE (shop_id, barber_id, name)
                )
            """))
            connection.execute(text("""
                INSERT INTO services_rebuilt (id, shop_id, barber_id, name, description, duration_minutes, price_cents, booking_fee_cents, deposit_cents, platform_fee_cents, is_active)
                SELECT id, shop_id, barber_id, name, description, duration_minutes, price_cents, booking_fee_cents, deposit_cents, platform_fee_cents, is_active FROM services
            """))
            connection.execute(text("DROP TABLE services"))
            connection.execute(text("ALTER TABLE services_rebuilt RENAME TO services"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_services_shop_id ON services (shop_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_services_barber_id ON services (barber_id)"))
            connection.execute(text("PRAGMA foreign_keys = ON"))
        nullable_shop_columns = {
            "address_line1": "VARCHAR(160)",
            "city": "VARCHAR(80)",
            "state": "VARCHAR(40)",
            "postal_code": "VARCHAR(20)",
            "latitude_microdegrees": "INTEGER",
            "longitude_microdegrees": "INTEGER",
        }
        for column_name, column_type in nullable_shop_columns.items():
            if column_name not in shop_columns:
                connection.execute(
                    text(f"ALTER TABLE barber_shops ADD COLUMN {column_name} {column_type}")
                )

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS checkout_attempts (
                    id INTEGER NOT NULL PRIMARY KEY,
                    shop_id INTEGER NOT NULL,
                    service_id INTEGER NOT NULL,
                    barber_id INTEGER,
                    payout_stripe_account_id VARCHAR(255),
                    client_phone VARCHAR(32) NOT NULL,
                    client_name VARCHAR(120),
                    starts_at DATETIME NOT NULL,
                    payment_option VARCHAR(40) NOT NULL,
                    amount_collected_cents INTEGER NOT NULL,
                    booking_fee_cents INTEGER NOT NULL,
                    deposit_cents INTEGER NOT NULL,
                    platform_fee_cents INTEGER NOT NULL,
                    status VARCHAR(40),
                    stripe_checkout_session_id VARCHAR(255) UNIQUE,
                    stripe_payment_intent_id VARCHAR(255),
                    expires_at DATETIME,
                    created_at DATETIME
                )
                """
            )
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_checkout_attempts_shop_id ON checkout_attempts (shop_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_checkout_attempts_starts_at ON checkout_attempts (starts_at)"))
        attempt_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(checkout_attempts)").all()}
        if "sms_opt_in" not in attempt_columns:
            connection.execute(text("ALTER TABLE checkout_attempts ADD COLUMN sms_opt_in BOOLEAN DEFAULT 1"))
        if "stripe_processing_fee_cents" not in attempt_columns:
            connection.execute(text("ALTER TABLE checkout_attempts ADD COLUMN stripe_processing_fee_cents INTEGER DEFAULT 0"))

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS barber_blockouts (
                    id INTEGER NOT NULL,
                    shop_id INTEGER NOT NULL,
                    barber_id INTEGER NOT NULL,
                    blocked_date VARCHAR(10) NOT NULL,
                    reason VARCHAR(255),
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(shop_id) REFERENCES barber_shops (id),
                    FOREIGN KEY(barber_id) REFERENCES barber_profiles (id),
                    CONSTRAINT uq_barber_blockouts_barber_date UNIQUE (barber_id, blocked_date)
                )
                """
            )
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_barber_blockouts_id ON barber_blockouts (id)")
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_barber_blockouts_blocked_date "
                "ON barber_blockouts (blocked_date)"
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS shop_date_hour_overrides (
                    id INTEGER NOT NULL,
                    shop_id INTEGER NOT NULL,
                    specific_date VARCHAR(10) NOT NULL,
                    opens_at VARCHAR(5),
                    closes_at VARCHAR(5),
                    is_closed BOOLEAN,
                    note VARCHAR(255),
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(shop_id) REFERENCES barber_shops (id),
                    CONSTRAINT uq_shop_date_hour_overrides_shop_date UNIQUE (shop_id, specific_date)
                )
                """
            )
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_shop_date_hour_overrides_id ON shop_date_hour_overrides (id)")
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_shop_date_hour_overrides_shop_id "
                "ON shop_date_hour_overrides (shop_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_shop_date_hour_overrides_specific_date "
                "ON shop_date_hour_overrides (specific_date)"
            )
        )
