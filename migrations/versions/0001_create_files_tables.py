"""create files and file_chunks tables

Revision ID: a1b2c3d4e5f60718293a4b5c6d7e8f90
Revises:
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("original_name", sa.Text(), nullable=False),
        sa.Column(
            "content_type",
            sa.Text(),
            server_default="application/octet-stream",
            nullable=False,
        ),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("size >= 0", name="ck_files_size_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("idx_files_created_at", "files", ["created_at"])

    op.create_table(
        "file_chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("file_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("seq > 0", name="ck_file_chunks_seq_positive"),
        sa.CheckConstraint("size > 0", name="ck_file_chunks_size_positive"),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "file_id",
            "seq",
            name="uq_file_chunks_file_id_seq",
        ),
    )
    op.create_index("idx_file_chunks_file_id", "file_chunks", ["file_id"])


def downgrade() -> None:
    op.drop_index("idx_file_chunks_file_id", table_name="file_chunks")
    op.drop_table("file_chunks")
    op.drop_index("idx_files_created_at", table_name="files")
    op.drop_table("files")
