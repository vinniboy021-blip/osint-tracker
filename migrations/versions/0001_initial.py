"""initial relational schema"""
from alembic import op
from app.db import Base
import app.models
def upgrade(): Base.metadata.create_all(op.get_bind())
def downgrade(): Base.metadata.drop_all(op.get_bind())
