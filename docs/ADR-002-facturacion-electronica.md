# ADR-002 - Facturacion electronica chilena

Fecha: 2026-08-21
Estado: aceptado, con revision prevista

## Contexto

Odoo Community no emite Documentos Tributarios Electronicos chilenos. El modulo
`l10n_cl` presente en el arbol aporta unicamente plan de cuentas, impuestos,
tipos de documento y validacion de RUT. El modulo que realiza la emision -
`l10n_cl_edi`: gestion de CAF, folios, firma XML-DSig y dialogo con el SII - es
exclusivo de Odoo Enterprise.

Se evaluaron tres caminos: proveedor externo con API, licencia Enterprise y
desarrollo propio de la firma.

## Decision

Agrogood emitira sus documentos en el **portal gratuito de Facturacion
Electronica MIPYME del SII**. Odoo no emite: **registra** el documento ya
emitido, conservando folio, tipo de documento, fecha, PDF y estado, vinculado a
la factura de Odoo correspondiente.

## Consecuencias aceptadas

* **Doble digitacion.** El documento se emite en el sitio del SII y se registra
  en Odoo. Es trabajo manual recurrente para Ventas.
* **Sin validacion automatica.** Odoo no conoce el estado real en el SII salvo
  que alguien lo registre. Los rechazos se detectan fuera del sistema.
* **Techo de crecimiento.** El portal MIPYME esta restringido por tamano de
  empresa y por volumen. Al superarlo, Agrogood debera migrar.

## Diseno que protege la decision

`agrogood_edi_cl` separa dos responsabilidades que en una implementacion ingenua
irian juntas:

1. **Registro documental** - modelo `agrogood.dte`, ligado a `account.move`:
   tipo de documento, folio, fecha, XML, PDF, estado, motivo de rechazo,
   historial de reintentos. Es independiente de como se emitio el documento.
2. **Mecanismo de emision** - una interfaz con una unica implementacion inicial,
   `manual` (portal MIPYME), donde el usuario adjunta el documento emitido.

Anadir manana un proveedor con API es escribir una segunda implementacion de esa
interfaz. El registro documental, los informes, la trazabilidad y las vistas no
cambian.

Deliberadamente **no** se construye un framework de proveedores: una interfaz
con dos metodos y una implementacion. La indireccion se justifica porque la
migracion es probable, no hipotetica.

## Revision

Reevaluar cuando se cumpla cualquiera de estas condiciones:

* Agrogood se acerque al limite de volumen o de tamano del portal MIPYME.
* El coste en horas de la doble digitacion supere el coste de un proveedor.
* Aparezca un rechazo del SII no detectado que genere un problema real.
