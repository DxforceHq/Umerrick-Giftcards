from django.db import migrations

def install_audit_guards(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql': return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""CREATE OR REPLACE FUNCTION giftcards_audit_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'Audit events are append-only'; END; $$ LANGUAGE plpgsql""")
        cursor.execute("CREATE TRIGGER giftcards_audit_no_update BEFORE UPDATE OR DELETE ON giftcards_auditevent FOR EACH ROW EXECUTE FUNCTION giftcards_audit_immutable()")
def remove_audit_guards(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql': return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP TRIGGER IF EXISTS giftcards_audit_no_update ON giftcards_auditevent')
        cursor.execute('DROP FUNCTION IF EXISTS giftcards_audit_immutable()')
class Migration(migrations.Migration):
    dependencies=[('giftcards','0001_initial')]
    operations=[migrations.RunPython(install_audit_guards,remove_audit_guards)]
