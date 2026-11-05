from django.db import migrations


def install_mysql_audit_guards(apps, schema_editor):
    if schema_editor.connection.vendor != 'mysql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP TRIGGER IF EXISTS giftcards_audit_no_update_mysql')
        cursor.execute('DROP TRIGGER IF EXISTS giftcards_audit_no_delete_mysql')
        cursor.execute("""
            CREATE TRIGGER giftcards_audit_no_update_mysql
            BEFORE UPDATE ON giftcards_auditevent
            FOR EACH ROW
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit events are append-only'
        """)
        cursor.execute("""
            CREATE TRIGGER giftcards_audit_no_delete_mysql
            BEFORE DELETE ON giftcards_auditevent
            FOR EACH ROW
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Audit events are append-only'
        """)


def remove_mysql_audit_guards(apps, schema_editor):
    if schema_editor.connection.vendor != 'mysql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP TRIGGER IF EXISTS giftcards_audit_no_update_mysql')
        cursor.execute('DROP TRIGGER IF EXISTS giftcards_audit_no_delete_mysql')


class Migration(migrations.Migration):
    atomic = False
    dependencies = [('giftcards', '0003_giftcard_activation_customer_spend')]
    operations = [migrations.RunPython(install_mysql_audit_guards, remove_mysql_audit_guards)]
