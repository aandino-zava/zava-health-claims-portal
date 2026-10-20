"""Initial synthetic claims schema."""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None


def upgrade():
    op.create_table("claims",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("patient_id", sa.String(50), nullable=False),
        sa.Column("patient_name", sa.String(160), nullable=False),
        sa.Column("service_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("request_key", sa.String(250), unique=True),
        sa.Column("request_hash", sa.String(64)),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.CheckConstraint("amount_cents > 0", name="positive_amount"),
        sa.CheckConstraint("version > 0", name="positive_version"),
    )
    for column in ("patient_id", "patient_name", "service_type", "status"):
        op.create_index(f"ix_claims_{column}", "claims", [column])


def downgrade():
    op.drop_table("claims")
