"""Normalize department sender addresses while preserving existing mappings.

Revision ID: d035a91e7b62
Revises: c914e3fa7012
"""

import sqlalchemy as sa

from alembic import op

revision = "d035a91e7b62"
down_revision = "c914e3fa7012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "department_senders",
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("address", sa.String(200), primary_key=True),
    )
    op.create_index("ix_department_senders_address", "department_senders", ["address"])
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO department_senders (department_id, address) SELECT id, lower(trim(sender)) FROM departments"
        )
    )
    constraints = sa.inspect(connection).get_unique_constraints("departments")
    with op.batch_alter_table("departments", naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"}) as batch:
        for constraint in constraints:
            if constraint["column_names"] == ["sender"]:
                batch.drop_constraint(constraint["name"] or "uq_departments_sender", type_="unique")
        batch.drop_column("sender")


def downgrade() -> None:
    connection = op.get_bind()
    invalid = connection.execute(
        sa.text(
            "SELECT d.id FROM departments d LEFT JOIN department_senders s ON s.department_id = d.id "
            "GROUP BY d.id HAVING count(s.address) != 1 LIMIT 1"
        )
    ).first()
    shared = connection.execute(
        sa.text("SELECT address FROM department_senders GROUP BY address HAVING count(*) > 1 LIMIT 1")
    ).first()
    too_long = connection.execute(
        sa.text("SELECT address FROM department_senders WHERE length(address) > 120 LIMIT 1")
    ).first()
    if invalid or shared or too_long:
        raise RuntimeError("Downgrade requires one unique sender of at most 120 characters per department")
    op.add_column("departments", sa.Column("sender", sa.String(120), nullable=True))
    connection.execute(
        sa.text(
            "UPDATE departments SET sender = (SELECT address FROM department_senders WHERE department_id = departments.id)"
        )
    )
    with op.batch_alter_table("departments") as batch:
        batch.alter_column("sender", nullable=False, existing_type=sa.String(120))
        batch.create_unique_constraint("uq_departments_sender", ["sender"])
    op.drop_index("ix_department_senders_address", table_name="department_senders")
    op.drop_table("department_senders")
