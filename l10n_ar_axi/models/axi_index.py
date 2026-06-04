from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AxiIndex(models.Model):
    _name = 'axi.index'
    _description = 'Indice IPC'
    _order = 'date desc, id desc'
    _rec_name = 'label'

    name = fields.Char(required=True)
    date = fields.Date(required=True, index=True)
    index_value = fields.Float(required=True, digits=(16, 6))
    active = fields.Boolean(default=True)
    label = fields.Char(compute='_compute_label', store=True)

    _sql_constraints = [
        ('axi_index_date_unique', 'unique(date)', 'Ya existe un índice para esa fecha.'),
        ('axi_index_value_positive', 'CHECK(index_value > 0)', 'El índice debe ser mayor que cero.'),
    ]

    @api.depends('name', 'date', 'index_value')
    def _compute_label(self):
        for rec in self:
            if rec.date:
                rec.label = '%s | %s' % (rec.date, rec.name or rec.index_value)
            else:
                rec.label = rec.name or str(rec.index_value)

    @api.constrains('date')
    def _check_month_end_date(self):
        for rec in self:
            if rec.date:
                month_end = fields.Date.end_of(rec.date, 'month')
                if rec.date != month_end:
                    raise ValidationError(_('La fecha del índice debe ser el último día del mes (%s).') % month_end)
