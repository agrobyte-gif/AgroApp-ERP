from odoo import api, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.depends('vat', 'agrogood_business_line_id', 'l10n_cl_sii_taxpayer_type')
    def _compute_agrogood_billing(self):
        # Se redeclaran todas las dependencias, incluidas las de la definicion
        # base: Odoo toma las del metodo que encuentra en el modelo.
        return super()._compute_agrogood_billing()

    def _agrogood_billing_blockers(self):
        """En Chile el RUT no basta: `l10n_cl` exige tambien el tipo de
        contribuyente al validar cualquier documento que no sea boleta
        (_check_document_types_post exime los tipos 35, 38, 39 y 41).

        Sin esta comprobacion, un cliente con RUT figuraba como facturable y
        fallaba al emitir la factura, con el pedido ya entregado.
        """
        motivos = super()._agrogood_billing_blockers()
        if not self.l10n_cl_sii_taxpayer_type:
            motivos.append("Falta el tipo de contribuyente")
        return motivos
