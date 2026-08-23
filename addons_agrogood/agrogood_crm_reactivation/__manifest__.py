{
    'name': 'Agrogood - Reactivacion de clientes',
    'summary': 'Comportamiento de compra y lista diaria de recontacto',
    'description': """
Agrogood - Reactivacion de clientes
===================================

Convierte el historial de ventas en una lista corta de llamadas concretas.

Las metricas viven como campos del cliente, no en un modelo aparte: son
atributos suyos, no entidades propias. Se almacenan y las recalcula un proceso
nocturno, porque recorrer el historico cada vez que alguien abre una ficha se
nota ya con la cartera actual.

**La situacion comercial es relativa, no absoluta.** Un umbral fijo de dias
trata igual a quien compra a diario y a quien compra una vez al mes, y por eso
genera avisos que Ventas aprende a ignorar. Aqui el retraso se mide contra el
ritmo habitual de cada cliente.

El motivo mas fiable en distribucion es el mas simple: **compro este mismo dia
la semana pasada y hoy no ha pedido**. Los clientes de este rubro tienen dias
fijos, y cuando uno se salta el suyo casi siempre es un olvido, no una
decision.
""",
    'author': 'Agrogood',
    'website': 'https://www.agrogood.cl',
    'category': 'Agrogood',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['agrogood_sales', 'crm'],
    'data': [
        'security/ir.model.access.csv',
        'views/agrogood_followup_views.xml',
        'views/res_partner_views.xml',
        'data/ir_cron.xml',
        'views/menus.xml',
    ],
    'installable': True,
}
