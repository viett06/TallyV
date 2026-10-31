"""Use the previous month's 26th through the named month's 25th for payroll.

Revision ID: b703d8a21c45
Revises: a6c832f03190
"""

import calendar
from datetime import date, timedelta

import sqlalchemy as sa

from alembic import op

revision = "b703d8a21c45"
down_revision = "a6c832f03190"
branch_labels = None
depends_on = None


def _periods():
    return sa.table(
        "review_periods", sa.column("id", sa.String), sa.column("starts", sa.Date), sa.column("ends", sa.Date)
    )


def upgrade() -> None:
    periods = _periods()
    connection = op.get_bind()
    for period_id in connection.execute(sa.select(periods.c.id)).scalars().all():
        ends = date.fromisoformat(period_id + "-25")
        starts = (ends.replace(day=1) - timedelta(days=1)).replace(day=26)
        connection.execute(periods.update().where(periods.c.id == period_id).values(starts=starts, ends=ends))


def downgrade() -> None:
    periods = _periods()
    connection = op.get_bind()
    for period_id in connection.execute(sa.select(periods.c.id)).scalars().all():
        starts = date.fromisoformat(period_id + "-01")
        ends = starts.replace(day=calendar.monthrange(starts.year, starts.month)[1])
        connection.execute(periods.update().where(periods.c.id == period_id).values(starts=starts, ends=ends))
