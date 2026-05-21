"""Re-apply append-only PG trigger after migrations were reset."""

from django.db import migrations


SQL_INSTALL = """
CREATE OR REPLACE FUNCTION block_audit_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_entry is append-only (% is forbidden)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_block_mutation ON audit_entry;
CREATE TRIGGER audit_block_mutation
    BEFORE UPDATE OR DELETE ON audit_entry
    FOR EACH ROW EXECUTE FUNCTION block_audit_mutation();
"""

SQL_UNINSTALL = """
DROP TRIGGER IF EXISTS audit_block_mutation ON audit_entry;
DROP FUNCTION IF EXISTS block_audit_mutation();
"""


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(SQL_INSTALL)


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(SQL_UNINSTALL)


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]
    operations = [migrations.RunPython(install, reverse_code=uninstall)]
