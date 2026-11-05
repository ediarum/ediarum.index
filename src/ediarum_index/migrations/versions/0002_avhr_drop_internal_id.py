"""avhr: drop ``internal_id`` from the entries' data

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-03

avhr's ``internal_id`` was a copy of the record's ``xml:id``, which the entry
already holds as its ``source_id`` (and the export writes from there). The
field is gone from avhr's schema and ingest, so the stored copies go too —
otherwise ``schemas.validate_entry`` would refuse to save an edit of such an
entry ("Unknown fields"). Nothing is lost: each value equals the entry's
``source_id``. ``updated_at`` is left alone (not a curator edit).
MEGA's ``internal_id`` is its own field and stays.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove the key (JSON_REMOVE: MariaDB and SQLite alike)."""
    op.execute(
        "UPDATE entry SET data = JSON_REMOVE(data, '$.internal_id') "
        "WHERE project_name = 'avhr' AND JSON_EXTRACT(data, '$.internal_id') IS NOT NULL"
    )


def downgrade() -> None:
    """Restore it from ``source_id``, where it came from."""
    op.execute(
        "UPDATE entry SET data = JSON_SET(data, '$.internal_id', source_id) "
        "WHERE project_name = 'avhr' AND source_id IS NOT NULL"
    )
