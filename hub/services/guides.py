"""Shared installation guides with durable last-editor attribution."""
from hub import db


def migrate(conn):
    columns = {row['name'] for row in conn.execute('PRAGMA table_info(game_guides)')}
    if 'author_name' not in columns:
        conn.execute("ALTER TABLE game_guides ADD COLUMN author_name TEXT NOT NULL DEFAULT ''")
    conn.execute("""UPDATE game_guides SET author_name=COALESCE(
        (SELECT username FROM users WHERE users.id=game_guides.author),'')
        WHERE author_name=''""")


def get(slug):
    row = db.query("""SELECT gg.*, COALESCE(NULLIF(gg.author_name,''),u.username,'') AS author_display
        FROM game_guides gg LEFT JOIN users u ON u.id=gg.author WHERE gg.slug=?""", (slug,), one=True)
    return dict(row) if row else None


def save(slug, values, user, updated_at):
    db.execute("""INSERT INTO game_guides
        (slug,verified_version,game_version,mod_url,source_url,steps,trouble,updated_at,author,author_name)
        VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(slug) DO UPDATE SET
        verified_version=excluded.verified_version,game_version=excluded.game_version,
        mod_url=excluded.mod_url,source_url=excluded.source_url,steps=excluded.steps,
        trouble=excluded.trouble,updated_at=excluded.updated_at,
        author=excluded.author,author_name=excluded.author_name""",
        (slug, *(values[key] for key in ('verified_version','game_version','mod_url','source_url','steps','trouble')),
         updated_at,user['id'],user['username']))
