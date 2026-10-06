"""Add paper market fields omitted from the original initial migration."""
from alembic import op
import sqlalchemy as sa

revision = "0003_paper_market_fields"
down_revision = "0002_paper_execution_state"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("paper_accounts", sa.Column("symbol", sa.String(32), nullable=False, server_default="BTC/USDT"))
    op.add_column("paper_accounts", sa.Column("timeframe", sa.String(16), nullable=False, server_default="1h"))


def downgrade():
    op.drop_column("paper_accounts", "timeframe")
    op.drop_column("paper_accounts", "symbol")
