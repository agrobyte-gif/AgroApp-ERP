-- Rol de aplicacion para Odoo.
-- CREATEDB es necesario porque Odoo crea y restaura bases desde su gestor.
-- No se concede SUPERUSER: Odoo no lo requiere y limitarlo acota el dano
-- ante una credencial filtrada.
CREATE ROLE odoo WITH LOGIN CREATEDB PASSWORD :'odoo_password';

CREATE DATABASE agrogood_dev
    OWNER odoo
    ENCODING 'UTF8'
    TEMPLATE template0;
-- Sin LC_COLLATE/LC_CTYPE explicitos: PostgreSQL en Windows no acepta el
-- formato 'es-CL' (usaria 'Spanish_Chile.1252'). Se hereda el locale del
-- servidor, que es lo correcto: Odoo gestiona idioma y formato por si mismo.

COMMENT ON DATABASE agrogood_dev IS 'Agrogood - entorno de desarrollo';
