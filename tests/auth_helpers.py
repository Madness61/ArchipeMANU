"""Explicit test accounts for feature tests; real authentication is tested separately."""
from werkzeug.security import generate_password_hash
from hub import db, yamlgen

TEST_PASSWORD = "Test password for player 42!"
PASSWORD_HASH = generate_password_hash(TEST_PASSWORD, method="scrypt")


def provision_user(app, username, is_admin=False):
    with app.app_context():
        db.execute("""INSERT OR IGNORE INTO users(username,slot_name,is_admin,password_hash)
            VALUES (?,?,?,?)""", (username,yamlgen.clean_slot_name(username),int(is_admin),PASSWORD_HASH))
