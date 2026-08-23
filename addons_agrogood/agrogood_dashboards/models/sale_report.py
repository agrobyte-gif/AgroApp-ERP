from odoo import fields, models


class SaleReport(models.Model):
    """La linea comercial en el informe de ventas.

    Sin esto no se puede responder a la pregunta mas basica de Direccion:
    cuanto vende cada linea. El campo se anade a la consulta del informe, no
    como columna calculada: agruparlo en SQL es lo que permite pivotar sobre
    miles de lineas sin que la pantalla se quede pensando.
    """

    _inherit = 'sale.report'

    agrogood_business_line_id = fields.Many2one(
        comodel_name='agrogood.business.line',
        string="Linea comercial", readonly=True,
    )

    def _select_additional_fields(self):
        res = super()._select_additional_fields()
        res['agrogood_business_line_id'] = "partner.agrogood_business_line_id"
        return res

    def _group_by_sale(self):
        return super()._group_by_sale() + """,
            partner.agrogood_business_line_id"""
