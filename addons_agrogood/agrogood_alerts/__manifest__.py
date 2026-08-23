{
    'name': 'Agrogood - Avisos automaticos',
    'summary': 'Pedidos atrasados, faltantes sin pedir, lotes por vencer y stock a cero',
    'description': """
Agrogood - Avisos automaticos
=============================

Cinco avisos diarios, todos con el mismo criterio: **decirle a una persona
concreta algo concreto que puede hacer hoy**. Un aviso que no dice quien debe
actuar, o que llega cuando ya no hay margen, se convierte en ruido y en dos
semanas nadie lo lee.

Se usan actividades de Odoo (`mail.activity`) y no correos. La actividad
aparece en la bandeja del responsable dentro del sistema, tiene fecha de
vencimiento y se cierra al resolverla. Un correo se pierde entre otros cien.

Cada aviso comprueba que no exista ya uno igual sin cerrar. Sin eso, un pedido
atrasado generaria una actividad nueva cada manana y la bandeja quedaria
inservible en una semana.

Los avisos:

* **Pedido atrasado** - paso su fecha de entrega y sigue sin entregarse.
* **Faltante sin pedir** - hay faltante y nadie lo paso a la pizarra de
  Compras. Es el hueco por el que se escapa el trabajo.
* **Solicitud estancada** - lleva dias sin moverse y la fecha ya paso.
* **Lote por vencer** - solo si queda stock: avisar de un lote ya vendido
  enseniaria a ignorar el aviso.
* **Sin stock** - solo de productos vendidos en el ultimo mes. Avisar de algo
  que nadie pide es lo que hace que se dejen de mirar los demas avisos.
""",
    'author': 'Agrogood',
    'website': 'https://www.agrogood.cl',
    'category': 'Agrogood',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['agrogood_procurement_board', 'agrogood_picking_ops', 'product_expiry'],
    'data': ['data/ir_cron.xml'],
    'installable': True,
}
