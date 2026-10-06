"""Pin paper strategy versions and persist candle/risk execution state."""
from alembic import op
import sqlalchemy as sa

revision = "0002_paper_execution_state"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("paper_accounts", sa.Column("strategy_version_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_paper_strategy_version", "paper_accounts", "strategy_versions", ["strategy_version_id"], ["id"], ondelete="SET NULL")
    op.add_column("paper_accounts", sa.Column("last_processed_bar", sa.DateTime(timezone=True), nullable=True))
    for name in ("stop_loss", "take_profit", "last_mark_price"):
        op.add_column("positions", sa.Column(name, sa.Numeric(20, 8), nullable=True))


def downgrade():
    for name in ("last_mark_price", "take_profit", "stop_loss"):
        op.drop_column("positions", name)
    op.drop_column("paper_accounts", "last_processed_bar")
    op.drop_constraint("fk_paper_strategy_version", "paper_accounts", type_="foreignkey")
    op.drop_column("paper_accounts", "strategy_version_id")
