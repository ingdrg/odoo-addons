from odoo import fields, models


class AxiResult(models.Model):
    _name = 'axi.result'
    _description = 'Detalle de Ajuste por Inflación'
    _order = 'batch_id desc, account_id'

    name = fields.Char(required=True)
    batch_id = fields.Many2one('axi.batch', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='batch_id.company_id', store=True, index=True)
    account_id = fields.Many2one('account.account', required=True, ondelete='restrict')
    base_nominal = fields.Monetary(currency_field='currency_id')
    coef_aplicado = fields.Float(digits=(16, 8))
    monto_ajustado = fields.Monetary(currency_field='currency_id')
    delta_ajuste = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)
