"""Remove the retired OCR eligibility setting; preserve all evidence/history rows."""

import sqlalchemy as sa

from alembic import op

revision = "739e52fa3c48"
down_revision = "628d41ef2b37"
branch_labels = None
depends_on = None


def upgrade():
    rules = sa.table("demo_rules", sa.column("id", sa.Integer()), sa.column("settings", sa.JSON()))
    bind = op.get_bind()
    for rule_id, settings in bind.execute(sa.select(rules.c.id, rules.c.settings)).all():
        if "require_readable_ocr" in settings:
            updated = {key: value for key, value in settings.items() if key != "require_readable_ocr"}
            bind.execute(rules.update().where(rules.c.id == rule_id).values(settings=updated))


def downgrade():
    # Older code requires the key; restore its conservative default, not OCR data.
    rules = sa.table("demo_rules", sa.column("id", sa.Integer()), sa.column("settings", sa.JSON()))
    bind = op.get_bind()
    for rule_id, settings in bind.execute(sa.select(rules.c.id, rules.c.settings)).all():
        bind.execute(
            rules.update().where(rules.c.id == rule_id).values(settings={"require_readable_ocr": True, **settings})
        )
