-- Rol de aplicacion para Odoo.
-- CREATEDB es necesario porque Odoo crea y restaura bases desde su gestor.
-- No se concede SUPERUSER: Odoo no lo requiere y limitarlo acota el dano
-- ante una credencial filtrada.
CREATE ROLE odoo WITH LOGIN CREATEDB PASSWORD :'odoo_password';

CREATE DATABASE agrogood_dev
    OWNER odoo
    ENCODING 'UTF8'
    TEMPLATE template0
    LC_COLLATE 'es-CL'
    LC_CTYPE 'es-CL';

COMMENT ON DATABASE agrogood_dev IS 'Agrogood - entorno de desarrollo';
