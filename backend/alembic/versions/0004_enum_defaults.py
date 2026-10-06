"""Match enum server defaults to SQLAlchemy's persisted member names."""
from alembic import op

revision = "0004_enum_defaults"
down_revision = "0003_paper_market_fields"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("orders", "backtests"):
        op.alter_column(table, "status", server_default="PENDING")


def downgrade():
    for table in ("orders", "backtests"):
        op.alter_column(table, "status", server_default="pending")
