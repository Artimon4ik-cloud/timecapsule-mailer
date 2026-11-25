import json
import os
import ssl
import time

import pg8000.dbapi


def lambda_handler(event, context):
    for record in event["Records"]:
        message = json.loads(record["body"])

        if message.get("event_type") != "capsule.sealed":
            continue

        capsule_id = message["capsule_id"]

        connection = pg8000.dbapi.connect(
            host=os.environ["DB_HOST"],
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            ssl_context=ssl.create_default_context(
                cafile="global-bundle.pem"
            ),
            timeout=5
        )

        try:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT c.user_id, c.title, c.open_at,
                       COALESCE(c.recipient_email, u.email)
                FROM capsules c
                JOIN users u ON u.id = c.user_id
                WHERE c.id = %s
            """, (capsule_id,))

            capsule = cursor.fetchone()

            if capsule is None:
                print(f"Capsule {capsule_id} not found")
                continue

            user_id, title, open_at, recipient = capsule

            time.sleep(float(os.getenv("MAIL_DELAY_SECONDS", "3")))

            text = (
                f'Capsule "{title}" was sealed for you '
                f'until {open_at:%Y-%m-%d %H:%M} UTC.'
            )

            cursor.execute("""
                INSERT INTO notifications
                    (capsule_id, user_id, recipient, message, event_type)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (capsule_id, event_type) DO NOTHING
            """, (
                capsule_id,
                user_id,
                recipient,
                text,
                "capsule.sealed"
            ))

            inserted = cursor.rowcount
            connection.commit()

            if inserted:
                print(f"Notification created: capsule {capsule_id}")
            else:
                print(f"Duplicate ignored: capsule {capsule_id}")

        finally:
            connection.close()

    return {"status": "ok"}