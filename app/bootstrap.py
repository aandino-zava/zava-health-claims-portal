"""Provision a restricted runtime role after migrations, using the bootstrap connection."""

from psycopg import sql
from sqlalchemy.engine import make_url


def configure_runtime_role(connection, runtime_url):
    url = make_url(runtime_url)
    if not url.username or not url.password:
        raise ValueError("DATABASE_URL requires runtime username and password")
    # Track the transaction in SQLAlchemy even when this helper is called without
    # the startup advisory-lock query. Driver-only transactions otherwise roll back
    # when a pooled connection closes.
    if not connection.in_transaction():
        connection.begin()
    # Identifiers and password literals are escaped by the driver, never interpolated.
    with connection.connection.driver_connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
            "FROM pg_roles WHERE rolname = %s", (url.username,),
        )
        privileges = cursor.fetchone()
        if privileges and any(privileges):
            raise ValueError("Runtime role already has elevated privileges; use a dedicated role")
        cursor.execute(
            "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member WHERE r.rolname = %s",
            (url.username,),
        )
        if cursor.fetchone():
            raise ValueError("Runtime role must not have membership in another role")
        cursor.execute(
            "SELECT 1 FROM pg_roles r WHERE r.rolname = %s AND ("
            "EXISTS (SELECT 1 FROM pg_database d WHERE d.datdba = r.oid) OR "
            "EXISTS (SELECT 1 FROM pg_class c WHERE c.relowner = r.oid) OR "
            "EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspowner = r.oid))", (url.username,),
        )
        if cursor.fetchone():
            raise ValueError("Runtime role must not own databases, tables, or schemas")
        if privileges is None:
            cursor.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                                   "NOREPLICATION NOBYPASSRLS").format(sql.Identifier(url.username)))
        cursor.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
            sql.Identifier(url.username), sql.Literal(url.password)))
        cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        cursor.execute(sql.SQL("REVOKE CREATE, TEMPORARY ON DATABASE {} FROM PUBLIC").format(
            sql.Identifier(url.database)))
        cursor.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(
            sql.Identifier(url.database), sql.Identifier(url.username)))
        cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(url.database), sql.Identifier(url.username)))
        cursor.execute(sql.SQL("REVOKE ALL ON SCHEMA public FROM {}").format(sql.Identifier(url.username)))
        cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(url.username)))
        cursor.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(
            sql.Identifier(url.username)))
        cursor.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE ON TABLE public.claims TO {}").format(
            sql.Identifier(url.username)))
    connection.commit()
