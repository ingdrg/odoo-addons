from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    axi_recpam_account_id = fields.Many2one(
        'account.account',
        string='Cuenta RECPAM',
        domain="[('company_id', '=', id), ('deprecated', '=', False)]",
        help='Cuenta contable a usar como contrapartida de los ajustes por inflación.',
    )
    axi_non_monetary_tag_id = fields.Many2one(
        'account.account.tag',
        string='Etiqueta cuentas no monetarias',
        help='Etiqueta que identifica las cuentas a reexpresar.',
    )
    axi_journal_id = fields.Many2one(
        'account.journal',
        string='Diario de ajuste por inflación',
        domain="[('type', '=', 'general'), ('company_id', '=', id)]",
        help='Diario propuesto por defecto al crear un batch de ajuste. Se puede cambiar en cada batch.',
    )
    axi_excluded_journal_ids = fields.Many2many(
        'account.journal',
        'axi_company_excluded_journal_rel',
        'company_id', 'journal_id',
        string='Diarios excluidos del reporte',
        domain="[('company_id', '=', id)]",
        help='Diarios excluidos por defecto en el reporte de Sumas y Saldos Comparativo.',
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Los domains de los campos en res.company usan `id` (= la compañía en su propio form),
    # pero al heredarse via related en settings, `id` pasa a ser el id del transient y no
    # matchea nada. Por eso acá se redefinen los domains en función de company_id.
    axi_recpam_account_id = fields.Many2one(
        related='company_id.axi_recpam_account_id', readonly=False,
        domain="[('company_id', '=', company_id), ('deprecated', '=', False)]",
    )
    axi_non_monetary_tag_id = fields.Many2one(
        related='company_id.axi_non_monetary_tag_id', readonly=False,
    )
    axi_journal_id = fields.Many2one(
        related='company_id.axi_journal_id', readonly=False,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
    )
    axi_excluded_journal_ids = fields.Many2many(
        related='company_id.axi_excluded_journal_ids', readonly=False,
        domain="[('company_id', '=', company_id)]",
    )
