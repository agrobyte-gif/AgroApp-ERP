-- ---------------------------------------------------------------------------
-- Agrogood - creacion del rol y la base de datos de desarrollo
-- Para ejecutar en la Query Tool de pgAdmin 4, conectado como 'postgres'.
--
-- ANTES DE EJECUTAR: sustituye PON_AQUI_TU_CLAVE por la clave que elijas.
-- Debe ser exactamente la misma que pongas en db_password de odoo.conf.
-- ---------------------------------------------------------------------------

-- Rol de aplicacion. CREATEDB es necesario porque Odoo crea y restaura bases
-- desde su propio gestor. No se concede SUPERUSER: Odoo no lo requiere y
-- limitarlo acota el dano ante una credencial filtrada.
CREATE ROLE odoo WITH LOGIN CREATEDB PASSWORD 'PON_AQUI_TU_CLAVE';

-- La base debe crearse en una ejecucion aparte: PostgreSQL no permite
-- CREATE DATABASE dentro de un bloque de transaccion, y pgAdmin envuelve en
-- transaccion todo lo que se ejecuta de una sola vez.
-- Selecciona solo esta sentencia y ejecutala por separado (F5 sobre la seleccion):
CREATE DATABASE agrogood_dev
    OWNER odoo
    ENCODING 'UTF8'
    TEMPLATE template0;
